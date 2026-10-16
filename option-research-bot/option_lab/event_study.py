"""Research candidates from Reddit/earnings literature using direct stock prices.

Fixed calendar and earnings hypotheses plus fully collateralized put writing.
Earnings dates are retrospectively known, not verified point-in-time forecasts.
No strategy here can emit or execute a live order.
"""
from __future__ import annotations
import argparse
import bisect
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from .broad_study import _dates_and_rows, _key
from .recent_study import valid_quote


def split_factor(row):
    try:
        a,b=float(row['to_factor']),float(row['for_factor'])
        if a>0 and b>0 and math.isfinite(a/b):return a/b
    except (TypeError,ValueError,KeyError):pass
    return None


def stock_context(path, split_rows, snapshot_days):
    import pyarrow.parquet as pq
    splits = {(r['act_symbol'], date.fromisoformat(r['ex_date'])):split_factor(r)
              for r in split_rows}
    by_symbol = defaultdict(list)
    for b in pq.ParquetFile(path).iter_batches(columns=['date','act_symbol','close','volume']):
        for r in b.to_pylist():
            if r['close'] is not None and math.isfinite(r['close']) and r['close'] > 0:
                by_symbol[r['act_symbol']].append((date.fromisoformat(r['date']),
                                                 r['close'], r['volume'] or 0))
    features, closes = {}, {}
    for symbol, series in by_symbol.items():
        history, dollar_vol = [], []
        for day, close, volume in sorted(series):
            factor = splits.get((symbol, day), 1.)
            if factor is None:
                history,dollar_vol=[],[]
            elif factor != 1:
                history = [p / factor for p in history]
            closes[symbol, day] = close
            if day in snapshot_days and len(history) >= 200:
                rv = statistics.stdev([math.log(b/a) for a,b in
                                       zip(history[-21:-1], history[-20:])]) * math.sqrt(252)
                features[symbol,day] = {'spot':close,'rv':rv,
                    'up':close > statistics.mean(history[-200:]),
                    'dollar_volume':statistics.mean(dollar_vol[-20:]),
                    'momentum_12_1':history[-21]/history[-252]-1 if len(history)>=252 else None}
            history.append(close)
            dollar_vol.append(close * volume)
    return features, closes, splits


def crossed_split(symbol, first, last, splits):
    return any(s == symbol and first < d <= last for s,d in splits)


def event_lookup(rows):
    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r['act_symbol']].append(date.fromisoformat(r['date']))
    return {s:sorted(set(ds)) for s,ds in by_symbol.items()}


def next_event(symbol, day, events):
    days = events.get(symbol, [])
    i = bisect.bisect_right(days, day)
    return days[i] if i < len(days) else None


