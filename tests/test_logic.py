"""Rules for alerts, paper marks, and bubbles. No network."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from monitor import COGE_MINT, DEMOCAT_MINT
from monitor.logic import (
    apply_trades,
    build_bubble_token,
    build_early_buys,
    et_iso,
    excluded_mints,
    normalize_trade,
    observe_checkpoints,
    pct_from_share,
    pnl_pct,
    same_owner_proven,
    update_known_holdings,
)

ET = ZoneInfo("America/New_York")
MATCHED = "Match111111111111111111111111111111111111"
OTHER = "Other111111111111111111111111111111111111"
NEW = "NewMint11111111111111111111111111111111111"
EXCHANGE = "Gate1111111111111111111111111111111111111"


def wallets():
    return {"wallets": [
        {"address": MATCHED, "role": "screenshot_matched_coge_holder", "reported_cluster_id": "coge-screenshot-1", "watch": True, "tokens": []},
        {"address": OTHER, "role": "deployer", "watch": True, "tokens": []},
        {"address": EXCHANGE, "role": "exchange_or_service", "watch": False, "tokens": []},
    ]}


def alerts():
    return {"alerts": [], "rule": {
        "flag": "possible_next_play",
        "excluded_mints": [COGE_MINT, DEMOCAT_MINT],
        "coach_mint_status": "unresolved",
    }}


def trade(wallet, mint, side="buy", slot=10, idx=1, sol=0.4, symbol=None, at="2026-11-07T12:00:00-05:00"):
    raw = {"wallet": wallet, "mint": mint, "side": side, "slot": slot, "idx": idx, "sol": sol, "at": at, "ts": 1}
    if symbol:
        raw["symbol"] = symbol
    return raw


class Rules(unittest.TestCase):
    def test_share_is_converted_to_percent(self):
        self.assertEqual(pct_from_share(0.008971), 0.8971)
        self.assertIsNone(pct_from_share(None))

    def test_signature_stays_null_and_identity_dedupes(self):
        row = normalize_trade(trade(MATCHED, NEW))
        self.assertIsNone(row["signature"])
        self.assertEqual(row["idx"], 1)
        transactions = {"transactions": []}
        alert_doc = alerts()
        paper = {"paper": []}
        apply_trades(transactions, alert_doc, paper, wallets(), [trade(MATCHED, NEW), trade(MATCHED, NEW)])
        self.assertEqual(len(transactions["transactions"]), 1)
        self.assertIsNone(transactions["transactions"][0]["signature"])

    def test_unknown_buy_by_matched_wallet_is_a_possible_next_play(self):
        transactions = {"transactions": []}
        alert_doc = alerts()
        paper = {"paper": []}
        apply_trades(
            transactions, alert_doc, paper, wallets(),
            [trade(MATCHED, NEW, symbol="Coach", sol=0.62)],
            prices_by_mint={NEW: {"market_cap_usd": 210000}},
        )
        self.assertEqual(len(alert_doc["alerts"]), 1)
        alert = alert_doc["alerts"][0]
        self.assertEqual(alert["flag"], "possible_next_play")
        self.assertEqual(alert["symbol"], "Coach")
        self.assertEqual(alert["mcap_at_detection"], 210000)
        self.assertEqual(alert["cluster_wallets"], [MATCHED])
        self.assertEqual(paper["paper"][0]["entry_mcap"], 210000)
        self.assertEqual(paper["paper"][0]["checkpoints"]["15m"]["status"], "pending")
        self.assertIsNone(paper["paper"][0]["checkpoints"]["15m"]["pnl_pct"])

    def test_known_mints_sells_and_other_wallets_do_not_flag(self):
        transactions = {"transactions": []}
        alert_doc = alerts()
        paper = {"paper": []}
        apply_trades(transactions, alert_doc, paper, wallets(), [
            trade(MATCHED, COGE_MINT),
            trade(MATCHED, DEMOCAT_MINT),
            trade(MATCHED, NEW, side="sell"),
            trade(OTHER, NEW, slot=11),
        ])
        self.assertEqual(alert_doc["alerts"], [])
        self.assertEqual(paper["paper"], [])
        self.assertEqual(len(transactions["transactions"]), 4)

    def test_missing_price_stays_null(self):
        transactions = {"transactions": []}
        alert_doc = alerts()
        paper = {"paper": []}
        apply_trades(transactions, alert_doc, paper, wallets(), [trade(MATCHED, NEW)], prices_by_mint={NEW: {"why": "no trade"}})
        self.assertIsNone(alert_doc["alerts"][0]["mcap_at_detection"])
        self.assertIsNone(paper["paper"][0]["entry_mcap"])

    def test_checkpoint_waits_until_due_and_does_not_invent_zero(self):
        transactions = {"transactions": []}
        alert_doc = alerts()
        paper = {"paper": []}
        apply_trades(transactions, alert_doc, paper, wallets(), [trade(MATCHED, NEW)], prices_by_mint={NEW: {"market_cap_usd": 100}})
        start = datetime(2026, 11, 7, 12, 0, tzinfo=ET)
        self.assertFalse(observe_checkpoints(paper, start, {NEW: {"market_cap_usd": 150, "as_of": et_iso(start), "last_trade": et_iso(start)}}))
        self.assertEqual(paper["paper"][0]["checkpoints"]["15m"]["status"], "pending")
        later = start + timedelta(minutes=16)
        quote = {"market_cap_usd": 150, "as_of": et_iso(later), "last_trade": et_iso(later), "source": "live"}
        self.assertTrue(observe_checkpoints(paper, later, {NEW: quote}))
        checkpoint = paper["paper"][0]["checkpoints"]["15m"]
        self.assertEqual(checkpoint["status"], "observed")
        self.assertEqual(checkpoint["pnl_pct"], pnl_pct(100, 150))
        self.assertGreater(checkpoint["lateness_s"], 0)
        self.assertEqual(paper["paper"][0]["checkpoints"]["1h"]["status"], "pending")
        unavailable = {"paper": [paper["paper"][0]]}
        unavailable["paper"][0]["checkpoints"]["1h"]["status"] = "pending"
        hour = start + timedelta(minutes=61)
        observe_checkpoints(unavailable, hour, {NEW: {"why": "thin"}})
        self.assertEqual(unavailable["paper"][0]["checkpoints"]["1h"]["status"], "unavailable")
        self.assertIsNone(unavailable["paper"][0]["checkpoints"]["1h"]["pnl_pct"])

    def test_exchange_link_is_not_an_owner_cluster(self):
        self.assertFalse(same_owner_proven({"funder": EXCHANGE, "same_owner_proven": True, "stop_reason": "busy"}, {EXCHANGE}))
        token = build_bubble_token(COGE_MINT, "COGE", {
            "as_of": "2026-11-07T17:00:00Z",
            "top": [{"address": MATCHED, "share": 0.008466}, {"address": "Stranger1111111111111111111111111111111", "share": 0.001}],
        }, wallets(), {"edges": [{
            "funder": EXCHANGE, "wallet": MATCHED, "amount_sol": 0.2, "time": "2026-11-07T12:00:00-05:00",
            "signature": "sig", "same_owner_proven": True, "stop_reason": "busy",
        }]})
        self.assertTrue(all(holder["cluster_id"] is None for holder in token["holders"]))
        self.assertEqual(token["holders"][0]["reported_cluster_id"], "coge-screenshot-1")
        self.assertIsNone(token["holders"][1]["reported_cluster_id"])
        self.assertFalse(token["links"][0]["same_owner_proven"])
        self.assertFalse(token["cluster_verified"])
        before = len(wallets()["wallets"])
        doc = wallets()
        update_known_holdings(doc, COGE_MINT, "COGE", token["holders"], token["as_of"])
        self.assertEqual(len(doc["wallets"]), before)
        self.assertFalse(any(wallet.get("cluster_membership_verified") for wallet in doc["wallets"]))

    def test_early_buy_does_not_claim_the_wallet_was_early(self):
        transactions = {"transactions": []}
        alert_doc = alerts()
        paper = {"paper": []}
        apply_trades(transactions, alert_doc, paper, wallets(), [trade(MATCHED, NEW, sol=1.25)])
        rows = build_early_buys(alert_doc, transactions, {NEW: {"market_cap_usd": 300000}})
        self.assertEqual(rows[0]["total_sol"], 1.25)
        self.assertEqual(rows[0]["current_mcap"], 300000)
        self.assertFalse(rows[0]["early_buyer_proven"])

    def test_coach_name_is_not_added_to_the_excluded_list(self):
        self.assertEqual(excluded_mints(alerts()), {COGE_MINT, DEMOCAT_MINT})


if __name__ == "__main__":
    unittest.main()
