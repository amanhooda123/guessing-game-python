"""Fixed monthly stock-momentum call-spread hypothesis, not a paper replication.

Rank 12-minus-one-month winners across available individual stocks. Buy a
same-expiry call vertical, account for all costs, and use an expiry payoff
approximation. No live signal or order is available.
"""
import argparse
import copy
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from .broad_study import _key
from .event_study import stock_context,valid_quote,entry_cashflow,crossed_split,summary,put_portfolio


def candidates(rows,day,features):
    chains=defaultdict(list)
    for r in rows:
        f=features.get((r['act_symbol'],day))
        if (not f or not f['up'] or f['spot']<10 or f['dollar_volume']<10_000_000
                or f['momentum_12_1'] is None or f['momentum_12_1']<=0):continue
        if not valid_quote(r) or r['call_put']!='Call':continue
        if r['delta'] is None or not math.isfinite(r['delta']):continue
        if (r['ask']-r['bid'])/r['ask']>.10:continue
        dte=(date.fromisoformat(r['expiration'][:10])-day).days
        if 45<=dte<=75:chains[r['act_symbol'],r['expiration'][:10]].append(r)
    best={}
    for (symbol,expiry),chain in chains.items():
        f=features[symbol,day]
        for long in chain:
            if not .55<=long['delta']<=.80:continue
            for short in chain:
                if not .20<=short['delta']<=.45 or short['strike']<1.02*f['spot']:continue
                width=short['strike']-long['strike'];debit=long['ask']-short['bid']
                if not .03*f['spot']<=width<=.20*f['spot'] or not .10*width<=debit<=.90*width:continue
                dte=(date.fromisoformat(expiry)-day).days
                score=abs(long['delta']-.65)+abs(short['delta']-.30)+.001*abs(dte-60)
                value=(score,((_key(long),1),(_key(short),-1)))
                if symbol not in best or value<best[symbol]:best[symbol]=value
    ranked=sorted(best,key=lambda s:(-features[s,day]['momentum_12_1'],s))[:5]
    return [{'symbol':s,'momentum':features[s,day]['momentum_12_1'],
             'legs':best[s][1]} for s in ranked]


def vertical_payoff(legs,spot):
    long,short=legs[0][0][2],legs[1][0][2]
    if not 0<long<short:raise ValueError('Invalid long call vertical strikes')
    return 100*(max(spot-long,0)-max(spot-short,0))


