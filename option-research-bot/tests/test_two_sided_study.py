import unittest
from datetime import date

from option_lab.spread_study import Leg
from option_lab.two_sided_study import replay


class TwoSidedAccountingTests(unittest.TestCase):
    def test_call_and_put_use_next_day_ask_and_later_bid_with_fx(self):
        days = [date(2025, 1, d) for d in (6, 7, 8, 9, 10, 13, 14)]
        expiry = date(2025, 2, 14)
        quotes = {}
        for i, day in enumerate(days):
            call_bid, put_bid = (.8, .5) if i == 6 else (.5, .4)
            quotes[day] = {(expiry, 110., "call"): Leg(call_bid, max(.6, call_bid), 100, 5, 5),
                           (expiry, 90., "put"): Leg(put_bid, max(.5, put_bid), 100, 5, 5)}
        result = replay({d: 100. for d in days}, quotes, days[0], days[-1])
        self.assertEqual(result["closed_trades"], 1)
        self.assertEqual(result["trades"][0]["entry"], "2025-01-07")
        self.assertEqual(result["trades"][0]["exit"], "2025-01-14")
        self.assertEqual(result["trades"][0]["cost"], 111.65)
        self.assertEqual(result["trades"][0]["proceeds"], 128.05)
        self.assertEqual(result["final_marked_equity"], 216.4)
        self.assertTrue(result["valid_quote_replay"])


if __name__ == "__main__":
    unittest.main()
