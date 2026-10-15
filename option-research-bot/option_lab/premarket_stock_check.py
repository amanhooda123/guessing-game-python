"""One-day raw premarket stock check, never an option-profitability claim."""
import argparse
import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from .premarket_reversal import NY, valid_bar


def run(bars_path, daily_path, session='2024-01-02'):
    import pandas as pd
    import exchange_calendars as xc
    calendar = xc.get_calendar('XNYS', start='2023-01-01', end='2024-12-31')
    previous_session = calendar.previous_session(session).strftime('%Y-%m-%d')
    raw = pd.read_csv(bars_path)
    total = len(raw)
    duplicates = int(raw.duplicated(['symbol', 'datetime'], keep=False).sum())
    raw = raw.drop_duplicates(['symbol', 'datetime'], keep=False)
    ts = pd.to_datetime(raw.datetime, utc=True).dt.tz_convert(NY)
    raw['minute'] = ts.dt.hour*60+ts.dt.minute
    raw['local_date'] = ts.dt.strftime('%Y-%m-%d')
    raw = raw.loc[raw.local_date == session]
    parts = []
    for chunk in pd.read_csv(daily_path, chunksize=500_000):
        parts.append(chunk.loc[(chunk.date >= '2023-01-01') & (chunk.date < session)])
    daily = pd.concat(parts).sort_values(['act_symbol', 'date'])
    histories = {s: g.tail(21).to_dict('records') for s, g in daily.groupby('act_symbol')}
    rows, skipped = [], Counter()
    for symbol, g in raw.groupby('symbol'):
        history = histories.get(symbol, [])
        if len(history) < 21 or any(not valid_bar(r) for r in history):
            skipped['missing_or_invalid_prior_daily_history'] += 1
            continue
        if history[-1]['date'] != previous_session:
            skipped['missing_previous_session_close'] += 1
            continue
        g = g.sort_values('minute')
        pre = g.loc[g.minute.between(240, 565) & (g.volume > 0)]
        required = g.loc[g.minute.isin([570, 575, 580, 590, 660])]
        if len(pre) < 6 or pre.iloc[-1].minute != 565 or len(required) != 5:
            skipped['missing_premarket_or_signal_or_exit_bars'] += 1
            continue
        pre_rows, required_rows = pre.to_dict('records'), required.to_dict('records')
        # Reject malformed or zero-volume observed bars; do not forward-fill.
        if any(not valid_bar(r) for r in pre_rows+required_rows):
            skipped['invalid_or_zero_volume_intraday'] += 1
            continue
        previous, p = history[-1]['close'], pre_rows[-1]['close']
        atr = statistics.mean(max(b['high']-b['low'], abs(b['high']-a['close']),
            abs(b['low']-a['close'])) for a, b in zip(history[-15:-1], history[-14:]))
        if (p < 5 or statistics.mean(r['close']*r['volume'] for r in history[-20:]) < 10_000_000
                or sum(r['close']*r['volume'] for r in pre_rows) < 100_000 or atr <= 0):
            skipped['liquidity_or_history_filter'] += 1
            continue
        gap = p/previous-1
        if not .005 <= abs(gap) <= .08 or not .25 <= abs(p-previous)/atr <= 2.5:
            skipped['gap_filter'] += 1
            continue
        direction = 1 if gap < 0 else -1
        first_three = required_rows[:3]
        volume = sum(r['volume'] for r in first_three)
        vwap = sum((r['high']+r['low']+r['close'])/3*r['volume'] for r in first_three)/volume
        if (direction*(first_three[-1]['close']-first_three[0]['open']) <= 0
                or direction*(first_three[-1]['close']-vwap) <= 0):
            skipped['no_price_and_vwap_confirmation'] += 1
            continue
        # Completed 09:40 bar produces a 09:45 signal. Stock proxy entry is
        # delayed until the 09:50 open; fixed exit is the 11:00 open.
        entry, exit_ = required_rows[3]['open'], required_rows[4]['open']
        ret = direction*(exit_/entry-1)
        rows.append({'symbol': symbol, 'direction': 'call_direction' if direction == 1 else 'put_direction',
            'premarket_gap': gap, 'entry_stock_price_0950': entry,
            'exit_stock_price_1100': exit_, 'gross_stock_return': ret})
    summary = {}
    for bps in (0, 5, 10, 20):
        net = [r['gross_stock_return']-bps/10_000 for r in rows]
        summary[str(bps)] = {'observations': len(net),
            'stock_direction_win_rate_after_cost': sum(v > 0 for v in net)/len(net) if net else None,
            'equal_weight_stock_return_for_this_one_day': statistics.mean(net) if net else None}
    return {'action': 'NO TRADE', 'classification': 'ONE-DAY PREMARKET STOCK CHECK ONLY',
        'date': session, 'source_rows': total, 'symbols': int(raw.symbol.nunique()),
        'duplicate_rows_removed': duplicates, 'qualified_stock_cases': len(rows),
        'exclusion_counts': dict(skipped), 'stock_cost_bps_sensitivity': summary,
        'option_returns_measured': False, 'confidence_calibrated': False,
        'monthly_target_validated': False, 'records': rows,
        'limitations': ['One session cannot establish monthly performance or stable win rate',
            'Stock OHLC observations do not supply option NBBO, Greeks or fills',
            'News, earnings, sector context, option liquidity and IV filters not tested in this stock-only check',
            'Public-source raw price provenance and corporate-action basis not independently verified',
            'All engineered macro/fundamental/technical fields were discarded; earlier audit found macro lookahead',
            'Fixed stock bps costs are sensitivities, not estimated option execution costs']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bars', required=True)
    p.add_argument('--daily', required=True)
    p.add_argument('--report', required=True)
    a = p.parse_args()
    r = run(a.bars, a.daily)
    Path(a.report).write_text(json.dumps(r, indent=2)+'\n')
    print(json.dumps({k: v for k, v in r.items() if k != 'records'}, indent=2))
