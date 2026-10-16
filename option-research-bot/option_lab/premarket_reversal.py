"""Premarket reversal research. Scores are rankings, never invented probabilities.

Input is point-in-time 5-minute stock bars, earlier daily bars, timestamped
event/context flags and real option NBBO/Greeks. No order API is present.
"""
import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
VERSION = 'premarket-reversal-v1'


def stamp(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('Timestamps must include an offset')
    return t


def bounded(x):
    return min(1., max(0., x))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def outcome_policy_id(fee=.65, slippage=.01, latency_seconds=1):
    return fingerprint({'target': .30, 'stop': -.20, 'time_exit': '11:00ET',
                        'fee': fee, 'slippage': slippage, 'latency': latency_seconds})


def finite(*values):
    return all(isinstance(v, (float, int)) and not isinstance(v, bool)
               and math.isfinite(v) for v in values)


@lru_cache(maxsize=2048)
def previous_exchange_session(country, session):
    import exchange_calendars as xc
    year = date.fromisoformat(session).year
    cal = xc.get_calendar('XNYS' if country == 'US' else 'XTSE',
                          start=f'{year-1}-01-01', end=f'{year+1}-12-31')
    if not cal.is_session(session):
        return None
    return cal.previous_session(session).strftime('%Y-%m-%d')


@dataclass(frozen=True)
class Config:
    decision_minute: int = 9 * 60 + 45
    min_price: float = 5.
    min_daily_dollar_volume: float = 10_000_000.
    min_premarket_dollar_volume: float = 100_000.
    min_gap: float = .005
    max_gap: float = .08
    min_gap_atr: float = .25
    max_gap_atr: float = 2.5
    min_score: float = 75.
    min_dte: int = 14
    max_dte: int = 45
    min_delta: float = .45
    max_delta: float = .70
    max_relative_spread: float = .10
    min_open_interest: int = 100
    min_option_volume: int = 10
    max_quote_wait_seconds: int = 30
    min_calibration_trades: int = 100
    min_calibration_days: int = 30


def valid_bar(r):
    vals = [r.get(k) for k in ('open', 'high', 'low', 'close', 'volume')]
    return (finite(*vals) and min(vals[:4]) > 0 and vals[4] > 0
            and r['low'] <= min(r['open'], r['close'])
            <= max(r['open'], r['close']) <= r['high'])


def stock_features(item, bars, daily, context, as_of, config=Config()):
    """Return a feature row or a visible reason for exclusion.

    Caller supplies an actual exchange session in the input manifest. No
    Canadian premarket price is inferred from the U.S. listing or CDR.
    """
    now = stamp(as_of)
    local = now.astimezone(NY)
    key = item['country'], item['symbol']
    signal = datetime.combine(local.date(), time(config.decision_minute // 60,
                                               config.decision_minute % 60), NY)
    if now < signal:
        return None, 'decision_bar_not_completed'
    if now-signal > timedelta(seconds=config.max_quote_wait_seconds):
        return None, 'decision_window_elapsed'
    if item.get('kind') != 'equity' or item.get('country') not in ('US', 'CA'):
        return None, 'not_classified_as_company_equity'
    if item.get('session_date') != local.date().isoformat():
        return None, 'missing_actual_exchange_session'
    if item.get('is_session') is not True:
        return None, 'not_a_verified_exchange_session'
    previous_session = previous_exchange_session(key[0], local.date().isoformat())
    if previous_session is None or item.get('previous_session_date') != previous_session:
        return None, 'invalid_exchange_session_or_previous_date'
    if item.get('currency') != {'US': 'USD', 'CA': 'CAD'}[key[0]]:
        return None, 'currency_mismatch'
    if context is None or stamp(context['known_at']) > signal:
        return None, 'missing_or_future_event_context'
    if context.get('date') != local.date().isoformat():
        return None, 'stale_context'
    if any(context.get(k) is not False for k in
           ('earnings_within_1d', 'major_news', 'corporate_action', 'halted')):
        return None, 'event_risk_or_unknown_status'
    if not finite(context.get('market_return'), context.get('sector_return')):
        return None, 'missing_market_sector_context'
    history = sorted((r for r in daily if (r['country'], r['symbol']) == key
                      and r['date'] < local.date().isoformat()), key=lambda r: r['date'])[-61:]
    if len(history) < 61 or len({r['date'] for r in history}) != len(history):
        return None, 'insufficient_or_duplicate_daily_history'
    if any(not valid_bar(r) for r in history):
        return None, 'invalid_daily_bar'
    if history[-1]['date'] != item.get('previous_session_date'):
        return None, 'missing_previous_session_close'
    # Prices must be on a common split basis known at signal time. Current
    # corporate-action days are excluded rather than inventing deliverables.
    if context.get('history_split_basis_verified') is not True:
        return None, 'unverified_historical_price_basis'
    earlier = []
    seen = set()
    for r in bars:
        if (r['country'], r['symbol']) != key:
            continue
        start = stamp(r['datetime'])
        if start.astimezone(NY).date() != local.date() or start + timedelta(minutes=5) > signal:
            continue
        if start.second or start.microsecond or start.minute % 5:
            return None, 'unaligned_five_minute_bar'
        if start in seen:
            return None, 'duplicate_intraday_bar'
        seen.add(start)
        if r.get('volume') == 0:
            continue  # A no-trade bar is not evidence of a tradable price.
        if not valid_bar(r):
            return None, 'invalid_intraday_bar'
        earlier.append((start, r))
    earlier.sort(key=lambda x: x[0])
    pre = [(t, r) for t, r in earlier if 240 <= t.astimezone(NY).hour * 60
           + t.astimezone(NY).minute < 570]
    regular = [(t, r) for t, r in earlier if 570 <= t.astimezone(NY).hour * 60
               + t.astimezone(NY).minute < config.decision_minute]
    expected = set(range(570, config.decision_minute, 5))
    if {t.astimezone(NY).hour * 60 + t.astimezone(NY).minute for t, _ in regular} != expected:
        return None, 'missing_regular_session_confirmation_bars'
    if len(pre) < 6 or signal - (pre[-1][0] + timedelta(minutes=5)) > timedelta(minutes=15):
        return None, 'missing_or_stale_premarket'
    previous = history[-1]['close']
    last_pre = pre[-1][1]['close']
    gap = last_pre / previous - 1
    atr = statistics.mean(max(b['high'] - b['low'], abs(b['high'] - a['close']),
                              abs(b['low'] - a['close'])) for a, b in zip(history[-15:-1], history[-14:]))
    if atr <= 0:
        return None, 'zero_atr'
    stretch = abs(last_pre - previous) / atr
    daily_liquidity = statistics.mean(r['close'] * r['volume'] for r in history[-20:])
    pre_liquidity = sum(r['close'] * r['volume'] for _, r in pre)
    if last_pre < config.min_price or daily_liquidity < config.min_daily_dollar_volume:
        return None, 'stock_liquidity'
    if pre_liquidity < config.min_premarket_dollar_volume:
        return None, 'premarket_liquidity'
    if not config.min_gap <= abs(gap) <= config.max_gap or not config.min_gap_atr <= stretch <= config.max_gap_atr:
        return None, 'gap_outside_fixed_range'
    direction = 1 if gap < 0 else -1
    first, last = regular[0][1], regular[-1][1]
    total_volume = sum(r['volume'] for _, r in regular)
    vwap = sum((r['high'] + r['low'] + r['close']) / 3 * r['volume']
               for _, r in regular) / total_volume
    reversal_atr = direction * (last['close'] - first['open']) / atr
    if reversal_atr <= 0 or direction * (last['close'] - vwap) <= 0:
        return None, 'no_completed_price_and_vwap_reversal'
    log_returns = [math.log(b['close'] / a['close']) for a, b in zip(history[-21:-1], history[-20:])]
    rv = statistics.stdev(log_returns) * math.sqrt(252)
    if rv <= 0:
        return None, 'zero_prior_realized_volatility'
    volume_proxy = total_volume / statistics.mean(r['volume'] for r in history[-20:])
    points = {
        'gap_stretch': 15 * bounded(stretch / 1.5),
        'premarket_liquidity': 10 * bounded(pre_liquidity / 1_000_000),
        'reversal_confirmation': 20 * bounded(reversal_atr / .5),
        'vwap_reclaim': 10 * bounded(direction * (last['close'] - vwap) / atr / .15),
        'opening_volume_proxy': 10 * bounded(volume_proxy / .05),
        'market_sector_alignment': 5 * bounded(.5 + direction *
            (context['market_return'] + context['sector_return']) / .02),
    }
    return {'version': VERSION, 'country': key[0], 'symbol': key[1],
            'currency': item['currency'], 'signal_time': signal.isoformat(),
            'right': 'call' if direction == 1 else 'put', 'gap': gap,
            'gap_atr': stretch, 'atr14': atr, 'prior_rv20': rv,
            'spot': last['close'], 'vwap_proxy': vwap, 'reversal_atr': reversal_atr,
            'prior_trend20_60': statistics.mean(r['close'] for r in history[-20:]) /
                                statistics.mean(r['close'] for r in history[-60:]) - 1,
            'opening_volume_fraction_of_prior_daily': volume_proxy,
            'premarket_dollar_volume': pre_liquidity, 'factor_points': points}, None


def choose_option(stock, quotes, as_of, config=Config()):
    signal, now = stamp(stock['signal_time']), stamp(as_of)
    rows = [q for q in quotes if (q['country'], q['symbol']) == (stock['country'], stock['symbol'])
            and signal < stamp(q['quote_timestamp']) <= min(now, signal + timedelta(seconds=config.max_quote_wait_seconds))]
    if not rows:
        return None, 'no_observed_post_signal_quote'
    # First post-signal chain only; never select a better price from later quotes.
    first = min(stamp(q['quote_timestamp']) for q in rows)
    choices = []
    for q in rows:
        if stamp(q['quote_timestamp']) != first or q['right'] != stock['right']:
            continue
        if q.get('currency') != stock['currency'] or q.get('standard_contract') is not True or q.get('multiplier') != 100:
            continue
        fields = ('bid', 'ask', 'bid_size', 'ask_size', 'delta', 'gamma', 'theta',
                  'vega', 'iv', 'open_interest', 'volume', 'underlying_price')
        if not finite(*(q.get(k) for k in fields)):
            continue
        if not 0 < q['bid'] <= q['ask'] or min(q['bid_size'], q['ask_size']) < 1:
            continue
        if q['open_interest'] < config.min_open_interest or q['volume'] < config.min_option_volume:
            continue
        if stamp(q['open_interest_known_at']) > first:
            continue
        spread = (q['ask'] - q['bid']) / q['ask']
        delta = q['delta'] if q['right'] == 'call' else -q['delta']
        if spread > config.max_relative_spread or not config.min_delta <= delta <= config.max_delta:
            continue
        if q['gamma'] < 0 or q['vega'] < 0 or q['theta'] > 0 or not 0 < q['iv'] <= 5:
            continue
        dte = (date.fromisoformat(q['expiration']) - first.astimezone(NY).date()).days
        if not config.min_dte <= dte <= config.max_dte:
            continue
        if abs(q['underlying_price'] / stock['spot'] - 1) > .005:
            continue
        # Theta is premium units per calendar day; vega is per 1 percentage point.
        if q.get('theta_unit') != 'per_calendar_day' or q.get('vega_unit') != 'per_volatility_point':
            continue
        points = dict(stock['factor_points'])
        points.update(option_liquidity=15 * bounded(1 - spread / config.max_relative_spread),
                      implied_vs_realized=10 * bounded(1.5 - q['iv'] / stock['prior_rv20']),
                      decay=5 * bounded(1 - abs(q['theta']) / q['ask'] / .05))
        row = {**stock, 'option_symbol': q['option_symbol'], 'entry_quote': q,
               'configuration_id': fingerprint(asdict(config)),
               'outcome_policy_id': outcome_policy_id(),
               'factor_points': points, 'setup_score': sum(points.values()),
               'score_is_probability': False,
               'greek_sensitivities': {'delta_per_contract': q['delta'] * 100,
                    'gamma_per_contract': q['gamma'] * 100,
                    'theta_per_day': q['theta'] * 100,
                    'vega_per_volatility_point': q['vega'] * 100}}
        choices.append(row)
    if not choices:
        return None, 'no_contract_passes_quote_and_greek_filters'
    return sorted(choices, key=lambda r: (-r['setup_score'], abs(abs(r['entry_quote']['delta']) - .6),
                                         r['option_symbol']))[0], None


def calibrate(candidate, history, config=Config()):
    """Past completed net option outcomes only; one sample per company/session.

    Same fixed version/country/direction/10-point score bucket. The interval
    is descriptive and does not account for cross-company day correlation.
    """
    cutoff = stamp(candidate['signal_time'])
    bucket = min(9, int(candidate['setup_score'] // 10))
    samples, seen = [], set()
    for r in sorted(history, key=lambda x: x['exit_time']):
        if r.get('version') != VERSION or r.get('country') != candidate['country'] or r.get('right') != candidate['right']:
            continue
        if (r.get('configuration_id') != candidate.get('configuration_id')
                or r.get('outcome_policy_id') != candidate.get('outcome_policy_id')):
            continue
        if not finite(r.get('setup_score'), r.get('net_option_return')):
            continue
        if min(9, int(r['setup_score'] // 10)) != bucket or r.get('complete_exit') is not True:
            continue
        entry, exit_ = stamp(r['entry_time']), stamp(r['exit_time'])
        # Embargo the entire decision day; no overlapping or same-day labels.
        if not entry < exit_ < cutoff or exit_.astimezone(NY).date() >= cutoff.astimezone(NY).date():
            continue
        identity = (r['country'], r['symbol'], entry.astimezone(NY).date())
        if identity in seen:
            continue
        seen.add(identity)
        samples.append(r)
    n = len(samples)
    days = len({stamp(r['entry_time']).astimezone(NY).date() for r in samples})
    if n < config.min_calibration_trades or days < config.min_calibration_days:
        return {'estimated_net_win_rate': None, 'samples': n, 'distinct_days': days,
                'sufficient_history': False, 'reason': 'Insufficient earlier net option outcomes'}
    p = sum(r['net_option_return'] > 0 for r in samples) / n
    z = 1.96
    center = (p + z*z/(2*n)) / (1+z*z/n)
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    mean = statistics.mean(r['net_option_return'] for r in samples)
    return {'estimated_net_win_rate': p, 'win_rate_wilson_95': [center-half, center+half],
            'samples': n, 'distinct_days': days, 'sufficient_history': True,
            'mean_net_option_return': mean,
            'paper_eligible': center-half > .5 and mean > 0,
            'note': 'Past conditional frequency, not a guaranteed probability; same-day trades are correlated.'}


def scan(payload, config=Config()):
    as_of = payload['as_of']
    coverage, candidates = Counter(), []
    contexts = {(r['country'], r['symbol']): r for r in payload['context']}
    keys = [(r['country'], r['symbol']) for r in payload['universe']]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate country/symbol in universe')
    # Index once for market-wide scanning, rather than repeatedly walking all bars.
    indexed = {}
    for name in ('bars', 'daily', 'quotes'):
        indexed[name] = defaultdict(list)
        for row in payload[name]:
            indexed[name][row['country'], row['symbol']].append(row)
    for item in payload['universe']:
        try:
            key = item['country'], item['symbol']
            stock, reason = stock_features(item, indexed['bars'][key], indexed['daily'][key],
                contexts.get(key), as_of, config)
            if reason:
                coverage[reason] += 1
                continue
            candidate, reason = choose_option(stock, indexed['quotes'][key], as_of, config)
            if reason:
                coverage[reason] += 1
                continue
            candidate['calibration'] = calibrate(candidate, payload.get('completed_history', []), config)
            candidate['decision'] = ('PAPER_CANDIDATE' if candidate['setup_score'] >= config.min_score
                and candidate['calibration'].get('paper_eligible') else 'NO TRADE')
            candidates.append(candidate)
            coverage['scored'] += 1
        except (KeyError, ValueError, TypeError, OverflowError):
            coverage['invalid_or_missing_input'] += 1
    return {'action': 'NO TRADE', 'version': VERSION, 'as_of': as_of,
            'parameters': asdict(config), 'universe_count': len(keys),
            'universe_by_country': dict(Counter(k[0] for k in keys)),
            'coverage_counts': dict(coverage),
            'candidates': sorted(candidates, key=lambda r: (-r['setup_score'], r['country'], r['symbol'])),
            'target_4_to_5_percent_monthly_validated': False,
            'note': 'Research/paper only. Missing coverage is reported, never filled with synthetic option prices.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--report', required=True)
    a = p.parse_args()
    result = scan(json.loads(Path(a.input).read_text()))
    Path(a.report).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'candidates'}, indent=2))
