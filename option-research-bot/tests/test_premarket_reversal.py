import copy
import unittest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from option_lab.premarket_reversal import Config, VERSION, calibrate, scan
from option_lab.premarket_replay import replay, trade
from option_lab.option_universe import normalize, parse_sources


class PremarketTests(unittest.TestCase):
    def fixture(self, gap_up=False, country='US'):
        daily = []
        day = datetime(2024, 1, 17, tzinfo=timezone.utc)
        while len(daily) < 61:
            if day.weekday() < 5:
                close = 100 + (.3 if len(daily) % 2 else 0)
                daily.append({'country': country, 'symbol': 'ABC', 'date': day.date().isoformat(),
                    'open': 100., 'high': 102., 'low': 98., 'close': close, 'volume': 2e6})
            day -= timedelta(days=1)
        daily.sort(key=lambda r: r['date'])
        daily[-1]['close'] = 100.
        pre = 102. if gap_up else 98.
        bars = []
        for minute in range(0, 30, 5):
            bars.append({'country': country, 'symbol': 'ABC',
                'datetime': f'2024-01-18T14:{minute:02d}:00Z', 'open': pre,
                'high': pre+.1, 'low': pre-.1, 'close': pre, 'volume': 10_000.})
        for n, minute in enumerate((30, 35, 40)):
            op = pre + (-1 if gap_up else 1)*n*.2
            cl = op + (-.2 if gap_up else .2)
            bars.append({'country': country, 'symbol': 'ABC',
                'datetime': f'2024-01-18T14:{minute}:00Z', 'open': op,
                'high': max(op, cl)+.05, 'low': min(op, cl)-.05,
                'close': cl, 'volume': 100_000.})
        currency = 'USD' if country == 'US' else 'CAD'
        quote = {'country': country, 'symbol': 'ABC', 'option_symbol': 'ABC_TEST',
            'right': 'put' if gap_up else 'call', 'currency': currency,
            'quote_timestamp': '2024-01-18T14:45:02Z', 'bid': 1.95, 'ask': 2.,
            'bid_size': 20, 'ask_size': 20, 'standard_contract': True, 'multiplier': 100,
            'expiration': '2024-02-16', 'delta': -.6 if gap_up else .6,
            'gamma': .03, 'theta': -.01, 'vega': .05, 'iv': .10,
            'open_interest': 500, 'volume': 200,
            'open_interest_known_at': '2024-01-18T13:00:00Z',
            'underlying_price': bars[-1]['close'], 'theta_unit': 'per_calendar_day',
            'vega_unit': 'per_volatility_point'}
        return {'as_of': '2024-01-18T14:45:03Z', 'universe': [{'country': country,
            'symbol': 'ABC', 'kind': 'equity', 'currency': currency,
            'session_date': '2024-01-18', 'is_session': True, 'previous_session_date': '2024-01-17'}],
            'bars': bars, 'daily': daily, 'quotes': [quote],
            'context': [{'country': country, 'symbol': 'ABC', 'date': '2024-01-18',
                'known_at': '2024-01-18T14:44:00Z', 'earnings_within_1d': False,
                'major_news': False, 'corporate_action': False, 'halted': False,
                'history_split_basis_verified': True, 'market_return': 0., 'sector_return': 0.}]}

    def candidate(self):
        result = scan(self.fixture())
        self.assertEqual(result['coverage_counts'], {'scored': 1})
        return result['candidates'][0]

    def test_both_directions_require_confirmation_and_do_not_invent_confidence(self):
        for up, right in ((False, 'call'), (True, 'put')):
            result = scan(self.fixture(up))
            c = result['candidates'][0]
            self.assertEqual(c['right'], right)
            self.assertTrue(0 <= c['setup_score'] <= 100)
            self.assertFalse(c['score_is_probability'])
            self.assertIsNone(c['calibration']['estimated_net_win_rate'])
            self.assertEqual(c['decision'], 'NO TRADE')

    def test_future_bar_cannot_change_score(self):
        p = self.fixture()
        before = scan(p)['candidates'][0]['setup_score']
        p['bars'].append({**p['bars'][-1], 'datetime': '2024-01-18T14:45:00Z',
                          'close': 500., 'high': 501.})
        self.assertEqual(scan(p)['candidates'][0]['setup_score'], before)
        p['as_of'] = '2024-01-18T14:44:59Z'
        self.assertFalse(scan(p)['candidates'])

    def test_canadian_symbol_cannot_use_us_premarket(self):
        p = self.fixture(country='CA')
        for r in p['bars']:
            r['country'] = 'US'
        result = scan(p)
        self.assertFalse(result['candidates'])
        self.assertEqual(result['coverage_counts']['missing_regular_session_confirmation_bars'], 1)

    def test_unknown_news_and_future_context_fail_closed(self):
        p = self.fixture()
        p['context'][0]['major_news'] = None
        self.assertFalse(scan(p)['candidates'])
        p['context'][0]['major_news'] = False
        p['context'][0]['known_at'] = '2024-01-18T15:00:00Z'
        self.assertFalse(scan(p)['candidates'])

    def test_pre_signal_option_and_future_open_interest_fail(self):
        p = self.fixture()
        p['quotes'][0]['quote_timestamp'] = '2024-01-18T14:44:59Z'
        self.assertFalse(scan(p)['candidates'])
        p = self.fixture()
        p['quotes'][0]['open_interest_known_at'] = '2024-01-19T14:00:00Z'
        self.assertFalse(scan(p)['candidates'])

    def test_no_reversal_and_wide_quote_fail(self):
        p = self.fixture()
        p['quotes'][0]['bid'] = .5
        self.assertFalse(scan(p)['candidates'])
        p = self.fixture()
        for r in p['bars'][-3:]:
            r.update(open=98., close=97.9, high=98.1, low=97.8)
        self.assertFalse(scan(p)['candidates'])

    def test_calibration_purges_future_and_same_day_and_duplicates(self):
        c = self.candidate()
        sample = {'version': VERSION, 'country': 'US', 'symbol': 'ZZZ', 'right': 'call',
            'configuration_id': c['configuration_id'], 'outcome_policy_id': c['outcome_policy_id'],
            'setup_score': c['setup_score'], 'net_option_return': .2, 'complete_exit': True,
            'entry_time': '2024-01-17T14:45:02Z', 'exit_time': '2024-01-17T15:00:02Z'}
        future = {**sample, 'exit_time': '2024-01-19T15:00:02Z'}
        same_day = {**sample, 'entry_time': '2024-01-18T14:30:02Z', 'exit_time': '2024-01-18T14:40:02Z'}
        result = calibrate(c, [sample]*100+[future, same_day])
        self.assertEqual(result['samples'], 1)
        self.assertFalse(result['sufficient_history'])

    def test_completed_calibration_reports_frequency_and_interval(self):
        c = self.candidate()
        history = []
        for n in range(100):
            t = datetime(2023, 5, 1, 14, 45, tzinfo=timezone.utc)+timedelta(days=n)
            history.append({'version': VERSION, 'country': 'US', 'symbol': 'ZZZ', 'right': 'call',
                'configuration_id': c['configuration_id'], 'outcome_policy_id': c['outcome_policy_id'],
                'setup_score': c['setup_score'], 'net_option_return': .3 if n < 70 else -.2,
                'complete_exit': True, 'entry_time': t.isoformat(),
                'exit_time': (t+timedelta(minutes=20)).isoformat()})
        result = calibrate(c, history)
        self.assertAlmostEqual(result['estimated_net_win_rate'], .7)
        self.assertTrue(result['paper_eligible'])
        self.assertLess(result['win_rate_wilson_95'][0], .7)
        for row in history:
            row['outcome_policy_id'] = 'different_cost_or_exit_policy'
        self.assertFalse(calibrate(c, history)['sufficient_history'])

    def exit_quote(self, timestamp, bid, country='US'):
        return {'country': country, 'currency': 'USD', 'option_symbol': 'ABC_TEST',
                'quote_timestamp': timestamp, 'bid': bid, 'ask': bid+.05, 'bid_size': 10, 'ask_size': 10}

    def test_stop_executes_at_later_quote_and_can_overshoot(self):
        c = self.candidate()
        qs = [self.exit_quote('2024-01-18T14:50:00Z', 1.4),
              self.exit_quote('2024-01-18T14:50:02Z', 1.0)]
        r = trade(c, qs)
        self.assertEqual(r['exit_time'], '2024-01-18T14:50:02+00:00')
        self.assertLess(r['net_option_return'], -.2)
        self.assertAlmostEqual(r['pnl'], 100*.99-.65-(200*1.01+.65))

    def test_missing_exit_invalidates_account_return(self):
        c = self.candidate()
        r = replay([c], [], 'USD', paper_gate=False)
        self.assertEqual(r['unresolved_positions'], 1)
        self.assertIsNone(r['account_return'])
        self.assertIsNone(r['monthly_measurement_at_4_percent'])

    def test_other_country_exit_cannot_resolve_us_contract(self):
        c = self.candidate()
        qs = [self.exit_quote('2024-01-18T16:00:00Z', 2., country='CA'),
              self.exit_quote('2024-01-18T16:00:02Z', 2., country='CA')]
        self.assertEqual(trade(c, qs)['status'], 'missing_exit_observation')

    def test_replay_respects_calibration_gate_and_cash_risk(self):
        c = self.candidate()
        self.assertEqual(replay([c], [], 'USD')['filled_trades'], 0)
        self.assertEqual(replay([c], [], 'USD', capital=1000., paper_gate=False)['filled_trades'], 0)

    def test_matched_trades_without_session_coverage_cannot_claim_account_return(self):
        c = self.candidate()
        qs = [self.exit_quote('2024-01-18T16:00:00Z', 2.5),
              self.exit_quote('2024-01-18T16:00:02Z', 2.5)]
        r = replay([c], qs, 'USD', paper_gate=False)
        self.assertEqual(r['matched_trades'], 1)
        self.assertGreater(r['matched_trade_pnl'], 0)
        self.assertIsNone(r['account_return'])
        self.assertGreater(r['sessions_without_verified_input_coverage'], 0)

    def test_same_ticker_us_and_canada_remain_separate(self):
        base = {'symbol': 'ABC', 'kind': 'equity', 'name': 'ABC', 'option_root': 'ABC', 'source': 'test'}
        rows = normalize([{**base, 'country': 'US'}, {**base, 'country': 'CA'}])
        self.assertEqual(len(rows), 2)

    def test_expired_decision_window_cannot_emit_stale_candidate(self):
        p = self.fixture()
        p['as_of'] = '2024-01-18T15:00:00Z'
        self.assertEqual(scan(p)['coverage_counts'], {'decision_window_elapsed': 1})

    def test_phlx_duplicate_symbol_headers_preserve_root_and_underlying(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'phlxoptions.csv').write_text(',,,PHLX LISTED OPTIONS,,\n'
                'Company,Cycle,Symbol,Symbol,Specialist Unit\nExample,JAN,ABC1,ABC,Maker\n')
            rows, details = parse_sources(d)
        self.assertEqual(rows[0]['symbol'], 'ABC')
        self.assertEqual(rows[0]['option_roots'], ['ABC1'])
        self.assertEqual(details[0]['rows'], 1)


if __name__ == '__main__':
    unittest.main()
