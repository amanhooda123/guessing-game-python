import unittest
from datetime import date, timedelta

from option_lab.spread_study import Leg, replay


class SpreadAccountingTests(unittest.TestCase):
    def test_credit_reserved_and_released_with_next_day_debit(self):
        monday = date(2024, 1, 8)
        spots = {monday - timedelta(days=i): 100. for i in range(1, 201)}
        spots[monday] = 101.
        expiry = date(2024, 2, 16)
        quotes = {}
        for i in range(4):
            day = monday + timedelta(days=i)
            spots[day] = 101.
            short_ask = [.45, .45, .25, .22][i]
            long_bid = [.10, .10, .13, .12][i]
            quotes[day] = {(expiry, 99.): Leg([.40, .40, .20, .18][i], short_ask, 100, 1, 1),
                           (expiry, 98.): Leg(long_bid, .15, 100, 1, 1)}
        result = replay(spots, quotes, monday, monday + timedelta(days=3))
        self.assertEqual(result["closed_trades"], 1)
        self.assertEqual(result["trades"][0]["pnl"], 15.)
        self.assertEqual(result["final_equity"], 215.)
        self.assertTrue(result["valid_quote_replay"])


if __name__ == "__main__":
    unittest.main()
