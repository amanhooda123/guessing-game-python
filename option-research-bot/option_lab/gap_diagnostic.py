"""Opening-gap stock diagnostic, NOT a premarket or options backtest.

Fixed filters use prior data only. Current option directories never filter
historical rows. The portfolio is an equal-weight 1x long/short stock proxy
with a stated round-trip cost, without intraday confirmation or borrow fees.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def run(source, start='2024-01-01', end='2025-12-31', cost_bps=20):
    import numpy as np
    import pandas as pd
    import exchange_calendars as xc
    chunks = []
    source_count = 0
    for df in pd.read_csv(source, chunksize=500_000):
        source_count += len(df)
        chunks.append(df.loc[(df.date >= '2023-01-01') & (df.date <= end)].copy())
    data = pd.concat(chunks, ignore_index=True)
    raw_count = len(data)
    duplicates = int(data.duplicated(['date', 'act_symbol'], keep=False).sum())
    # Ambiguous duplicate observations are all removed, never selected by return.
    data = data.drop_duplicates(['date', 'act_symbol'], keep=False)
    valid = ((data[['open', 'high', 'low', 'close', 'volume']] > 0).all(axis=1)
             & (data.high >= data[['open', 'close']].max(axis=1))
             & (data.low <= data[['open', 'close']].min(axis=1)))
    invalid = int((~valid).sum())
    data = data.loc[valid].sort_values(['act_symbol', 'date'])
    cal = xc.get_calendar('XNYS', start='2022-12-01', end=end)
    sessions = [x.strftime('%Y-%m-%d') for x in cal.sessions]
    session_id = {d: i for i, d in enumerate(sessions)}
    data = data.loc[data.date.isin(session_id)].copy()
    data['session_id'] = data.date.map(session_id)
    groups = data.groupby('act_symbol', sort=False)
    data['prev_close'] = groups.close.shift()
    data['prev_session_id'] = groups.session_id.shift()
    data['dollar_volume'] = data.close * data.volume
    data['previous_dollar_volume20'] = groups.dollar_volume.transform(lambda x: x.shift().rolling(20).mean())
    data['tr'] = np.maximum(data.high-data.low,
                           np.maximum(abs(data.high-data.prev_close), abs(data.low-data.prev_close)))
    data['atr14'] = data.groupby('act_symbol', sort=False).tr.transform(lambda x: x.shift().rolling(14).mean())
    data['gap'] = data.open / data.prev_close - 1
    data['gap_atr'] = abs(data.open-data.prev_close)/data.atr14
    eligible = data.loc[(data.date >= start) & (data.date <= end)
        & (data.session_id-data.prev_session_id == 1)
        & (data.open >= 5) & (data.previous_dollar_volume20 >= 10_000_000)
        & data.gap.abs().between(.005, .08) & data.gap_atr.between(.25, 2.5)].copy()
    eligible['direction'] = np.where(eligible.gap < 0, 1, -1)
    eligible['gross_stock_return'] = eligible.direction * (eligible.close/eligible.open-1)
    eligible['net_proxy_return'] = eligible.gross_stock_return - cost_bps / 10_000
    by_day = eligible.groupby('date').net_proxy_return.mean()
    gross_by_day = eligible.groupby('date').gross_stock_return.mean()
    results = {}
    for year in sorted({d[:4] for d in sessions if start <= d <= end}):
        days = [d for d in sessions if start <= d <= end and d.startswith(year)]
        rows = eligible.loc[eligible.date.str.startswith(year)]
        ret = by_day.reindex(days, fill_value=0)
        gross = gross_by_day.reindex(days, fill_value=0)
        nav = (1+ret).cumprod()
        monthly = []
        for month in sorted({d[:7] for d in days}):
            values = ret.loc[[d for d in days if d.startswith(month)]]
            monthly.append({'month': month, 'stock_proxy_return': float((1+values).prod()-1)})
        counts = len(rows)
        results[year] = {
            'stock_observations': counts, 'symbols': int(rows.act_symbol.nunique()),
            'sessions_with_opportunities': int(rows.date.nunique()),
            'gross_direction_win_rate': float((rows.gross_stock_return > 0).mean()) if counts else None,
            'after_cost_stock_win_rate': float((rows.net_proxy_return > 0).mean()) if counts else None,
            'mean_gross_stock_trade_return': float(rows.gross_stock_return.mean()) if counts else None,
            'mean_net_stock_trade_return': float(rows.net_proxy_return.mean()) if counts else None,
            'equal_weight_1x_stock_proxy_annual_return': float(nav.iloc[-1]-1),
            'gross_stock_proxy_annual_return': float((1+gross).prod()-1),
            'stock_proxy_monthly_equivalent': float(nav.iloc[-1]**(1/12)-1),
            'stock_proxy_daily_drawdown': float((nav/nav.cummax().clip(lower=1)-1).min()),
            'months_at_least_4_percent': sum(r['stock_proxy_return'] >= .04 for r in monthly),
            'months_at_least_5_percent': sum(r['stock_proxy_return'] >= .05 for r in monthly),
            'monthly': monthly,
            'directions': {name: {'observations': int(len(x)),
                'gross_win_rate': float((x.gross_stock_return > 0).mean()),
                'mean_gross_return': float(x.gross_stock_return.mean())}
                for name, x in [('gap_down_long', rows.loc[rows.direction == 1]),
                                ('gap_up_short', rows.loc[rows.direction == -1])] if len(x)}
        }
        # Preserve the whole cost sensitivity, not only the cost that looks best.
        sensitivity = {}
        for bps in (0, 5, 10, 20):
            adjusted = gross - bps/10_000
            # Sessions without a position incur no trading cost.
            adjusted.loc[~adjusted.index.isin(by_day.index)] = 0
            sensitivity[str(bps)] = {
                'stock_proxy_annual_return': float((1+adjusted).prod()-1),
                'mean_stock_trade_return': float(rows.gross_stock_return.mean()-bps/10_000),
                'stock_trade_win_rate': float((rows.gross_stock_return > bps/10_000).mean()),
                'months_at_least_4_percent': sum(float((1+adjusted.loc[
                    [d for d in days if d.startswith(month)]]).prod()-1) >= .04
                    for month in sorted({d[:7] for d in days}))}
        results[year]['round_trip_stock_cost_bps_sensitivity'] = sensitivity
    return {'action': 'NO TRADE', 'classification': 'OPENING-GAP STOCK PROXY ONLY',
        'source_rows_scanned': source_count, 'rows_2023_to_end_before_cleaning': raw_count,
        'duplicate_rows_removed': duplicates, 'invalid_ohlcv_rows_removed': invalid,
        'historical_symbols_observed': int(data.act_symbol.nunique()),
        'source_revision': 'de36a6a731b5ff46857146123d4624bed6e87419',
        'parameters': {'gap': [.005, .08], 'gap_atr': [.25, 2.5], 'min_price': 5,
            'prior_daily_dollar_volume20': 10_000_000, 'round_trip_stock_cost_bps': cost_bps,
            'weighting': 'Equal capital per available signal each session, 1x gross stock notional'},
        'years': results, 'option_performance_measured': False,
        'premarket_performance_measured': False, 'target_validated': False,
        'limitations': ['Opening prices replace premarket prices in this diagnostic only',
            'Includes available stock/ETF symbols without verified historical option eligibility',
            'Raw source provenance, opening auction executability and complete coverage not independently verified',
            'Dividends, symbol changes and small corporate-action gaps are not fully adjusted',
            'Short-stock availability, borrow fees, taxes and market impact omitted',
            'Fixed bps stock costs cannot represent option bid/ask or IV changes',
            'Earlier studies repeatedly examined these years; no untouched strategy holdout']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stocks', required=True)
    p.add_argument('--report', required=True)
    p.add_argument('--cost-bps', type=float, default=20)
    a = p.parse_args()
    if a.cost_bps < 0 or a.cost_bps > 1000:
        p.error('Cost must be between 0 and 1000 bps')
    r = run(a.stocks, cost_bps=a.cost_bps)
    Path(a.report).write_text(json.dumps(r, indent=2)+'\n')
    print(json.dumps({k: v for k, v in r.items() if k != 'years'}, indent=2))
