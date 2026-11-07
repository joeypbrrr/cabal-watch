"""Polling loop. Reads public JSON and writes the data contract. Sends nothing."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from monitor import COGE_MINT, DEMOCAT_MINT
from monitor.api import Client, launch_rows, price_map
from monitor.logic import (
    build_bubble_token,
    build_early_buys,
    due_mints,
    et_iso,
    observe_checkpoints,
    stamp,
    update_known_holdings,
    apply_trades,
)

LIVE_FILES = (
    "wallets.json",
    "funding.json",
    "transactions.json",
    "alerts.json",
    "paper.json",
    "bubbles.json",
    "early_buys.json",
)
KNOWN_SYMBOLS = {COGE_MINT: "COGE", DEMOCAT_MINT: "Democat"}
ROOT = Path(__file__).resolve().parents[1]


def read_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def empty_alerts(now):
    return stamp({
        "alerts": [],
        "rule": {
            "flag": "possible_next_play",
            "trigger": "Any screenshot-matched cluster wallet buys a previously unknown mint",
            "excluded_mints": [COGE_MINT, DEMOCAT_MINT],
            "coach_mint_status": "unresolved; do not silently treat a name-only candidate as confirmed",
        },
        "warning": "A token is not excluded just because its name is Coach. No Coach mint is confirmed.",
    }, now)


class Monitor:
    def __init__(self, out, seed_dir=None, client=None, now=None, sleep=None, publish=True,
                 trade_poll_s=180, slow_s=1800, publish_s=1800, once=False):
        self.out = Path(out)
        self.seed_dir = Path(seed_dir or (ROOT / "data"))
        self.client = client or Client()
        self.now = now or (lambda: datetime.now().astimezone())
        self.sleep = sleep or __import__("time").sleep
        self.publish_enabled = publish
        self.trade_poll_s = trade_poll_s
        self.slow_s = slow_s
        self.publish_s = publish_s
        self.once = once
        self.state = {}

    def path(self, name):
        return self.out / name

    def seed(self):
        self.out.mkdir(parents=True, exist_ok=True)
        for name in LIVE_FILES:
            dest = self.path(name)
            src = self.seed_dir / name
            if not dest.exists() and src.exists():
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        now = self.now()
        if not self.path("alerts.json").exists():
            write_json(self.path("alerts.json"), empty_alerts(now))
        if not self.path("transactions.json").exists():
            write_json(self.path("transactions.json"), stamp({
                "transactions": [],
                "as_of": et_iso(now),
                "coverage": {"wallets_queried": [], "since": None, "retention_start": None,
                             "pumpfun_and_pumpswap_only": True, "api_returned_count": 0, "more": False},
            }, now))
        if not self.path("paper.json").exists():
            write_json(self.path("paper.json"), stamp({
                "paper": [],
                "model": {
                    "basis": "market_cap_return_gross_proxy_not_executable_pnl",
                    "formula": "(checkpoint_mcap / entry_mcap - 1) * 100",
                    "horizons_minutes": [15, 60, 360],
                    "fees_slippage_included": False,
                },
                "warning": "Simulated market-cap change only. No orders are sent.",
            }, now))
        if not self.path("wallets.json").exists():
            raise RuntimeError("wallets.json is missing. Seed the output directory from data/wallets.json.")
        self.state = read_json(self.path("monitor_state.json"), {})

    def save_state(self):
        write_json(self.path("monitor_state.json"), self.state)

    def watched(self, role=None):
        doc = read_json(self.path("wallets.json"), {"wallets": []})
        wallets = []
        for wallet in doc.get("wallets") or []:
            if not wallet.get("watch") or not wallet.get("address"):
                continue
            if role is not None and wallet.get("role") != role:
                continue
            wallets.append(wallet)
        return wallets

    def cycle(self):
        self.poll_launches()
        self.poll_trades()
        self.observe_paper()
        now = self.now()
        if self._due("last_slow_at", self.slow_s, now):
            self.rebuild_slow()
            self.state["last_slow_at"] = et_iso(now)
            self.save_state()
        if self.publish_enabled and self._due("last_publish_at", self.publish_s, now):
            self.publish()
            self.state["last_publish_at"] = et_iso(now)
            self.save_state()

    def run(self):
        self.seed()
        while True:
            try:
                self.cycle()
            except Exception as exc:
                self.state["last_error"] = str(exc)[:500]
                self.save_state()
                print("monitor cycle failed:", exc, file=sys.stderr, flush=True)
                if self.once:
                    return 1
            if self.once:
                return 0
            self.sleep(self.trade_poll_s)

    def _due(self, key, seconds, now):
        previous = self.state.get(key)
        if not previous:
            return True
        from monitor.logic import as_et
        then = as_et(previous)
        current = as_et(now)
        if then is None or current is None:
            return True
        return current - then >= timedelta(seconds=seconds)

    def poll_launches(self):
        launches = self.state.setdefault("launches", {})
        cursors = self.state.setdefault("launch_cursors", {})
        for wallet in self.watched("deployer"):
            address = wallet["address"]
            cursor = cursors.get(address)
            pages = 0
            while pages < 5:
                try:
                    body = self.client.launches(address, cursor)
                except Exception as exc:
                    print("launches skipped", address, exc, file=sys.stderr, flush=True)
                    break
                for row in launch_rows(body):
                    mint = row.get("mint")
                    if not mint:
                        continue
                    launches[mint] = {
                        "created": row.get("created"),
                        "creator": row.get("creator") or row.get("deployer"),
                        "slot": row.get("slot"),
                    }
                cursor = body.get("next_since", cursor)
                pages += 1
                if not body.get("more"):
                    break
            if cursor is not None:
                cursors[address] = cursor
        self.save_state()

    def poll_trades(self):
        from monitor.logic import as_et
        now = self.now()
        wallets = [wallet["address"] for wallet in self.watched()]
        if not wallets:
            return
        batch = wallets[:50]
        cursor = self.state.get("trades_since")
        if cursor is None:
            # The free feed keeps about three hours. Start at the back of that window.
            cursor = int(as_et(now).timestamp()) - (3 * 3600 - 90)
        raw = []
        more = False
        pages = 0
        while pages < 20:
            body = self.client.trades(batch, cursor)
            raw.extend(body.get("trades") or [])
            cursor = body.get("next_since", cursor)
            more = bool(body.get("more"))
            pages += 1
            if not more:
                break
        if cursor is not None:
            self.state["trades_since"] = cursor
        transactions = read_json(self.path("transactions.json"), {"transactions": []})
        alerts = read_json(self.path("alerts.json"), empty_alerts(now))
        paper = read_json(self.path("paper.json"), {"paper": []})
        wallets_doc = read_json(self.path("wallets.json"), {"wallets": []})
        fresh = []
        seen = set()
        for trade in raw:
            from monitor.logic import normalize_trade, trade_key
            row = normalize_trade(trade)
            if row is None or trade_key(row) in seen:
                continue
            seen.add(trade_key(row))
            fresh.append(trade)
        mints = []
        from monitor.logic import excluded_mints, is_buy, screenshot_addresses
        screens = screenshot_addresses(wallets_doc)
        excluded = excluded_mints(alerts)
        for trade in fresh:
            row = normalize_trade(trade)
            if row["address"] in screens and row["side"] == "buy" and row["mint"] not in excluded:
                if row["mint"] not in mints:
                    mints.append(row["mint"])
        try:
            prices = price_map(self.client.prices(mints)) if mints else {}
        except Exception as exc:
            print("price skipped", exc, file=sys.stderr, flush=True)
            prices = {}
        apply_trades(
            transactions, alerts, paper, wallets_doc, fresh,
            prices_by_mint=prices, launches_by_mint=self.state.get("launches") or {},
        )
        window_start = as_et(now) - timedelta(hours=3)
        transactions["as_of"] = et_iso(body.get("as_of") or now) if raw or body else et_iso(now)
        transactions["coverage"] = {
            "wallets_queried": batch,
            "since": et_iso(self.state.get("trades_since")) if isinstance(self.state.get("trades_since"), (int, float)) else self.state.get("trades_since"),
            "retention_start": et_iso(window_start),
            "pumpfun_and_pumpswap_only": True,
            "api_returned_count": len(raw),
            "more": more,
        }
        stamp(transactions, now)
        stamp(alerts, now)
        if "model" not in paper:
            paper["model"] = {
                "basis": "market_cap_return_gross_proxy_not_executable_pnl",
                "formula": "(checkpoint_mcap / entry_mcap - 1) * 100",
                "horizons_minutes": [15, 60, 360],
                "fees_slippage_included": False,
            }
        paper["warning"] = "Simulated market-cap change only. No orders are sent."
        stamp(paper, now)
        write_json(self.path("transactions.json"), transactions)
        write_json(self.path("alerts.json"), alerts)
        write_json(self.path("paper.json"), paper)
        self.save_state()

    def observe_paper(self):
        now = self.now()
        paper = read_json(self.path("paper.json"), {"paper": []})
        mints = due_mints(paper, now)
        if not mints:
            return
        prices = price_map(self.client.prices(mints))
        if observe_checkpoints(paper, now, prices):
            stamp(paper, now)
            write_json(self.path("paper.json"), paper)

    def rebuild_slow(self):
        now = self.now()
        wallets_doc = read_json(self.path("wallets.json"), {"wallets": []})
        funding_doc = read_json(self.path("funding.json"), {"edges": []})
        alerts = read_json(self.path("alerts.json"), {"alerts": []})
        transactions = read_json(self.path("transactions.json"), {"transactions": []})
        mints = [COGE_MINT, DEMOCAT_MINT]
        for alert in alerts.get("alerts") or []:
            mint = alert.get("mint")
            if mint and mint not in mints:
                mints.append(mint)
        tokens = []
        for mint in mints[:8]:
            try:
                body = self.client.holders(mint)
            except Exception as exc:
                print("holders skipped", mint, exc, file=sys.stderr, flush=True)
                continue
            symbol = KNOWN_SYMBOLS.get(mint)
            if symbol is None:
                for alert in alerts.get("alerts") or []:
                    if alert.get("mint") == mint and alert.get("symbol"):
                        symbol = alert["symbol"]
            token = build_bubble_token(mint, symbol, body, wallets_doc, funding_doc)
            tokens.append(token)
            update_known_holdings(wallets_doc, mint, symbol, token["holders"], token.get("as_of"))
        bubbles = read_json(self.path("bubbles.json"), {})
        previous = {token.get("mint"): token for token in bubbles.get("tokens") or [] if token.get("mint")}
        for token in tokens:
            previous[token["mint"]] = token
        ordered = []
        seen = set()
        for mint in list(mints) + list(previous):
            if mint in previous and mint not in seen:
                ordered.append(previous[mint])
                seen.add(mint)
        if ordered:
            bubbles["tokens"] = ordered
        bubbles["requested_refresh_seconds"] = 1800
        bubbles["warning"] = (
            "cluster_id stays null until ownership is verified. "
            "Exchange and busy-wallet links are not an ownership cluster. "
            "Holder rows are the top accounts, not all 63 screenshot wallets."
        )
        stamp(bubbles, now)
        prices = price_map(self.client.prices([row.get("mint") for row in alerts.get("alerts") or [] if row.get("mint")]))
        early = read_json(self.path("early_buys.json"), {})
        early["early_buys"] = build_early_buys(alerts, transactions, prices)
        early["requested_refresh_seconds"] = 1800
        early["warning"] = "A newly seen buy is not proof the wallet was among the first buyers. early_buyer_proven stays false without a launch time."
        stamp(early, now)
        stamp(wallets_doc, now)
        write_json(self.path("bubbles.json"), bubbles)
        write_json(self.path("early_buys.json"), early)
        write_json(self.path("wallets.json"), wallets_doc)

    def publish(self):
        script = ROOT / "publish_data.py"
        if not script.exists():
            return
        proc = subprocess.run(
            [sys.executable, str(script), str(self.out)],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=180,
        )
        if proc.returncode != 0:
            print("publish failed:", (proc.stderr or proc.stdout or "")[:400], file=sys.stderr, flush=True)
