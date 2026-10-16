"""Options trade cards and position monitoring for the premarket reversal rule.

Uses the existing signal/score/calibration unchanged. All outputs are paper
instructions. There is no broker client, login, execution or scheduling.
"""
import argparse
import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from .premarket_reversal import Config, NY, finite, scan, stamp
from .premarket_replay import replay, usable


def exit_bid_levels(cost, contracts=1, multiplier=100, exit_fee=.65, slippage=.01):
    """Bid observations needed for +30%/-20% net, rather than premium-only P&L."""
    if (not finite(cost, contracts, multiplier, exit_fee, slippage) or cost <= 0
            or contracts < 1 or int(contracts) != contracts or multiplier != 100
            or exit_fee < 0 or not 0 <= slippage < 1):
        raise ValueError('Invalid option cost, quantity or friction')
    denominator = contracts*multiplier*(1-slippage)
    return {'target_net_return': .30, 'stop_net_return': -.20,
            'target_observed_bid': (cost*1.30+exit_fee*contracts)/denominator,
            'stop_observed_bid': (cost*.80+exit_fee*contracts)/denominator,
            'time_exit_ET': '11:00',
            'note': 'Observation thresholds, not guaranteed fills or submitted stop orders.'}


def entry_cost(position):
    n = position['contracts']
    premium, fee = position['filled_premium'], position['entry_fee_total']
    if (not finite(n, premium, fee) or int(n) != n or n < 1 or premium <= 0 or fee < 0
            or position.get('multiplier') != 100 or position.get('right') not in ('call', 'put')
            or position.get('currency') != {'US': 'USD', 'CA': 'CAD'}.get(position.get('country'))):
        raise ValueError('Invalid actual option fill or explicit entry fee')
    return premium*100*n+fee


