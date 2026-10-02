import unittest
from datetime import date, timedelta

from option_lab.backtest import Config, choose, run, trend_on_prior_day
from option_lab.model import Quote


class ReplayTests(unittest.TestCase):
    def test_signal_never_uses_future_stock_closes(self):
        first = date(2025, 1, 1)
        prices = {("RDDT", first + timedelta(days=i)): 100 + i * 0.1 for i in range(61)}
        day = first + timedelta(days=60)
        before = trend_on_prior_day("RDDT", day, prices)
        prices[("RDDT", day + timedelta(days=1))] = 0.01
        self.assertEqual(before, trend_on_prior_day("RDDT", day, prices))

    def test_cash_uses_ask_entry_bid_exit_and_fx_both_sides(self):
        first = date(2025, 1, 1)
        closes = {("RDDT", first + timedelta(days=i)): 100 + i for i in range(70)}
        quotes = []
        for i in range(60, 65):
            day = first + timedelta(days=i)
            bid, ask = [(0.95, 1.00), (0.95, 1.00), (1.50, 1.55),
                        (1.50, 1.55), (1.45, 1.50)][i - 60]
            quotes.append(Quote(day, "RDDT", day + timedelta(days=70 - (i - 60)),
                                165, "call", bid, ask, 100, 1, 1))
        report = run(quotes, closes, Config(capital=200, min_dte=45))
        self.assertEqual(len(report["closed_trades"]), 1)
        trade = report["closed_trades"][0]
        self.assertEqual(trade["entry"], (first + timedelta(days=61)).isoformat())
        self.assertEqual(trade["exit"], (first + timedelta(days=63)).isoformat())
        self.assertEqual(trade["buy_ask"], 1.0)
        self.assertEqual(trade["sell_bid"], 1.5)
        self.assertEqual(trade["cost"], 101.5)
        self.assertEqual(trade["proceeds"], 147.75)
        self.assertEqual(trade["pnl"], 46.25)

    def test_rejects_wide_spread_and_oversized_contract(self):
        day = date(2025, 4, 1)
        wide = Quote(day, "RDDT", day + timedelta(days=70), 103, "call", .4, 1, 100, 1, 1)
        expensive = Quote(day, "RDDT", day + timedelta(days=70), 103, "call", 2, 2.1, 100, 1, 1)
        self.assertIsNone(choose([wide, expensive], {("RDDT", day): 100}, Config()))


if __name__ == "__main__":
    unittest.main()
