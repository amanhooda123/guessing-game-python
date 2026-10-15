"""One-contract long-option quote replay for the fixed premarket hypothesis.

Requires observed entry and exit bid/ask; no Black-Scholes or stock-return
substitution. Currency accounts are separate. Missing held exits invalidate
the account return. Stops/targets execute at a later quote with a fixed delay.
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from .premarket_reversal import NY, VERSION, finite, stamp, outcome_policy_id
from .monthly_target import marked_monthly_nav


def usable(q):
    return (finite(*(q.get(k) for k in ('bid', 'ask', 'bid_size', 'ask_size')))
            and 0 < q['bid'] <= q['ask'] and min(q['bid_size'], q['ask_size']) >= 1)


def trade(candidate, quotes, fee=.65, slippage=.01, latency_seconds=1):
    q = candidate['entry_quote']
    entry = stamp(q['quote_timestamp'])
    if (not usable(q) or q.get('multiplier') != 100 or q.get('standard_contract') is not True
            or q.get('currency') != candidate['currency'] or entry <= stamp(candidate['signal_time'])):
        return {'status': 'invalid_entry'}
    cost = q['ask'] * (1+slippage) * 100 + fee
    cutoff = datetime.combine(entry.astimezone(NY).date(), time(11), NY)
    if entry >= cutoff:
        return {'status': 'invalid_entry_time'}
    after = sorted((r for r in quotes if r.get('country') == candidate['country']
        and r.get('option_symbol') == candidate['option_symbol']
        and r.get('currency') == candidate['currency']
        and entry < stamp(r['quote_timestamp'])
        and stamp(r['quote_timestamp']).astimezone(NY).date() == entry.astimezone(NY).date()),
        key=lambda r: stamp(r['quote_timestamp']))
    if len({r['quote_timestamp'] for r in after}) != len(after):
        return {'status': 'invalid_duplicate_quotes'}
    trigger, reason = None, None
    for r in after:
        if not usable(r):
            continue
        at = stamp(r['quote_timestamp'])
        # First observed quote at/after time stop, or first observed target/stop.
        # A gap between quotes can make actual losses larger than the threshold.
        liquidation = r['bid'] * (1-slippage) * 100 - fee
        ret = liquidation / cost - 1
        if at >= cutoff or ret <= -.20 or ret >= .30:
            trigger, reason = at, 'time' if at >= cutoff else 'stop' if ret <= -.20 else 'target'
            break
    base = {'version': VERSION, 'country': candidate['country'], 'symbol': candidate['symbol'],
        'configuration_id': candidate.get('configuration_id'),
        'outcome_policy_id': outcome_policy_id(fee, slippage, latency_seconds),
        'right': candidate['right'], 'currency': candidate['currency'],
        'option_symbol': candidate['option_symbol'], 'setup_score': candidate['setup_score'],
        'entry_time': entry.isoformat(), 'cost': cost, 'complete_exit': False}
    if trigger is None:
        return {**base, 'status': 'missing_exit_observation'}
    # Execute at the first usable quote after the trigger + order latency,
    # within a minute, and never carry an intraday model into another day.
    for r in after:
        at = stamp(r['quote_timestamp'])
        if (trigger+timedelta(seconds=latency_seconds) <= at <= trigger+timedelta(seconds=60)
                and at < datetime.combine(entry.astimezone(NY).date(), time(15, 50), NY)
                and usable(r)):
            proceeds = r['bid'] * (1-slippage) * 100 - fee
            return {**base, 'status': 'matched', 'complete_exit': True,
                'exit_time': at.isoformat(), 'exit_reason': reason, 'proceeds': proceeds,
                'pnl': proceeds-cost, 'net_option_return': proceeds/cost-1}
    return {**base, 'status': 'missing_post_trigger_execution_quote', 'exit_reason': reason}


def replay(candidates, quotes, currency, start='2024-01-01', end='2025-12-31',
           capital=100_000., allocation=.005, max_open_cost=.02, paper_gate=True,
           covered_sessions=None):
    if not 0 < allocation <= max_open_cost <= 1 or capital <= 0:
        raise ValueError('Invalid account parameters')
    first_day, last_day = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
    if first_day.day != 1 or (last_day+timedelta(days=1)).day != 1 or first_day > last_day:
        raise ValueError('Use complete calendar months')
    skipped, selected = Counter(), []
    for c in sorted(candidates, key=lambda x: (stamp(x['entry_quote']['quote_timestamp']), -x['setup_score'], x['symbol'])):
        d = stamp(c['entry_quote']['quote_timestamp']).astimezone(NY).date()
        if c['currency'] != currency or not first_day <= d <= last_day:
            continue
        if paper_gate and c.get('decision') != 'PAPER_CANDIDATE':
            skipped['uncalibrated_or_low_score'] += 1
            continue
        selected.append(trade(c, quotes))
    cash, held, filled, timeline = capital, {}, [], defaultdict(lambda: {'buy': [], 'sell': []})
    invalid = [r for r in selected if 'cost' not in r]
    for i, r in enumerate(selected):
        if 'cost' not in r:
            skipped[r['status']] += 1
            continue
        timeline[stamp(r['entry_time'])]['buy'].append((i, r))
        if r['status'] == 'matched':
            timeline[stamp(r['exit_time'])]['sell'].append((i, r))
    daily, daily_start, daily_pnl = {}, {}, defaultdict(float)
    traded_days = set()
    for at in sorted(timeline):
        day = at.astimezone(NY).date().isoformat()
        daily_start.setdefault(day, cash+sum(r['cost'] for r in held.values()))
        for i, r in timeline[at]['sell']:
            if i in held:
                cash += r['proceeds']
                daily_pnl[day] += r['pnl']
                del held[i]
        for i, r in timeline[at]['buy']:
            key = r['country'], r['symbol']
            equity_at_cost = cash+sum(x['cost'] for x in held.values())
            if key in {(x['country'], x['symbol']) for x in held.values()} or key+(day,) in traded_days:
                skipped['already_traded_or_held'] += 1
                continue
            if daily_pnl[day] <= -.01*daily_start[day]:
                skipped['daily_realized_loss_limit'] += 1
                continue
            if (r['cost'] > allocation*equity_at_cost or r['cost'] > cash
                    or r['cost']+sum(x['cost'] for x in held.values()) > max_open_cost*equity_at_cost):
                skipped['capital_or_premium_risk_limit'] += 1
                continue
            cash -= r['cost']
            held[i] = r
            filled.append(r)
            traded_days.add(key+(day,))
        daily[day] = cash+sum(r['cost'] for r in held.values())
    matched = [r for r in filled if r['status'] == 'matched']
    import exchange_calendars as xc
    calendar = xc.get_calendar('XNYS' if currency == 'USD' else 'XTSE', start=start, end=end)
    required_sessions = {d.strftime('%Y-%m-%d') for d in calendar.sessions}
    missing_sessions = required_sessions-set(covered_sessions or [])
    complete = not held and not invalid and not missing_sessions
    # No overnight positions are allowed in the model. A missing intraday exit
    # permanently fails complete NAV, even if a later source file has prices.
    monthly_pnl = defaultdict(float)
    for r in matched:
        monthly_pnl[r['exit_time'][:7]] += r['pnl']
    month = first_day.replace(day=1)
    previous = month-timedelta(days=1)
    nav, rows = capital, [{'month': previous.strftime('%Y-%m'),
                          'net_liquidation_value': capital, 'complete_position_marks': complete}]
    while month <= last_day:
        key = month.strftime('%Y-%m')
        nav += monthly_pnl[key]
        rows.append({'month': key, 'net_liquidation_value': nav, 'complete_position_marks': complete})
        month = (month.replace(day=28)+timedelta(days=4)).replace(day=1)
    measurement = marked_monthly_nav(rows, target=.04) if complete and nav > 0 else None
    if measurement and not filled:
        measurement['note'] = 'No trades; flat hypothetical account does not measure a strategy edge.'
    wins = sum(r['pnl'] > 0 for r in matched)
    positive = sum(max(r['pnl'], 0) for r in matched)
    negative = -sum(min(r['pnl'], 0) for r in matched)
    return {'action': 'NO TRADE', 'classification': 'HYPOTHETICAL REAL-QUOTE REPLAY; FILLS NOT VERIFIED',
        'currency': currency, 'initial_capital': capital, 'filled_trades': len(filled),
        'matched_trades': len(matched), 'unresolved_positions': len(held), 'skipped': dict(skipped),
        'win_rate': wins/len(matched) if matched else None,
        'profit_factor': positive/negative if negative else None,
        'mean_net_option_return': sum(r['net_option_return'] for r in matched)/len(matched) if matched else None,
        'account_return': cash/capital-1 if complete and filled else None,
        'complete_account_valuations': complete,
        'sessions_without_verified_input_coverage': len(missing_sessions),
        'matched_trade_pnl': sum(r['pnl'] for r in matched),
        'monthly_measurement_at_4_percent': measurement,
        'target_4_to_5_percent_monthly_validated': False,
        'parameters': {'fee_per_side': .65, 'adverse_price_slippage': .01,
            'target_net_option_return': .30, 'stop_net_option_return': -.20,
            'time_exit_ET': '11:00, executed at a subsequent quote',
            'full_premium_account_limit': allocation, 'total_open_premium_limit': max_open_cost,
            'require_past_calibration': paper_gate},
        'trades': filled,
        'limitations': ['Quotes with size do not guarantee execution',
            'Missing session input coverage prevents a full account-return claim',
            'Price-triggered exits use later observed quotes and can overshoot loss thresholds',
            'Per-currency accounts assume funding is already in that currency; FX and taxes omitted',
            'Complete supplied input coverage and quote provenance require independent verification']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidates', required=True, help='Scanner output, already scored at each historical timestamp')
    p.add_argument('--quotes', required=True)
    p.add_argument('--currency', required=True, choices=['USD', 'CAD'])
    p.add_argument('--report', required=True)
    p.add_argument('--start', default='2024-01-01')
    p.add_argument('--end', default='2025-12-31')
    p.add_argument('--diagnostic-without-calibration', action='store_true')
    a = p.parse_args()
    c = json.loads(Path(a.candidates).read_text())
    r = replay(c['candidates'], json.loads(Path(a.quotes).read_text()), a.currency,
               a.start, a.end, paper_gate=not a.diagnostic_without_calibration,
               covered_sessions=c.get('covered_sessions'))
    Path(a.report).write_text(json.dumps(r, indent=2)+'\n')
    print(json.dumps({k: v for k, v in r.items() if k != 'trades'}, indent=2))