def trade_cards(result, accounts, positions=None, config=Config()):
    """Turn observed scored contracts into budgeted paper plans, never orders.

    Reserved cash/open-premium budgets are shared across proposed cards, so
    several attractive companies cannot all spend the same available cash.
    """
    positions = positions or []
    now = stamp(result['as_of'])
    reserved = {currency: 0. for currency in accounts}
    open_cost = {currency: 0. for currency in accounts}
    held = set()
    for p in positions:
        if stamp(p['entry_time']) > now:
            raise ValueError('Position entry is later than the plan timestamp')
        cost = entry_cost(p)
        held.add((p['country'], p['symbol']))
        if p['currency'] in open_cost:
            open_cost[p['currency']] += cost
    cards = []
    for c in sorted(result['candidates'], key=lambda r: (-r['setup_score'], r['country'], r['symbol'])):
        q = c['entry_quote']
        currency = c['currency']
        reasons = []
        if not (finite(q.get('strike'), q.get('tick_size')) and q['strike'] > 0 and q['tick_size'] > 0):
            cards.append({'country': c['country'], 'symbol': c['symbol'], 'status': 'NO TRADE',
                          'reasons': ['Missing strike or exchange tick-size metadata']})
            continue
        if (not usable(q) or q.get('standard_contract') is not True or q.get('multiplier') != 100
                or (q['country'], q['symbol'], q['currency'], q['right'], q['option_symbol']) !=
                   (c['country'], c['symbol'], currency, c['right'], c['option_symbol'])):
            cards.append({'country': c['country'], 'symbol': c['symbol'], 'status': 'NO TRADE',
                          'reasons': ['Inconsistent or invalid option contract/quote']})
            continue
        # Indicative limit must be on the feed-supplied tick grid. Never guess
        # whether a particular class/premium trades in pennies or nickels.
        if Decimal(str(q['ask'])) % Decimal(str(q['tick_size'])) != 0:
            reasons.append('Quoted ask is not on the supplied tick grid')
        quote_time, signal = stamp(q['quote_timestamp']), stamp(c['signal_time'])
        if (not signal < quote_time <= now or now-quote_time > timedelta(seconds=10)
                or now-signal > timedelta(seconds=config.max_quote_wait_seconds)):
            reasons.append('Signal or option quote is stale/future')
        if not finite(c.get('setup_score')) or c['setup_score'] < config.min_score:
            reasons.append('Setup score below fixed threshold')
        if (c.get('decision') != 'PAPER_CANDIDATE'
                or c.get('calibration', {}).get('paper_eligible') is not True):
            reasons.append('Earlier net option outcomes have not passed calibration')
        if (c['country'], c['symbol']) in held:
            reasons.append('Company already held or reserved')
        # Research cost/reserve matches the existing replay's conservative
        # ask +1% friction. The indicative limit itself remains the observed ask.
        modeled_cost = q['ask']*100*1.01+.65
        account = accounts.get(currency)
        budget = None
        if not account:
            reasons.append('Missing same-currency account input')
        else:
            fields = ('equity', 'available_cash', 'daily_start_equity', 'realized_pnl_today')
            if (not finite(*(account.get(k) for k in fields)) or account['equity'] <= 0
                    or account['daily_start_equity'] <= 0 or account['available_cash'] < 0):
                raise ValueError('Invalid account values')
            budget = min(.005*account['equity'], account['available_cash']-reserved[currency],
                         .02*account['equity']-open_cost[currency]-reserved[currency])
            if account['realized_pnl_today'] <= -.01*account['daily_start_equity']:
                reasons.append('Daily realized loss limit reached')
            if modeled_cost > budget:
                reasons.append('One contract exceeds cash or full-premium risk allocation')
        approved = not reasons
        if approved:
            reserved[currency] += modeled_cost
            held.add((c['country'], c['symbol']))
        cards.append({'country': c['country'], 'symbol': c['symbol'], 'currency': currency,
            'status': 'PAPER_ENTRY_PLAN' if approved else 'WATCH_ONLY', 'reasons': reasons,
            'option_contract': {'option_symbol': c['option_symbol'], 'right': c['right'],
                'strike': q['strike'], 'expiration': q['expiration'], 'multiplier': 100},
            'order_intent': 'BUY_TO_OPEN', 'order_type': 'LIMIT',
            'indicative_limit_premium': q['ask'], 'tick_size': q['tick_size'],
            'proposed_contracts': 1 if approved else 0,
            'quoted_debit_one_contract_before_fees': q['ask']*100,
            'modeled_full_premium_reserve': modeled_cost,
            'available_position_budget': budget,
            'exit_rules_on_modeled_entry': exit_bid_levels(modeled_cost),
            'entry_limit_note': 'Indicative ask-based limit; the 1% research buffer is not permission to fill above it. Actual fills/fees replace modeled costs in monitoring.',
            'setup_score': c['setup_score'], 'score_is_probability': False,
            'calibration': c['calibration'], 'greek_sensitivities': c['greek_sensitivities'],
            'strategy': 'premarket_down_confirmed_up_buy_call' if c['right'] == 'call'
                        else 'premarket_up_confirmed_down_buy_put'})
    return {'action': 'RESEARCH_ONLY', 'as_of': result['as_of'],
        'universe_count': result['universe_count'], 'coverage_counts': result['coverage_counts'],
        'trade_cards': cards, 'reserved_for_new_paper_plans': reserved,
        'target_4_to_5_percent_monthly_validated': False,
        'note': 'No order submitted. Ranking, calibration and paper plans do not establish future account returns.'}


