"""Fixed cross-symbol 2024/2025 comparison; exploratory, never a trade signal.

Compare directional trend, reversal, discounted straddles and rich-volatility credit spreads.
This is quote matching, not a portfolio simulation or an executable-fill claim.
"""
from __future__ import annotations
import argparse
import bisect
import json
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from .broad_study import _dates_and_rows, _key, _spot_from_parity
from .factors import evaluate


def elapsed_volatility(series):
    """Diffusion variance estimate per elapsed calendar day, annualized by 365.

    Irregular observations are not silently treated as consecutive trading days.
    This proxy assumes constant drift and variance; it is not daily-close RV.
    """
    if len(series) < 21:
        return None
    pairs = list(zip(series[-21:-1], series[-20:]))
    gaps = [(b[0] - a[0]).days for a, b in pairs]
    if min(gaps) <= 0 or max(gaps) > 10:
        return None
    returns = [math.log(b[1] / a[1]) for a, b in pairs]
    drift = sum(returns) / sum(gaps)
    variance = sum((r - drift * dt) ** 2 / dt for r, dt in zip(returns, gaps))
    return math.sqrt(365 * variance / (len(returns) - 1))


def features(daily):
    histories, result = defaultdict(list), {}
    for day, spots in daily:
        for symbol, spot in spots.items():
            prior = histories[symbol]
            # Reject proxy discontinuities, and warm up afresh. Real corporate
            # action data is required to interpret rather than discard them.
            if prior and (abs(math.log(spot / prior[-1][1])) > .25
                          or (day - prior[-1][0]).days > 10):
                prior.clear()
            if len(prior) >= 60:
                rv = elapsed_volatility(prior)
                prices = [x[1] for x in prior[-60:]]
                trend = sum(prices[-20:]) / 20 > sum(prices) / 60
                move = math.log(prices[-1] / prices[-6])
                gap = (prior[-1][0] - prior[-6][0]).days
                z = move / (rv * math.sqrt(gap / 365)) if rv and gap else 0
                result[symbol, day] = (spot, rv, trend, z)
            prior.append((day, spot))
    return result


def valid_quote(row):
    bid, ask = row.get('bid'), row.get('ask')
    return (bid is not None and ask is not None and math.isfinite(bid)
            and math.isfinite(ask) and bid > 0 and ask >= bid)


def picks(rows, day, signals):
    best, pairs, wings = {}, defaultdict(dict), defaultdict(list)
    for r in rows:
        f = signals.get((r['act_symbol'], day))
        if f is None or f[1] is None or not valid_quote(r):
            continue
        if r['call_put'] not in ('Call', 'Put'):
            continue
        if any(r[k] is None or not math.isfinite(r[k]) for k in
               ('vol', 'delta', 'gamma', 'theta', 'vega', 'strike')):
            continue
        dte = (date.fromisoformat(r['expiration'][:10]) - day).days
        spread = (r['ask'] - r['bid']) / r['ask']
        if 30 <= dte <= 60 and spread <= .10 and r['vol'] > 0:
            wings[(r['act_symbol'], r['expiration'][:10], r['call_put'])].append(r)
        # Straddle IV filter and ATM selection use the decision snapshot only.
        if (30 <= dte <= 60 and spread <= .10 and .35 <= abs(r['delta']) <= .65
                and 0 < r['vol'] <= .8 * f[1] and abs(r['strike'] / f[0] - 1) <= .03):
            pairs[(r['act_symbol'], r['expiration'][:10], r['strike'])][r['call_put']] = r
        mapped = {'underlying_symbol': r['act_symbol'], 'quote_date': day.isoformat(),
                  'expiration': r['expiration'][:10], 'strike': r['strike'],
                  'option_type': 'C' if r['call_put'] == 'Call' else 'P',
                  'bid_1545': r['bid'], 'ask_1545': r['ask']}
        for source, target in [('vol', 'implied_volatility'), ('delta', 'delta'),
                               ('gamma', 'gamma'), ('theta', 'theta'), ('vega', 'vega')]:
            mapped[target + '_1545'] = r[source]
        c, _ = evaluate(mapped, f[0], f[1], require_size_volume=False)
        if not c:
            continue
        is_call = r['call_put'] == 'Call'
        for name, qualify in [('trend', is_call == f[2]),
                               ('reversal', abs(f[3]) >= 1.5 and is_call == (f[3] < 0))]:
            if qualify:
                choice = (c['score'], (_key(r),))
                if name not in best or choice < best[name]:
                    best[name] = choice
    for (symbol, expiry, strike), sides in pairs.items():
        if len(sides) == 2:
            f = signals[symbol, day]
            c, p = sides['Call'], sides['Put']
            score = ((c['vol'] + p['vol']) / (2 * f[1])
                     + abs(strike / f[0] - 1))
            choice = (score, (_key(c), _key(p)))
            if 'discount_straddle' not in best or choice < best['discount_straddle']:
                best['discount_straddle'] = choice
    for (symbol, expiry, right), chain in wings.items():
        f = signals[symbol, day]
        # Sell put spreads in an uptrend, call spreads in a downtrend.
        if (right == 'Put') != f[2]:
            continue
        for short in chain:
            if not (.15 <= abs(short['delta']) <= .30 and short['vol'] >= 1.3 * f[1]):
                continue
            for long in chain:
                width = (short['strike'] - long['strike'] if right == 'Put'
                         else long['strike'] - short['strike'])
                credit = short['bid'] - long['ask']
                if .02 * f[0] <= width <= .08 * f[0] and .15 * width <= credit < .60 * width:
                    score = abs(abs(short['delta']) - .20) - .1 * credit / width
                    choice = (score, (_key(short), _key(long)))
                    if 'rich_vol_credit_spread' not in best or choice < best['rich_vol_credit_spread']:
                        best['rich_vol_credit_spread'] = choice
    return {name: keys for name, (_, keys) in best.items()}