def run(paths,stocks,split_rows):
    import pyarrow as pa,pyarrow.parquet as pq,pyarrow.compute as pc
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS',start='2022-01-01',end='2026-03-01')
    sessions=[d.date() for d in cal.sessions];session_set=set(sessions)
    dates=sorted({d for p in paths for d in pc.unique(pq.read_table(p,columns=['date'])['date']).to_pylist()
                  if date.fromisoformat(d) in session_set})
    months={}
    for d in dates:months.setdefault(d[:7],d)
    signals={date.fromisoformat(d) for d in months.values()}
    features,closes,splits=stock_context(stocks,split_rows,signals)
    records={2024:[],2025:[]};pending={}
    # Need full chains only on monthly signal dates. On other dates retrieve
    # just the already-chosen exact contracts for entry, using Arrow filtering.
    for text_day in dates:
        day=date.fromisoformat(text_day)
        signal=day in signals
        needed={tuple(k) for r in pending.values() for k,_ in r['legs']}
        rows=[]
        if signal or pending:
            for path in paths:
                if str(day.year) not in Path(path).name:continue
                t=pq.read_table(path,filters=[('date','=',text_day)])
                if not signal and len(t):
                    t=t.filter(pc.is_in(t['act_symbol'],value_set=pa.array(sorted({k[0] for k in needed}))))
                rows.extend(t.to_pylist())
        found={_key(r):r for r in rows if signal or _key(r) in needed}
        for symbol,r in list(pending.items()):
            if (day-date.fromisoformat(r['signal'])).days>5:
                r['status']='missing_entry';del pending[symbol];continue
            q=[found.get(tuple(k)) for k,_ in r['legs']]
            if not all(x is not None and valid_quote(x) for x in q):
                r['status']='missing_entry';del pending[symbol];continue
            flow=entry_cashflow(r['legs'],q)
            width=(r['legs'][1][0][2]-r['legs'][0][0][2])*100
            if not 0<-flow<width:
                r['status']='invalid_entry_cashflow';del pending[symbol];continue
            r.update(entry=day.isoformat(),entry_quotes=q,entry_flow=flow,cost=-flow)
            expiry=date.fromisoformat(r['legs'][0][0][1]);spot=closes.get((symbol,expiry))
            if crossed_split(symbol,day,expiry,splits):r['status']='nonstandard_contract'
            elif spot is None:r['status']='missing_underlying_exit'
            else:
                payout=vertical_payoff(r['legs'],spot)
                # Conservative synthetic settlement haircut, two $0.65 fees.
                proceeds=payout*.999-1.3;pnl=flow+proceeds
                r.update(status='matched',exit=expiry.isoformat(),exit_spot=spot,
                         proceeds=proceeds,pnl=pnl,return_fraction=pnl/r['cost'])
            del pending[symbol]
        if not signal:continue
        for choice in candidates(rows,day,features):
            expiry=date.fromisoformat(choice['legs'][0][0][1])
            if expiry.year!=day.year:continue
            r={'kind':'momentum_call_spread','signal':text_day,'legs':choice['legs'],
               'momentum_12_1':choice['momentum'],'status':'pending_entry',
               'planned_exit':expiry.isoformat()}
            records[day.year].append(r);pending[choice['symbol']]=r
        print('monthly selection',text_day,len(records[day.year]),flush=True)
    for r in pending.values():r['status']='missing_entry'
    results={str(y):summary(rs,'momentum_call_spread') for y,rs in records.items()}
    portfolios={str(y):put_portfolio(rs,allocation=.10) for y,rs in records.items()}
    # All tested selections retained. Sensitivities reprice these contracts;
    # they do not choose the profitable subset or alter momentum thresholds.
    stress={}
    for label,fee,slip,fx in [('double_cost',1.3,.02,0.),('cad_fx',.65,.01,.015)]:
        stress[label]={}
        for y,rs in records.items():
            changed=copy.deepcopy(rs)
            for r in changed:
                if 'entry_quotes' not in r:continue
                flow=entry_cashflow(r['legs'],r['entry_quotes'],fee,slip,fx)
                r.update(entry_flow=flow,cost=-flow)
                if r['status']=='matched':
                    proceeds=vertical_payoff(r['legs'],r['exit_spot'])*(1-.001*(fee/.65))*(1-fx)-2*fee
                    r.update(proceeds=proceeds,pnl=flow+proceeds,return_fraction=(flow+proceeds)/-flow)
            d=summary(changed,'momentum_call_spread');d.pop('records')
            stress[label][str(y)]={'summary':d,'portfolio':put_portfolio(changed,allocation=.10)}
    return {'action':'NO TRADE','classification':'Exploratory options adaptation of stock momentum',
            'years':results,'capital_portfolios':portfolios,'cost_sensitivities':stress,
            'limitations':['Sparse next-observation quotes, no timestamps/sizes/option volume',
                'Available universe includes ETFs; complete delisting coverage not established',
                'Expiry payoff approximation omits American early assignment and actual stock exercise',
                'Missing/nonstandard outcomes cannot be labeled profits',
                'Repeated 2024/2025 history; not fresh validation',
                'No daily mark-to-market drawdown/Sharpe; terminal capital replay only']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files',nargs='+',required=True);p.add_argument('--stocks',required=True)
    p.add_argument('--splits',required=True);p.add_argument('--report',required=True)
    a=p.parse_args();r=run(a.files,a.stocks,json.loads(Path(a.splits).read_text()))
    Path(a.report).write_text(json.dumps(r,indent=2)+'\n')
    print({y:{k:v for k,v in d.items() if k!='records'} for y,d in r['years'].items()})
    print('portfolios',{y:{k:v for k,v in d.items() if k!='filled_contracts'} for y,d in r['capital_portfolios'].items()})