def monitor(positions, quotes, as_of, exit_fee=.65, slippage=.01):
    """Mark actual long-option fills at an observed bid with explicit exit costs."""
    now = stamp(as_of)
    if not finite(exit_fee, slippage) or exit_fee < 0 or not 0 <= slippage < 1:
        raise ValueError('Invalid exit-cost assumptions')
    records = []
    for p in positions:
        cost = entry_cost(p)
        entered = stamp(p['entry_time'])
        if entered > now:
            raise ValueError('Future entry fill')
        cutoff = datetime.combine(entered.astimezone(NY).date(), time(11), NY)
        due = now >= cutoff
        identity = (p['country'], p['symbol'], p['currency'], p['option_symbol'])
        observed = [q for q in quotes if (q.get('country'), q.get('symbol'), q.get('currency'), q.get('option_symbol')) == identity
                    and entered < stamp(q['quote_timestamp']) <= now]
        base = {'country': p['country'], 'symbol': p['symbol'], 'option_symbol': p['option_symbol'],
                'right': p['right'], 'currency': p['currency'], 'contracts': p['contracts'],
                'entry_cost_with_actual_fee': cost, 'time_exit_due': due,
                'exit_rules_on_actual_entry': exit_bid_levels(cost, p['contracts'], exit_fee=exit_fee, slippage=slippage)}
        latest = max(observed, key=lambda q: stamp(q['quote_timestamp'])) if observed else None
        if (latest is None or now-stamp(latest['quote_timestamp']) > timedelta(seconds=10)
                or not usable(latest) or latest['bid_size'] < p['contracts']):
            records.append({**base, 'decision': 'NEEDS_FRESH_EXECUTABLE_OPTION_QUOTE',
                            'net_option_return': None, 'net_liquidation_pnl': None})
            continue
        proceeds = latest['bid']*100*p['contracts']*(1-slippage)-exit_fee*p['contracts']
        ret = proceeds/cost-1
        reason = 'stop' if ret <= -.20 else 'target' if ret >= .30 else 'time' if due else None
        records.append({**base, 'quote_time': latest['quote_timestamp'], 'bid': latest['bid'],
            'net_liquidation_value_model': proceeds, 'net_liquidation_pnl': proceeds-cost,
            'net_option_return': ret, 'decision': 'EXIT_PAPER_SIGNAL' if reason else 'HOLD_PAPER_POSITION',
            'exit_reason': reason, 'exit_order_intent': 'SELL_TO_CLOSE' if reason else None,
            'note': 'Bid-based net mark with exit-cost assumptions, not a realized fill. Actual later execution can differ.'})
    return {'action': 'RESEARCH_ONLY', 'as_of': as_of, 'positions': records,
            'return_basis': 'Actual option entry fill/fee versus observed option bid and modeled exit costs',
            'exit_fee_per_contract_assumption': exit_fee, 'adverse_exit_slippage': slippage,
            'note': 'No stock-return substitution, order submission or monthly profitability claim.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='Scan all supplied companies and build option trade cards')
    plan.add_argument('--input', required=True)
    plan.add_argument('--accounts', required=True, help='JSON object keyed by USD/CAD')
    plan.add_argument('--positions', help='JSON list of already open actual fills')
    watch = sub.add_parser('monitor', help='Monitor actual long call/put fills at option bid')
    watch.add_argument('--positions', required=True)
    watch.add_argument('--quotes', required=True)
    watch.add_argument('--as-of', required=True)
    watch.add_argument('--exit-fee', type=float, default=.65)
    watch.add_argument('--slippage', type=float, default=.01)
    evaluate = sub.add_parser('evaluate', help='Replay option quotes; stock-return records are not inputs')
    evaluate.add_argument('--candidates', required=True)
    evaluate.add_argument('--quotes', required=True)
    evaluate.add_argument('--currency', required=True, choices=['USD', 'CAD'])
    evaluate.add_argument('--start', default='2024-01-01')
    evaluate.add_argument('--end', default='2025-12-31')
    for cmd in (plan, watch, evaluate):
        cmd.add_argument('--report', required=True)
    a = p.parse_args()
    read = lambda path: json.loads(Path(path).read_text())
    if a.command == 'plan':
        r = trade_cards(scan(read(a.input)), read(a.accounts), read(a.positions) if a.positions else [])
    elif a.command == 'monitor':
        r = monitor(read(a.positions), read(a.quotes), a.as_of, a.exit_fee, a.slippage)
    else:
        c = read(a.candidates)
        r = replay(c['candidates'], read(a.quotes), a.currency, a.start, a.end,
                   covered_sessions=c.get('covered_sessions'))
    Path(a.report).write_text(json.dumps(r, indent=2, allow_nan=False)+'\n')
    print(json.dumps(r, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
