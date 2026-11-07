"""The committed snapshot matches the contract and is not example data."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("wallets", "funding", "transactions", "alerts", "paper", "bubbles", "early_buys")
COGE = "8UQdy5sHMVWUWSHeA5B3ZuuAVNumjSLPXdf19MXcpump"
DEMOCAT = "9Y1F6dZ6HpjZDYZdYuUGwMbkUiPsyU7WPTqTQU4Tpump"


class Contract(unittest.TestCase):
    def test_snapshot_is_honest_and_samples_are_marked(self):
        for name in FILES:
            live = json.loads((ROOT / "data" / f"{name}.json").read_text())
            sample = json.loads((ROOT / "data" / "sample" / f"{name}.json").read_text())
            self.assertEqual(live["schema_version"], 1)
            self.assertEqual(live["timezone"], "America/New_York")
            self.assertEqual(live["status"], "snapshot_only_monitor_not_running")
            self.assertNotEqual(live.get("example"), True)
            self.assertTrue(sample["example"])
            self.assertEqual(sample["status"], "example")
            self.assertIn("FICTIONAL", sample["note"])
        alerts = json.loads((ROOT / "data" / "alerts.json").read_text())
        self.assertEqual(alerts["alerts"], [])
        self.assertEqual(alerts["rule"]["flag"], "possible_next_play")
        self.assertEqual(alerts["rule"]["excluded_mints"], [COGE, DEMOCAT])
        self.assertIn("unresolved", alerts["rule"]["coach_mint_status"])
        paper = json.loads((ROOT / "data" / "paper.json").read_text())
        early = json.loads((ROOT / "data" / "early_buys.json").read_text())
        trades = json.loads((ROOT / "data" / "transactions.json").read_text())
        self.assertEqual(paper["paper"], [])
        self.assertEqual(early["early_buys"], [])
        self.assertEqual(trades["transactions"], [])
        self.assertEqual(early["requested_refresh_seconds"], 1800)
        bubbles = json.loads((ROOT / "data" / "bubbles.json").read_text())
        self.assertEqual(bubbles["requested_refresh_seconds"], 1800)
        funding = json.loads((ROOT / "data" / "funding.json").read_text())
        self.assertTrue(all(row["same_owner_proven"] is False for row in funding["common_funders"]))
        wallets = json.loads((ROOT / "data" / "wallets.json").read_text())
        matched = [row for row in wallets["wallets"] if row.get("reported_cluster_id") == "coge-screenshot-1"]
        self.assertEqual(len(matched), 5)
        self.assertTrue(all(row["cluster_membership_verified"] is False for row in wallets["wallets"]))
        exchanges = [row for row in wallets["wallets"] if row["role"] == "exchange_or_service"]
        self.assertTrue(exchanges)
        self.assertTrue(all(row["watch"] is False for row in exchanges))
        text = (ROOT / "SPEC.md").read_text()
        self.assertIn("44.65%", text)
        self.assertIn("30 minutes", text)
        self.assertIn("possible next cabal play", text.lower())
        readme = (ROOT / "README.md").read_text()
        self.assertIn("SPEC.md", readme)
        self.assertIn("30 minutes", readme)
        page = (ROOT / "index.html").read_text() + (ROOT / "js" / "dashboard.js").read_text()
        self.assertIn("possible next cabal play", page.lower())
        self.assertIn("60000", page)
        self.assertIn("30 minutes", page)


if __name__ == "__main__":
    unittest.main()
