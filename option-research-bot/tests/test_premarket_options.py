"""Synthetic accounting/decision checks; no trading performance is claimed."""
import copy
import unittest
from option_lab.premarket_options import exit_bid_levels, monitor, trade_cards


class OptionWorkflowTests(unittest.TestCase):
    def candidate(self, symbol='ABC'):
        q = {'country': 'US', 'symbol': symbol, 'currency': 'USD',
             'option_symbol': symbol+'_SYNTHETIC', 'right': 'call', 'strike': 100.,
             'expiration': '2024-02-16', 'multiplier': 100, 'standard_contract': True,
             'bid': 1.95, 'ask': 2., 'bid_size': 20, 'ask_size': 20,
             'tick_size': .05, 'quote_timestamp': '2024-01-18T14:45:02Z'}
        return {'country': 'US', 'symbol': symbol, 'currency': 'USD',
            'option_symbol': q['option_symbol'], 'right': 'call',
            'signal_time': '2024-01-18T14:45:00Z', 'entry_quote': q,
            'setup_score': 90., 'decision': 'PAPER_CANDIDATE',
            'calibration': {'paper_eligible': True, 'estimated_net_win_rate': .7},
            'greek_sensitivities': {'delta_per_contract': 60.}}

    def result(self, candidates):
        return {'as_of': '2024-01-18T14:45:03Z', 'candidates': candidates,
                'universe_count': len(candidates), 'coverage_counts': {'scored': len(candidates)}}

    def account(self, cash=100_000, equity=100_000):
        return {'USD': {'equity': equity, 'available_cash': cash,
            'daily_start_equity': equity, 'realized_pnl_today': 0.}}

    def position(self, right='call', contracts=1):
        return {'country': 'US', 'symbol': 'ABC', 'currency': 'USD',
            'option_symbol': 'ABC_SYNTHETIC', 'right': right, 'strike': 100.,
            'expiration': '2024-02-16', 'multiplier': 100, 'contracts': contracts,
            'entry_time': '2024-01-18T14:45:03Z', 'filled_premium': 2., 'entry_fee_total': .65*contracts}

    def quote(self, bid=2., timestamp='2024-01-18T14:50:00Z'):
        return {'country': 'US', 'symbol': 'ABC', 'currency': 'USD',
            'option_symbol': 'ABC_SYNTHETIC', 'quote_timestamp': timestamp,
            'bid': bid, 'ask': bid+.05, 'bid_size': 20, 'ask_size': 20}

    def test_profit_thresholds_include_contract_multiplier_both_fees_and_slippage(self):
        cost = 2.*100*2+1.30
        levels = exit_bid_levels(cost, contracts=2)
        target_proceeds = levels['target_observed_bid']*100*2*.99-.65*2
        stop_proceeds = levels['stop_observed_bid']*100*2*.99-.65*2
        self.assertAlmostEqual(target_proceeds/cost-1, .30)
        self.assertAlmostEqual(stop_proceeds/cost-1, -.20)

    def test_underlying_rise_cannot_be_reported_as_option_profit(self):
        q = {**self.quote(1.5), 'underlying_price': 200., 'delta': .99}
        r = monitor([self.position()], [q], '2024-01-18T14:50:01Z')['positions'][0]
        self.assertLess(r['net_option_return'], -.20)
        self.assertEqual(r['exit_reason'], 'stop')
        self.assertAlmostEqual(r['net_liquidation_pnl'], 150*.99-.65-200.65)

    def test_profitable_put_closes_by_selling_same_contract(self):
        r = monitor([self.position('put')], [self.quote(2.8)],
                    '2024-01-18T14:50:01Z')['positions'][0]
        self.assertEqual(r['exit_reason'], 'target')
        self.assertEqual(r['exit_order_intent'], 'SELL_TO_CLOSE')
        self.assertGreater(r['net_option_return'], .30)

    def test_stale_quote_keeps_overdue_exit_visible_without_fabricated_pnl(self):
        r = monitor([self.position()], [self.quote()],
                    '2024-01-18T16:01:00Z')['positions'][0]
        self.assertTrue(r['time_exit_due'])
        self.assertEqual(r['decision'], 'NEEDS_FRESH_EXECUTABLE_OPTION_QUOTE')
        self.assertIsNone(r['net_option_return'])

    def test_future_or_wrong_country_quotes_do_not_value_position(self):
        for q in (self.quote(timestamp='2024-01-18T15:00:00Z'), {**self.quote(), 'country': 'CA'}):
            r = monitor([self.position()], [q], '2024-01-18T14:50:01Z')['positions'][0]
            self.assertIsNone(r['net_liquidation_pnl'])

    def test_insufficient_bid_size_is_not_a_full_position_exit(self):
        q = {**self.quote(), 'bid_size': 1}
        r = monitor([self.position(contracts=2)], [q],
                    '2024-01-18T14:50:01Z')['positions'][0]
        self.assertIsNone(r['net_option_return'])

    def test_trade_card_is_option_specific_and_retains_reversal_direction(self):
        c = self.candidate()
        r = trade_cards(self.result([c]), self.account())['trade_cards'][0]
        self.assertEqual(r['status'], 'PAPER_ENTRY_PLAN')
        self.assertEqual(r['order_intent'], 'BUY_TO_OPEN')
        self.assertEqual(r['proposed_contracts'], 1)
        self.assertEqual(r['option_contract']['strike'], 100.)
        self.assertAlmostEqual(r['modeled_full_premium_reserve'], 202.65)
        self.assertFalse(r['score_is_probability'])

    def test_no_confidence_does_not_turn_high_score_into_entry(self):
        c = self.candidate()
        c['calibration'] = {'paper_eligible': False, 'estimated_net_win_rate': None}
        r = trade_cards(self.result([c]), self.account())
        self.assertEqual(r['trade_cards'][0]['status'], 'WATCH_ONLY')
        self.assertEqual(r['reserved_for_new_paper_plans']['USD'], 0.)

    def test_two_companies_cannot_spend_same_cash(self):
        r = trade_cards(self.result([self.candidate('ABC'), self.candidate('XYZ')]), self.account(cash=300))
        self.assertEqual([x['proposed_contracts'] for x in r['trade_cards']], [1, 0])
        self.assertAlmostEqual(r['reserved_for_new_paper_plans']['USD'], 202.65)

    def test_expensive_option_has_no_fixed_dollar_cap_when_account_allows(self):
        c = self.candidate()
        c['entry_quote'].update(ask=40., bid=39.)
        r = trade_cards(self.result([c]), self.account(equity=1_000_000, cash=1_000_000))
        self.assertEqual(r['trade_cards'][0]['status'], 'PAPER_ENTRY_PLAN')

    def test_existing_premium_and_daily_loss_block_new_plans(self):
        p = {**self.position(), 'symbol': 'OTHER', 'filled_premium': 18.}
        r = trade_cards(self.result([self.candidate()]), self.account(), [p])
        self.assertEqual(r['trade_cards'][0]['proposed_contracts'], 0)
        account = self.account()
        account['USD']['realized_pnl_today'] = -1000.
        r = trade_cards(self.result([self.candidate()]), account)
        self.assertEqual(r['trade_cards'][0]['proposed_contracts'], 0)

    def test_missing_tick_metadata_and_stale_quote_cannot_make_entry_plan(self):
        c = self.candidate()
        del c['entry_quote']['tick_size']
        self.assertEqual(trade_cards(self.result([c]), self.account())['trade_cards'][0]['status'], 'NO TRADE')
        c = self.candidate()
        r = self.result([c])
        r['as_of'] = '2024-01-18T14:45:25Z'
        self.assertEqual(trade_cards(r, self.account())['trade_cards'][0]['proposed_contracts'], 0)


if __name__ == '__main__':
    unittest.main()