def selections(rows, day, features, events):
    """Rank all available symbols; no ticker list or option premium ceiling."""
    best, chains = {}, defaultdict(dict)
    def consider(name, rank, legs, event=None):
        value = (rank, tuple((_key(r), side) for r,side in legs), event)
        if name not in best or value[:2] < best[name][:2]:best[name] = value
    for r in rows:
        f = features.get((r['act_symbol'],day))
        if (not f or f['spot'] < 10 or f['dollar_volume'] < 10_000_000
                or f['rv'] <= 0 or not valid_quote(r)):
            continue
        if any(r[k] is None or not math.isfinite(r[k]) for k in ('vol','delta','strike')):
            continue
        if r['call_put'] not in ('Call','Put') or not 0 < r['vol'] <= 2:
            continue
        if (r['ask']-r['bid'])/r['ask'] > .10:continue
        dte = (date.fromisoformat(r['expiration'][:10])-day).days
        if (r['call_put']=='Put' and 30<=dte<=60 and -.30<=r['delta']<=-.15
                and f['up'] and r['vol']/f['rv'] >= 1.2 and r['strike'] < f['spot']):
            # Fixed delta preference, then yield; not fitted to returns.
            rank = abs(abs(r['delta'])-.20) - .1*r['bid']/r['strike']
            consider('cash_secured_put', rank, [(r,-1)])
        if abs(r['strike']/f['spot']-1)<=.02 and .35<=abs(r['delta'])<=.65 and 14<=dte<=90:
            chains[(r['act_symbol'],float(r['strike']))][(r['expiration'][:10],r['call_put'])] = r
    for (symbol,strike), chain in chains.items():
        expiries = sorted({expiry for expiry,_ in chain})
        event = next_event(symbol,day,events)
        f = features[symbol,day]
        for front in expiries:
            dte = (date.fromisoformat(front)-day).days
            # Pre-earnings long straddle: deliberately an event-timing
            # hypothesis, not the unconditional long-straddle rule.
            if (event and 3<=(event-day).days<=10 and event<date.fromisoformat(front)
                    and 14<=dte<=45 and (front,'Call') in chain and (front,'Put') in chain):
                c,p=chain[front,'Call'],chain[front,'Put']
                if (c['vol']+p['vol'])/(2*f['rv'])<=1.5:
                    rank=(c['vol']+p['vol'])/(2*f['rv'])+abs(strike/f['spot']-1)
                    consider('pre_earnings_straddle',rank,[(c,1),(p,1)],event)
            if not 14<=dte<=45:continue
            for back in expiries:
                back_dte=(date.fromisoformat(back)-day).days
                if not 45<=back_dte<=90 or (date.fromisoformat(back)-date.fromisoformat(front)).days<14:
                    continue
                for right in ('Call','Put'):
                    if (front,right) not in chain or (back,right) not in chain:continue
                    short,long=chain[front,right],chain[back,right]
                    ratio=short['vol']/long['vol']
                    if ratio<1.2 or long['ask']<=short['bid']:continue
                    rank=-ratio+abs(strike/f['spot']-1)
                    consider('term_structure_calendar',rank,[(long,1),(short,-1)])
                    if event and 3<=(event-day).days<=10 and event<date.fromisoformat(front):
                        consider('earnings_calendar',rank,[(long,1),(short,-1)],event)
    return {n:{'legs':legs,'event':event} for n,(_,legs,event) in best.items()}


def entry_cashflow(legs, quotes, fee=.65, slip=.01, fx=0.):
    flow=0.
    for (_,side),q in zip(legs,quotes):
        if side==1:flow-=q['ask']*100*(1+slip)*(1+fx)
        else:flow+=q['bid']*100*(1-slip)*(1-fx)
        flow-=fee
    return flow


def exit_cashflow(legs, quotes, fee=.65, slip=.01, fx=0.):
    return entry_cashflow([(k,-side) for k,side in legs],quotes,fee,slip,fx)


def settle_put(key, premium, spot, fee=.65, stock_slip=.001, fx=0.):
    """Expiry economics including immediate liquidation of assigned stock.

    This is a terminal-payoff approximation: American early assignment and the
    mismatch between expiry close and actual liquidation time are not modeled.
    """
    strike=key[2]
    if spot>=strike:return premium
    stock_purchase=strike*100*(1+fx)
    stock_sale=spot*100*(1-stock_slip)*(1-fx)-fee
    return premium + stock_sale-stock_purchase


def summary(records, kind):
    matched=[r for r in records if r['status']=='matched']
    entered=[r for r in records if 'cost' in r]
    returns=[r['return_fraction'] for r in matched]
    # Only puts have a genuinely finite terminal loss bound here. A calendar
    # can develop assignment/stock risk; missing exits cannot safely be given
    # a fabricated finite worst-case value.
    stress=([r.get('return_fraction',-1.) for r in entered]
            if kind=='cash_secured_put' else None)
    pnl=[r['pnl'] for r in matched]
    positives=sum(p for p in pnl if p>0);negatives=-sum(p for p in pnl if p<0)
    return {'selected':len(records),'entered':len(entered),'matched':len(matched),
        'status_counts':dict(Counter(r['status'] for r in records)),
        'match_fraction':len(matched)/len(records) if records else 0,
        'mean_return':statistics.mean(returns) if returns else None,
        'median_return':statistics.median(returns) if returns else None,
        'win_fraction':sum(p>0 for p in pnl)/len(pnl) if pnl else None,
        'total_matched_pnl':sum(pnl),
        'profit_factor':positives/negatives if negatives else None,
        'worst_matched_return':min(returns) if returns else None,
        'put_full_loss_stress_mean':statistics.mean(stress) if stress else None,
        'mean_required_capital':statistics.mean([r['cost'] for r in matched]) if matched else None,
        'symbols_matched':len({r['legs'][0][0][0] for r in matched}), 'records':records}


