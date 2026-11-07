"""Pure rules for alerts, paper marks, and bubble files.

Unknown numbers stay null. Exchange wallets are never treated as the cabal funder.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from monitor import COGE_MINT, DEMOCAT_MINT

ET = ZoneInfo("America/New_York")
SCREENSHOT_CLUSTER = "coge-screenshot-1"
EXCHANGE_ROLE = "exchange_or_service"
BUSY_ROLE = "unlabeled_busy_funder"
HORIZONS = (("15m", 15), ("1h", 60), ("6h", 360))
TRADE_SOURCE = "https://pumpdata.fun/trades/since.json"
DEFAULT_EXCLUDED = (COGE_MINT, DEMOCAT_MINT)


def as_et(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(ET)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc).astimezone(ET)
    text = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ET)


def et_iso(value):
    dt = as_et(value)
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds")


def stamp(doc, now, status="monitor_running"):
    doc["schema_version"] = 1
    doc["updated_at"] = et_iso(now)
    doc["timezone"] = "America/New_York"
    doc["status"] = status
    doc.pop("example", None)
    return doc


def screenshot_addresses(wallets_doc):
    found = set()
    for wallet in wallets_doc.get("wallets") or []:
        if wallet.get("role") == "screenshot_matched_coge_holder" or wallet.get("reported_cluster_id") == SCREENSHOT_CLUSTER:
            if wallet.get("address"):
                found.add(wallet["address"])
    return found


def exchange_addresses(wallets_doc):
    return {
        wallet["address"]
        for wallet in wallets_doc.get("wallets") or []
        if wallet.get("address") and wallet.get("role") in {EXCHANGE_ROLE, BUSY_ROLE}
    }


def excluded_mints(alerts_doc):
    """Known cabal mints. Coach is not added from a name; only listed mints count."""
    listed = [mint for mint in ((alerts_doc.get("rule") or {}).get("excluded_mints") or []) if mint]
    return set(listed or DEFAULT_EXCLUDED)


def is_buy(side):
    text = str(side or "").lower()
    return text == "buy" or text.startswith("buy")


def normalize_trade(raw):
    """Return a transaction row, or None when the API row has no stable identity."""
    if not isinstance(raw, dict):
        return None
    wallet = raw.get("wallet") or raw.get("address")
    mint = raw.get("mint")
    side = str(raw.get("side") or "").lower()
    slot = raw.get("slot")
    idx = raw.get("idx")
    when = raw.get("at") if raw.get("at") is not None else raw.get("ts")
    if not wallet or not mint or slot is None or idx is None or not side or when is None:
        return None
    sol = raw.get("sol")
    if sol is None:
        sol = raw.get("amount_sol")
    if isinstance(sol, bool) or not isinstance(sol, (int, float)):
        sol = None
    symbol = raw.get("symbol")
    if symbol is not None:
        symbol = str(symbol).strip() or None
    return {
        "address": wallet,
        "signature": None,
        "slot": slot,
        "idx": idx,
        "time": et_iso(when),
        "type": "trade",
        "mint": mint,
        "symbol": symbol,
        "side": "buy" if is_buy(side) else side,
        "amount_sol": sol,
        "source": TRADE_SOURCE,
    }


def trade_key(row):
    return (row.get("address"), row.get("slot"), row.get("idx"), row.get("mint"), row.get("side"))


def pnl_pct(entry_mcap, mcap):
    if isinstance(entry_mcap, bool) or isinstance(mcap, bool):
        return None
    if not isinstance(entry_mcap, (int, float)) or not isinstance(mcap, (int, float)):
        return None
    if entry_mcap <= 0:
        return None
    return (mcap / entry_mcap - 1.0) * 100.0


def mcap_from_price(price_row):
    if not isinstance(price_row, dict):
        return None
    value = price_row.get("market_cap_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def pct_from_share(share):
    """pumpdata `share` is a fraction of supply. Percent fields are 0–100."""
    if isinstance(share, bool) or not isinstance(share, (int, float)) or share < 0:
        return None
    value = share * 100 if share <= 1 else share
    return round(value, 4)


def _launch_extra(detected_iso, launch):
    if not isinstance(launch, dict):
        return {}
    extra = {}
    created = launch.get("created")
    if created is not None:
        created_iso = et_iso(created)
        if created_iso:
            extra["created_at"] = created_iso
            start = as_et(created_iso)
            seen = as_et(detected_iso)
            if start and seen:
                extra["token_age_s"] = int((seen - start).total_seconds())
    if launch.get("slot") is not None:
        extra["launch_slot"] = launch.get("slot")
    return extra


def _blank_paper(alert):
    entry = as_et(alert["detected_at"])
    checkpoints = {}
    for key, minutes in HORIZONS:
        checkpoints[key] = {
            "due_at": (entry + timedelta(minutes=minutes)).isoformat(timespec="seconds"),
            "observed_at": None,
            "mcap": None,
            "pnl_pct": None,
            "status": "pending",
        }
    return {
        "alert_id": alert["id"],
        "mint": alert["mint"],
        "entry_at": alert["detected_at"],
        "entry_mcap": alert.get("mcap_at_detection"),
        "checkpoints": checkpoints,
    }


def apply_trades(transactions_doc, alerts_doc, paper_doc, wallets_doc, raw_trades, prices_by_mint=None, launches_by_mint=None):
    """Fold newly observed trades into the three documents. Returns how many were new."""
    prices_by_mint = prices_by_mint or {}
    launches_by_mint = launches_by_mint or {}
    screens = screenshot_addresses(wallets_doc)
    excluded = excluded_mints(alerts_doc)
    rows = transactions_doc.setdefault("transactions", [])
    seen = {trade_key(row) for row in rows}
    alerts = alerts_doc.setdefault("alerts", [])
    by_mint = {alert.get("mint"): alert for alert in alerts}
    paper_rows = paper_doc.setdefault("paper", [])
    paper_ids = {row.get("alert_id") for row in paper_rows}
    added = 0
    for raw in raw_trades or []:
        row = normalize_trade(raw)
        if row is None:
            continue
        key = trade_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        added += 1
        if row["address"] not in screens or row["side"] != "buy" or row["mint"] in excluded:
            continue
        alert = by_mint.get(row["mint"])
        if alert is None:
            price = prices_by_mint.get(row["mint"])
            alert = {
                "id": f"possible_next_play:{row['mint']}",
                "flag": "possible_next_play",
                "mint": row["mint"],
                "symbol": row.get("symbol"),
                "detected_at": row["time"],
                "mcap_at_detection": mcap_from_price(price),
                "cluster_wallet_count": 0,
                "cluster_wallets": [],
                "source": TRADE_SOURCE,
            }
            alert.update(_launch_extra(row["time"], launches_by_mint.get(row["mint"])))
            alerts.append(alert)
            by_mint[row["mint"]] = alert
        elif alert.get("symbol") is None and row.get("symbol"):
            alert["symbol"] = row["symbol"]
        wallets = alert.setdefault("cluster_wallets", [])
        if row["address"] not in wallets:
            wallets.append(row["address"])
        alert["cluster_wallet_count"] = len(wallets)
        if alert["id"] not in paper_ids:
            paper_rows.append(_blank_paper(alert))
            paper_ids.add(alert["id"])
    if len(rows) > 2000:
        del rows[:-2000]
    return added


def observe_checkpoints(paper_doc, now, prices_by_mint):
    """Fill checkpoints that are due. A quote taken early is ignored."""
    now_et = as_et(now)
    changed = False
    for row in paper_doc.get("paper") or []:
        price = (prices_by_mint or {}).get(row.get("mint"))
        for key, _minutes in HORIZONS:
            checkpoint = (row.get("checkpoints") or {}).get(key)
            if not checkpoint or checkpoint.get("status") not in (None, "pending"):
                continue
            due = as_et(checkpoint.get("due_at"))
            if due is None or now_et is None or now_et < due:
                continue
            if not isinstance(price, dict):
                continue
            mcap = mcap_from_price(price)
            observed_src = price.get("last_trade") or price.get("as_of")
            quote_at = as_et(observed_src)
            if mcap is not None and quote_at is not None and quote_at < due:
                continue
            changed = True
            observed = et_iso(observed_src or now)
            checkpoint["observed_at"] = observed
            if mcap is None:
                checkpoint["status"] = "unavailable"
                checkpoint["mcap"] = None
                checkpoint["pnl_pct"] = None
            else:
                checkpoint["status"] = "observed"
                checkpoint["mcap"] = mcap
                checkpoint["pnl_pct"] = pnl_pct(row.get("entry_mcap"), mcap)
            if observed and checkpoint.get("due_at"):
                late = as_et(observed) - as_et(checkpoint["due_at"])
                checkpoint["lateness_s"] = int(late.total_seconds())
            if isinstance(price, dict) and price.get("source"):
                checkpoint["source"] = price.get("source")
            if isinstance(price, dict) and price.get("last_trade") and price.get("as_of"):
                age = as_et(price["as_of"]) - as_et(price["last_trade"])
                checkpoint["source_age_s"] = int(age.total_seconds())
    return changed


def due_mints(paper_doc, now):
    now_et = as_et(now)
    found = []
    for row in paper_doc.get("paper") or []:
        mint = row.get("mint")
        if not mint:
            continue
        for key, _minutes in HORIZONS:
            checkpoint = (row.get("checkpoints") or {}).get(key) or {}
            if checkpoint.get("status") not in (None, "pending"):
                continue
            due = as_et(checkpoint.get("due_at"))
            if due is not None and now_et is not None and now_et >= due:
                found.append(mint)
                break
    return list(dict.fromkeys(found))


def same_owner_proven(edge, exchanges):
    """A busy or exchange source is not proof of a common owner."""
    funder = edge.get("funder")
    if funder in exchanges or edge.get("stop_reason") == "busy":
        return False
    if edge.get("funder_role") in {EXCHANGE_ROLE, BUSY_ROLE}:
        return False
    return bool(edge.get("same_owner_proven"))


def build_bubble_token(mint, symbol, holders_body, wallets_doc, funding_doc):
    screens = screenshot_addresses(wallets_doc)
    exchanges = exchange_addresses(wallets_doc)
    holders = []
    for row in (holders_body or {}).get("top") or []:
        address = row.get("address")
        if not address:
            continue
        holders.append({
            "address": address,
            "pct_supply": pct_from_share(row.get("share")),
            "cluster_id": None,
            "reported_cluster_id": SCREENSHOT_CLUSTER if address in screens else None,
        })
    holding = {holder["address"] for holder in holders}
    links = []
    for edge in (funding_doc or {}).get("edges") or []:
        if edge.get("wallet") not in holding:
            continue
        links.append({
            "source": edge.get("funder"),
            "target": edge.get("wallet"),
            "kind": "first_inbound_SOL",
            "amount_sol": edge.get("amount_sol"),
            "time": edge.get("time"),
            "signature": edge.get("signature"),
            "same_owner_proven": same_owner_proven(edge, exchanges),
        })
    return {
        "mint": mint,
        "symbol": symbol,
        "as_of": et_iso((holders_body or {}).get("as_of")),
        "holders": holders,
        "links": links,
        "source": f"https://pumpdata.fun/holders/{mint}.json",
        "cluster_verified": False,
    }


def update_known_holdings(wallets_doc, mint, symbol, holders, as_of):
    """Refresh percent held for wallets already on file. Never adds a wallet."""
    by_address = {holder["address"]: holder for holder in holders}
    for wallet in wallets_doc.get("wallets") or []:
        holder = by_address.get(wallet.get("address"))
        if holder is None or holder.get("pct_supply") is None:
            continue
        tokens = wallet.setdefault("tokens", [])
        match = next((token for token in tokens if token.get("mint") == mint), None)
        if match is None:
            tokens.append({
                "mint": mint,
                "symbol": symbol,
                "pct_held": holder["pct_supply"],
                "as_of": as_of,
            })
        else:
            match["pct_held"] = holder["pct_supply"]
            match["as_of"] = as_of
            if symbol and not match.get("symbol"):
                match["symbol"] = symbol
        wallet["cluster_membership_verified"] = False


def build_early_buys(alerts_doc, transactions_doc, prices_by_mint):
    rows = []
    trades = transactions_doc.get("transactions") or []
    for alert in alerts_doc.get("alerts") or []:
        if alert.get("flag") != "possible_next_play" or not alert.get("mint"):
            continue
        members = set(alert.get("cluster_wallets") or [])
        total = None
        for trade in trades:
            if trade.get("mint") != alert["mint"] or trade.get("side") != "buy":
                continue
            if members and trade.get("address") not in members:
                continue
            amount = trade.get("amount_sol")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                total = (total or 0) + amount
        price = (prices_by_mint or {}).get(alert["mint"])
        rows.append({
            "mint": alert["mint"],
            "symbol": alert.get("symbol"),
            "first_buy_at": alert.get("detected_at"),
            "mcap_at_detection": alert.get("mcap_at_detection"),
            "cluster_wallet_count": alert.get("cluster_wallet_count"),
            "total_sol": None if total is None else round(total, 6),
            "current_mcap": mcap_from_price(price),
            "created_at": alert.get("created_at"),
            "token_age_s": alert.get("token_age_s"),
            "launch_slot": alert.get("launch_slot"),
            "early_buyer_proven": False,
        })
    return rows
