import math
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from option_lab.recent_study import elapsed_volatility, features, summarize, valid_quote


class RecentStudyTests(unittest.TestCase):
    def test_elapsed_gaps_change_variance_scale(self):
        start = date(2023, 1, 1)
        prices = [100 * math.exp(.01 * (i % 2)) for i in range(21)]
        daily = [(start + timedelta(days=i), p) for i, p in enumerate(prices)]
        spaced = [(start + timedelta(days=4*i), p) for i, p in enumerate(prices)]
        self.assertAlmostEqual(elapsed_volatility(daily), 2 * elapsed_volatility(spaced))
        self.assertIsNone(elapsed_volatility(daily[:20]))

    def test_features_do_not_consume_future_prices_and_reset_on_jump(self):
        start = date(2023, 1, 1)
        daily = [(start + timedelta(days=i), {'ABC': 100 + i}) for i in range(61)]
        original = features(daily)
        changed = features(daily + [(start + timedelta(days=61), {'ABC': 10000})])
        self.assertEqual(original, changed)
        self.assertIn(('ABC', start + timedelta(days=60)), original)

    def test_missing_exits_remain_in_entered_and_stress_denominator(self):
        records = [{'status': 'matched', 'keys': [('ABC',)], 'cost': 100,
                    'proceeds': 150, 'return_fraction': .5},
                   {'status': 'missing_exit', 'keys': [('DEF',)], 'cost': 200},
                   {'status': 'missing_entry', 'keys': [('GHI',)]}]
        d = summarize(records)
        self.assertEqual((d['selected'], d['entered'], d['matched']), (3, 2, 1))
        self.assertEqual(d['mean_return'], .5)
        self.assertEqual(d['mean_full_loss_stress'], -.25)
        self.assertAlmostEqual(d['match_fraction'], 1/3)
        self.assertEqual(d['matched_total_pnl'], 50)

    def test_invalid_executable_quote_rejected(self):
        for bid, ask in [(0, 1), (2, 1), (float('nan'), 1), (1, float('inf'))]:
            self.assertFalse(valid_quote({'bid': bid, 'ask': ask}))
        self.assertTrue(valid_quote({'bid': 1, 'ask': 1.1}))

    def test_next_snapshot_execution_both_sides_and_spread_risk(self):
        from option_lab.recent_study import run
        short = ('ABC', '2024-03-15', 100., 'Put')
        long = ('ABC', '2024-03-15', 95., 'Put')
        def quote(key, bid, ask):
            return dict(zip(('act_symbol', 'expiration', 'strike', 'call_put'), key),
                        bid=bid, ask=ask)
        stream = [(date(2024, 1, 2), [quote(short, 5., 6.), quote(long, 2., 3.)]),
                  (date(2024, 1, 3), [quote(short, 2., 2.2), quote(long, .4, .5)]),
                  (date(2024, 1, 17), [quote(short, .8, 1.), quote(long, .1, .2)])]
        def selections(rows, day, signals):
            return {'trend': (short,), 'rich_vol_credit_spread': (short, long)} if day.day == 2 else {}
        with patch('option_lab.recent_study._dates_and_rows', side_effect=lambda *a: iter(stream)), \
             patch('option_lab.recent_study._spot_from_parity', return_value={'ABC': 100}), \
             patch('option_lab.recent_study.picks', side_effect=selections):
            result = run([], .015)
        t = result['strategies']['trend']['2024']['records'][0]
        self.assertAlmostEqual(t['cost'], 2.2 * 100 * 1.015)
        self.assertAlmostEqual(t['proceeds'], .8 * 100 * .985)
        s = result['strategies']['rich_vol_credit_spread']['2024']['records'][0]
        credit = (2 * .985 - .5 * 1.015) * 100
        debit = (1 * 1.015 - .1 * .985) * 100
        self.assertAlmostEqual(s['cost'], 500 - credit)
        self.assertAlmostEqual(s['return_fraction'], (credit - debit) / (500 - credit))


if __name__ == '__main__':
    unittest.main()