def put_portfolio(records, capital=100000., allocation=.20):
    """Realized terminal replay with cash collateral and integer contracts.

    Intermediate option marks are incomplete, so no daily Sharpe/MTM drawdown
    is reported. Unmatched held trades retain collateral and prevent a claim
    of complete terminal portfolio profit. Does not implement broker margin.
    """
    matched_entries=[r for r in records if 'cost' in r]
    timeline=defaultdict(lambda:{'entries':[],'exits':[]})
    for r in matched_entries:timeline[r['entry']]['entries'].append(r)
    cash,held,filled,skipped=capital,{},[],Counter()
    realized=[]
    for day in sorted(set(timeline)|{r['planned_exit'] for r in matched_entries}):
        for symbol,r in list(held.items()):
            if r['planned_exit']==day and r['status']=='matched':
                cash+=r['cost']+r['pnl'];realized.append(r['pnl']);del held[symbol]
        for r in timeline[day]['entries']:
            symbol=r['legs'][0][0][0]
            equity=cash+sum(p['cost'] for p in held.values())
            if symbol in held:skipped['symbol_already_held']+=1;continue
            if r['cost']>allocation*equity:skipped['position_allocation']+=1;continue
            if r['cost']>cash:skipped['collateral']+=1;continue
            cash-=r['cost'];held[symbol]=r;filled.append(r)
    unresolved=sum(r['cost'] for r in held.values())
    return {'initial_capital':capital,'position_allocation':allocation,
        'fills':len(filled),'resolved':len(realized),'unresolved':len(held),
        'skipped':dict(skipped),'realized_pnl':sum(realized),'ending_cash':cash,
        'ending_equity_unresolved_at_cost':cash+unresolved,
        'terminal_return_if_fully_resolved':cash/capital-1 if not held else None,
        'unresolved_full_loss_equity':cash,
        'worst_closed_trade_pnl':min(realized) if realized else None,
        'note':'Terminal-payoff model; no daily mark-to-market drawdown, interest or early assignment.',
        'filled_contracts':[{'entry':r['entry'],'legs':r['legs'],'status':r['status']} for r in filled]}


