import unittest
from datetime import date

from option_lab.universe import scan


class UniverseScreenTests(unittest.TestCase):
    def test_multiple_companies_stale_snapshot_never_emits_order(self):
        day = "2025-06-02"
        snapshot = {"date": day, "snapshots": [
            {"symbol": "ABC", "date": day, "truncated": False, "errors": [],
             "volatility": {"hv_current": ".4", "iv_current": ".2"},
             "options": [
                 {"expiration": "2025-07-18", "strike": "110", "call_put": "Call",
                  "bid": ".40", "ask": ".45", "delta": ".20"},
                 {"expiration": "2025-07-18", "strike": "90", "call_put": "Put",
                  "bid": ".30", "ask": ".35", "delta": "-.20"}]},
            {"symbol": "XYZ", "date": day, "truncated": False, "errors": ["timeout"],
             "volatility": None, "options": []}]}
        result = scan(snapshot, today=date(2026, 10, 9))
        self.assertEqual(result["action"], "NO TRADE")
        self.assertEqual(result["historical_research_candidates"][0]["symbol"], "ABC")
        self.assertEqual(result["historical_research_candidates"][0]["estimated_ask_cost_usd_equivalent"], 81.2)
        self.assertEqual(result["coverage"][1]["errors"], ["timeout"])


if __name__ == "__main__":
    unittest.main()
