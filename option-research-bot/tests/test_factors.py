import unittest
from datetime import date

from option_lab.factor_replay import modeled_greeks
from option_lab.factors import evaluate, historical_volatility
from option_lab.broad_study import _spot_from_parity, _signals
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

    def test_stock_proxy_from_two_call_put_pairs_and_prior_only_signal(self):
        rows = []
        for strike, call, put in ((99., 3., 2.), (100., 2.5, 2.5)):
            for right, price, delta in (("Call", call, .5), ("Put", put, -.5)):
                rows.append({"act_symbol": "ABC", "expiration": "2025-08-01",
                             "strike": strike, "call_put": right, "bid": price - .02,
                             "ask": price + .02, "delta": delta})
        spot = _spot_from_parity(rows, date(2025, 6, 2))
        self.assertEqual(spot["ABC"], 100.)
        days = [(date.fromordinal(date(2025, 1, 1).toordinal() + i), {"ABC": 100 + i})
                for i in range(61)]
        signals = _signals(days)
        self.assertNotIn(("ABC", days[59][0]), signals)
        self.assertTrue(signals["ABC", days[60][0]][2])


if __name__ == "__main__":
    unittest.main()