def run(paths, stocks, earnings, split_rows, fx=0.):
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS',start='2023-01-01',end='2025-12-31')
    sessions=[d.date() for d in cal.sessions];session_set=set(sessions)
    # Read only the date columns for the global observation calendar.
    import pyarrow.parquet as pq,pyarrow.compute as pc
    days=sorted({date.fromisoformat(d) for p in paths for d in
                 pc.unique(pq.read_table(p,columns=['date'])['date']).to_pylist()
                 if date.fromisoformat(d) in session_set})
    features,closes,splits=stock_context(stocks,split_rows,set(days))
    events=event_lookup(earnings)
    ix={d:i for i,d in enumerate(days)}
    names=('term_structure_calendar','earnings_calendar','pre_earnings_straddle','cash_secured_put')
    records={n:{2024:[],2025:[]} for n in names};pending=defaultdict(list)
    for day,rows in _dates_and_rows(paths,date(2024,1,1),date(2025,12,31)):
        if day not in ix:continue
        i=ix[day];due=pending.pop(i,[])
        needed={tuple(k) for r in due for k,_ in r['legs']}
        found={_key(r):r for r in rows if _key(r) in needed}
        for r in due:
            quotes=[found.get(tuple(k)) for k,_ in r['legs']]
            if not all(q is not None and valid_quote(q) for q in quotes):
                r['status']='missing_entry' if r['status']=='pending_entry' else 'missing_exit';continue
            if r['status']=='pending_entry':
                flow=entry_cashflow(r['legs'],quotes,fx=fx)
                if (r['kind']=='cash_secured_put' and flow<=0) or (r['kind']!='cash_secured_put' and flow>=0):
                    r['status']='invalid_entry_cashflow';continue
                r.update(entry=day.isoformat(),entry_flow=flow,entry_quotes=quotes)
                r['cost']=r['legs'][0][0][2]*100*(1+fx) if r['kind']=='cash_secured_put' else -flow
                r['status']='pending_exit'
                if r['kind']=='cash_secured_put':
                    symbol=r['legs'][0][0][0];target=date.fromisoformat(r['planned_exit'])
                    spot=closes.get((symbol,target))
                    if crossed_split(symbol,day,target,splits):r['status']='nonstandard_contract'
                    elif spot is None:r['status']='missing_underlying_exit'
                    else:
                        pnl=settle_put(r['legs'][0][0],flow,spot,fx=fx)
                        r.update(status='matched',exit=target.isoformat(),exit_spot=spot,
                                 pnl=pnl,return_fraction=pnl/r['cost'])
                else:pending[r['exit_index']].append(r)
            elif crossed_split(r['legs'][0][0][0],date.fromisoformat(r['entry']),day,splits):
                r['status']='nonstandard_contract'
            else:
                flow=exit_cashflow(r['legs'],quotes,fx=fx);pnl=r['entry_flow']+flow
                r.update(status='matched',exit=day.isoformat(),exit_quotes=quotes,
                         exit_flow=flow,pnl=pnl,return_fraction=pnl/r['cost'])
        if i+1>=len(days) or (days[i+1]-day).days>5:continue
        for kind,pick in selections(rows,day,features,events).items():
            legs=pick['legs'];entry_day=days[i+1];event=pick['event']
            if kind=='cash_secured_put':
                expiry=date.fromisoformat(legs[0][0][1])
                # Do not clip an expiry outside the dataset onto its last
                # session and fabricate an early terminal payoff.
                if expiry.year!=day.year or expiry>sessions[-1]:continue
                j=bisect.bisect_right(sessions,expiry)-1
                target=sessions[j];exit_i=None
            else:
                target=(event+timedelta(days=1) if event else entry_day+timedelta(days=5))
                exit_i=bisect.bisect_left(days,target)
                if exit_i>=len(days) or (days[exit_i]-target).days>5:continue
                target=days[exit_i]
                if event and entry_day>=event:continue
                if any(date.fromisoformat(k[1])<=target for k,_ in legs):continue
            if target.year!=day.year or target<=entry_day:continue
            r={'signal':day.isoformat(),'kind':kind,'legs':legs,'status':'pending_entry',
               'event':event.isoformat() if event else None,'planned_exit':target.isoformat(),
               'exit_index':exit_i}
            records[kind][day.year].append(r);pending[i+1].append(r)
        if day.day<=3:print('processing',day,flush=True)
    assert not pending,'Unresolved calendar quote match tasks'
    result={n:{str(y):summary(rs,n) for y,rs in ys.items()} for n,ys in records.items()}
    portfolios={str(y):put_portfolio(records['cash_secured_put'][y]) for y in (2024,2025)}
    return {'action':'NO TRADE','classification':'Exploratory repeated-history research',
        'assumptions':{'fx_per_cashflow':fx,'option_fee_per_leg':.65,'option_slippage':.01,
                       'stock_liquidation_slippage':.001},
        'stock_rows_features':len(features),'underlying_closes':len(closes),
        'earnings_events':sum(len(v) for v in events.values()),'splits':len(splits),
        'strategies':result,'put_portfolios':portfolios,
        'limitations':['No verified executable quote timestamp, quote sizes or option volume',
            'Historical earnings dates not verified as known before the signal',
            'American early assignment and actual settlement mechanics omitted',
            'No Canadian option contracts; available US source contains ETFs too',
            'Capital replay only for cash-secured puts; no daily MTM Sharpe/drawdown',
            'All selected nonstandard/missing trades remain in coverage and stress accounting',
            '2024 and 2025 repeatedly examined; future forward validation required']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files',nargs='+',required=True);p.add_argument('--stocks',required=True)
    p.add_argument('--earnings',required=True);p.add_argument('--splits',required=True)
    p.add_argument('--fx-fee',type=float,default=0.);p.add_argument('--report',required=True)
    a=p.parse_args()
    if not 0<=a.fx_fee<1:p.error('FX fee must lie in [0,1)')
    r=run(a.files,a.stocks,json.loads(Path(a.earnings).read_text()),
          json.loads(Path(a.splits).read_text()),a.fx_fee)
    Path(a.report).write_text(json.dumps(r,indent=2)+'\n')
    for n,ys in r['strategies'].items():print(n,{y:{k:v for k,v in d.items() if k!='records'} for y,d in ys.items()})
    print('portfolios',{y:{k:v for k,v in d.items() if k!='filled_contracts'} for y,d in r['put_portfolios'].items()})
