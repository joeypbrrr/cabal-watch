"""Monitor cycle with a fake HTTP opener. No live network and no publish."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from monitor import COGE_MINT
from monitor.api import Client
from monitor.service import Monitor

ET = ZoneInfo("America/New_York")
MATCHED = "5wpeY1mo19QsfjFsrsp774gTJdApRtkexTspbYwSnFjK"
NEW = "NewMint11111111111111111111111111111111111"


class Response:
    def __init__(self, payload, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Opener:
    def __init__(self):
        self.calls = []
        self.pages = 0
        self.price = 100000
        self.quoted = "2026-11-07T17:00:02Z"

    def open(self, request, timeout=None):
        if request.get_method() != "GET":
            raise AssertionError(request.get_method())
        url = request.full_url
        self.calls.append(url)
        if "/trades/since.json" in url:
            self.pages += 1
            if self.pages == 1:
                return Response({
                    "as_of": "2026-11-07T17:00:00Z",
                    "more": True,
                    "next_since": 100,
                    "trades": [{
                        "wallet": MATCHED, "mint": NEW, "side": "buy", "slot": 5, "idx": 0,
                        "sol": 0.61, "at": "2026-11-07T12:00:00-05:00", "symbol": "Coach",
                    }],
                })
            return Response({"as_of": "2026-11-07T17:00:01Z", "more": False, "next_since": 101, "trades": []})
        if "/price.json" in url:
            return Response({"as_of": "2026-11-07T17:00:02Z", "prices": [{
                "mint": NEW, "market_cap_usd": self.price, "last_trade": self.quoted, "source": "live",
            }]})
        if "/holders/" in url:
            return Response({"as_of": "2026-11-07T17:00:03Z", "top": [{"address": MATCHED, "share": 0.008466}]})
        if "/launches/since.json" in url:
            return Response({"columns": ["mint", "created"], "launches": [], "more": False, "next_since": 50})
        raise AssertionError(url)


class RetryOpener:
    def __init__(self):
        self.calls = 0

    def open(self, request, timeout=None):
        self.calls += 1
        if self.calls == 1:
            return Response({}, status=429, headers={"Retry-After": "1"})
        return Response({"trades": [], "more": False, "next_since": 5, "as_of": "2026-11-07T17:00:00Z"})


class MonitorHttp(unittest.TestCase):
    def test_retry_after_429(self):
        slept = []
        client = Client(opener=RetryOpener(), sleep=slept.append, min_interval=0, clock=lambda: 0)
        body = client.trades([MATCHED], since=1)
        self.assertEqual(body["next_since"], 5)
        self.assertIn(1, slept)

    def test_cycle_flags_a_buy_and_waits_for_the_paper_checkpoint(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed"
            out = root / "out"
            seed.mkdir()
            (seed / "wallets.json").write_text(json.dumps({"schema_version": 1, "wallets": [{
                "address": MATCHED,
                "label": "matched",
                "role": "screenshot_matched_coge_holder",
                "watch": True,
                "reported_cluster_id": "coge-screenshot-1",
                "tokens": [],
                "cluster_membership_verified": False,
            }]}), encoding="utf-8")
            opener = Opener()
            clock = {"now": datetime(2026, 11, 7, 12, 0, tzinfo=ET)}
            published = []
            monitor = Monitor(
                out=out, seed_dir=seed, client=Client(opener=opener, sleep=lambda _s: None, min_interval=0, clock=lambda: 0),
                now=lambda: clock["now"], publish=False, once=True, slow_s=1800,
            )
            monitor.publish = lambda: published.append("no")
            self.assertEqual(monitor.run(), 0)
            alerts = json.loads((out / "alerts.json").read_text())
            self.assertEqual(alerts["alerts"][0]["flag"], "possible_next_play")
            self.assertEqual(alerts["alerts"][0]["symbol"], "Coach")
            self.assertIsNone(json.loads((out / "transactions.json").read_text())["transactions"][0]["signature"])
            paper = json.loads((out / "paper.json").read_text())
            self.assertEqual(paper["paper"][0]["checkpoints"]["15m"]["status"], "pending")
            bubbles = json.loads((out / "bubbles.json").read_text())
            self.assertEqual(bubbles["requested_refresh_seconds"], 1800)
            self.assertIsNone(bubbles["tokens"][0]["holders"][0]["cluster_id"])
            self.assertEqual(published, [])
            trade_calls = [url for url in opener.calls if "/trades/since.json" in url]
            self.assertEqual(len(trade_calls), 2)
            self.assertIn("since=100", trade_calls[1])
            clock["now"] = clock["now"] + timedelta(minutes=16)
            opener.price = 125000
            opener.quoted = "2026-11-07T17:20:00Z"
            monitor.once = True
            monitor.cycle()
            paper = json.loads((out / "paper.json").read_text())
            self.assertEqual(paper["paper"][0]["checkpoints"]["15m"]["status"], "observed")
            self.assertAlmostEqual(paper["paper"][0]["checkpoints"]["15m"]["pnl_pct"], 25.0)
            self.assertTrue((out / "monitor_state.json").exists())
            self.assertNotIn("monitor_state.json", [path.name for path in out.glob("*.json") if path.name in {
                "wallets.json", "funding.json", "transactions.json", "alerts.json", "paper.json", "bubbles.json", "early_buys.json",
            }])


if __name__ == "__main__":
    unittest.main()
