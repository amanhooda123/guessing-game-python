import unittest
from datetime import date

from option_lab.factor_replay import modeled_greeks
from option_lab.factors import evaluate, historical_volatility
from option_lab.model import Quote


class FactorTests(unittest.TestCase):
    def test_realized_volatility_requires_21_prior_closes(self):
        self.assertIsNone(historical_volatility([100.] * 20))
        self.assertEqual(historical_volatility([100.] * 21), 0.)

    def test_missing_greeks_and_expensive_contract_fail_closed(self):
        row = {"underlying_symbol": "ABC", "quote_date": "2025-06-02", "expiration": "2025-07-18",
               "strike": "105", "option_type": "C", "bid_1545": "1.15", "ask_1545": "1.20",
               "bid_size_1545": "3", "ask_size_1545": "3", "trade_volume": "40",
               "implied_volatility_1545": "0.25", "delta_1545": "0.30",
               "gamma_1545": "0.02", "theta_1545": "-0.02", "vega_1545": "0.10"}
        candidate, reason = evaluate(row, 100., .25)
        self.assertEqual(reason, "eligible")
        self.assertEqual(candidate["estimated_cost_usd_equivalent"], 121.8)
        self.assertEqual(evaluate(row, 100., .25, budget=30.)[1], "budget")
        self.assertEqual(evaluate({**row, "delta_1545": "0"}, 100., .25)[1], "greeks")
        self.assertEqual(evaluate(row, 100., None)[1], "volatility_history")
        put = {**row, "option_type": "P", "delta_1545": "-0.30"}
        self.assertEqual(evaluate(put, 100., .25)[1], "eligible")

    def test_modeled_greeks_from_real_bid_ask_shape(self):
        q = Quote(date(2025, 6, 2), "ABC", date(2025, 7, 18), 105.,
                  "call", 1.15, 1.20, 40, 3, 3)
        model = modeled_greeks(q, 100.)
        self.assertIsNotNone(model)
        self.assertGreater(model["delta_1545"], 0)
        self.assertGreater(model["gamma_1545"], 0)
        self.assertLess(model["theta_1545"], 0)


if __name__ == "__main__":
    unittest.main()