def summarize(records):
    matched = [r for r in records if r['status'] == 'matched']
    entered = [r for r in records if r['status'] in ('matched', 'missing_exit')]
    values = [r['return_fraction'] for r in matched]
    stress = [r.get('return_fraction', -1.) for r in entered]
    invested = sum(r['cost'] for r in matched)
    return {'selected': len(records), 'matched': len(matched), 'entered': len(entered),
            'missing_entry': sum(r['status'] == 'missing_entry' for r in records),
            'missing_exit': sum(r['status'] == 'missing_exit' for r in records),
            'match_fraction': len(matched) / len(records) if records else 0,
            'mean_return': statistics.mean(values) if values else None,
            'median_return': statistics.median(values) if values else None,
            'win_fraction': sum(v > 0 for v in values) / len(values) if values else None,
            'mean_full_loss_stress': statistics.mean(stress) if stress else None,
            'matched_total_pnl': sum(r['proceeds'] - r['cost'] for r in matched),
            'matched_risk_weighted_return': sum(r['proceeds'] for r in matched) / invested - 1
                if invested else None,
            'symbols_matched': len({r['keys'][0][0] for r in matched}),
            'records': records}


def run(paths, fx_fee=.015, cache=None):
    import exchange_calendars as xc
    calendar = xc.get_calendar('XNYS', start='2023-01-01', end='2025-12-31')
    sessions = {d.date() for d in calendar.sessions}
    first, last = date(2023, 1, 1), date(2025, 12, 31)
    # Cache is only an output, so a stale cache cannot silently affect results.
    daily = [(day, _spot_from_parity(rows, day)) for day, rows in
             _dates_and_rows(paths, first, last) if day in sessions]
    if cache:
        Path(cache).write_text(json.dumps([(d.isoformat(), s) for d, s in daily]))
    signals = features(daily)
    days = [day for day, _ in daily]
    ix = {d: i for i, d in enumerate(days)}
    pending, records = defaultdict(list), {n: {2024: [], 2025: []} for n in
                                          ('trend', 'reversal', 'discount_straddle',
                                           'rich_vol_credit_spread')}
    for day, rows in _dates_and_rows(paths, first, last):
        if day not in ix:
            continue
        i = ix[day]
        due = pending.pop(i, [])
        needed = {tuple(k) for r in due for k in r['keys']}
        found = {_key(r): r for r in rows if _key(r) in needed}
        for record in due:
            quotes = [found.get(tuple(k)) for k in record['keys']]
            ok = all(q is not None and valid_quote(q) for q in quotes)
            if record['status'] == 'pending_entry':
                if not ok:
                    record['status'] = 'missing_entry'
                    continue
                if record['strategy'] == 'rich_vol_credit_spread':
                    credit = (quotes[0]['bid'] * (1 - fx_fee)
                              - quotes[1]['ask'] * (1 + fx_fee)) * 100
                    width = abs(record['keys'][0][2] - record['keys'][1][2]) * 100
                    if not 0 < credit < width:
                        record['status'] = 'missing_entry'
                        continue
                    record.update(credit=credit, width=width, cost=width-credit)
                else:
                    record['cost'] = sum(q['ask'] for q in quotes) * 100 * (1 + fx_fee)
                record.update(entry=day.isoformat(), status='pending_exit')
                pending[record['exit_index']].append(record)
            elif not ok:
                record['status'] = 'missing_exit'
            else:
                if record['strategy'] == 'rich_vol_credit_spread':
                    debit = (quotes[0]['ask'] * (1 + fx_fee)
                             - quotes[1]['bid'] * (1 - fx_fee)) * 100
                    # Impossible spread marks are missing exits, not profits.
                    if not 0 <= debit <= record['width'] * (1 + fx_fee):
                        record['status'] = 'missing_exit'
                        continue
                    # Equivalent ending risk reserve; this is not sale proceeds.
                    proceeds = record['cost'] + record['credit'] - debit
                    record['close_debit'] = debit
                else:
                    proceeds = sum(q['bid'] for q in quotes) * 100 * (1 - fx_fee)
                record.update(status='matched', exit=day.isoformat(), proceeds=proceeds,
                              return_fraction=proceeds / record['cost'] - 1)
        if day.year not in (2024, 2025) or i + 1 >= len(days):
            continue
        entry_day = days[i + 1]
        target = entry_day + timedelta(days=14)
        exit_i = bisect.bisect_left(days, target)
        if (exit_i >= len(days) or days[exit_i].year != day.year
                or (entry_day - day).days > 7 or (days[exit_i] - target).days > 7):
            continue
        for name, keys in picks(rows, day, signals).items():
            if any(date.fromisoformat(k[1]) <= days[exit_i] for k in keys):
                continue
            record = {'signal': day.isoformat(), 'keys': keys,
                      'strategy': name, 'status': 'pending_entry', 'exit_index': exit_i}
            records[name][day.year].append(record)
            pending[i + 1].append(record)
    assert not pending, 'Unresolved quote matches'
    results = {n: {str(y): summarize(r) for y, r in years.items()}
               for n, years in records.items()}
    # A historical candidate must survive costs, missing-exit full-loss stress,
    # and have at least 30 matches and 80% quote coverage in BOTH years.
    eligible = [n for n, years in results.items() if all(
        d['matched'] >= 30 and d['match_fraction'] >= .8 and d['mean_return'] > 0
        and d['mean_full_loss_stress'] > 0 for d in years.values())]
    return {'action': 'NO TRADE', 'fx_fee_per_side': fx_fee,
            'classification': 'Exploratory repeated historical comparison; 2025 already examined',
            'hypotheses_passing_historical_gate': eligible,
            'exchange_session_snapshots': len(days),
            'symbols_with_proxy': len({s for _, spots in daily for s in spots}),
            'strategies': results,
            'limitations': ['No executable timestamp, volume or quote sizes',
                'Underlying is a put-call-parity proxy with carry/dividends omitted',
                'Irregular snapshots and incomplete strike/expiry universe',
                'No account capital, overlap constraints, live fills or Canadian-option data',
                'Credit-spread returns use reserved maximum risk; long-option returns use premium',
                'Short-option early assignment, exercise, borrow and dividend cashflows are omitted',
                'Missing-exit stress is a sensitivity assumption, not an observed loss',
                'Fresh future evaluation is required before any live signal']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files', nargs='+', required=True)
    p.add_argument('--report', required=True)
    p.add_argument('--spot-cache')
    p.add_argument('--fx-fee', type=float, default=.015)
    args = p.parse_args()
    if not 0 <= args.fx_fee < 1:
        p.error('FX fee must lie in [0, 1)')
    result = run(args.files, args.fx_fee, args.spot_cache)
    Path(args.report).write_text(json.dumps(result, indent=2) + '\n')
    for name, years in result['strategies'].items():
        print(name, {y: {k: v for k, v in d.items() if k != 'records'}
                     for y, d in years.items()}, flush=True)
