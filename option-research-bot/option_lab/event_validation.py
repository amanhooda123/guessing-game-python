"""Reprice recorded selections without searching for new profitable thresholds.

Check next-open stock liquidation after put assignment and doubled execution
frictions, plus a separate CAD-conversion sensitivity. Keeps missing outcomes.
"""
import argparse
import copy
import json
from datetime import date
from pathlib import Path
from .event_study import entry_cashflow,exit_cashflow,put_portfolio,summary,crossed_split,split_factor


def next_open_put(record, opens, next_session, splits, fee=.65, option_slip=.01,
                  stock_slip=.001, fx=0.):
    r=copy.deepcopy(record)
    if 'entry_quotes' not in r:return r
    flow=entry_cashflow(r['legs'],r['entry_quotes'],fee,option_slip,fx)
    key=r['legs'][0][0];symbol,expiry,strike,_=key
    r['entry_flow']=flow;r['cost']=strike*100*(1+fx)
    if record['status']!='matched':return r
    settle_day=date.fromisoformat(record['exit'])
    liquidation_day=next_session.get(settle_day)
    if liquidation_day is None:
        r['status']='missing_next_session';return r
    r['planned_exit']=liquidation_day.isoformat()
    if record['exit_spot']>=strike:
        pnl=flow
    else:
        price=opens.get((symbol,liquidation_day))
        if price is None:
            r['status']='missing_assignment_open';return r
        if crossed_split(symbol,date.fromisoformat(r['entry']),liquidation_day,splits):
            r['status']='nonstandard_contract';return r
        pnl=flow+price*100*(1-stock_slip)*(1-fx)-fee-strike*100*(1+fx)
        r['assignment_sale_open']=price
    r.update(exit=liquidation_day.isoformat(),pnl=pnl,return_fraction=pnl/r['cost'])
    return r


def validate(report, stocks, split_rows, stock_csv=None):
    import pyarrow.parquet as pq
    import exchange_calendars as xc
    import math
    c=xc.get_calendar('XNYS',start='2023-01-01',end='2026-01-15')
    sessions=[d.date() for d in c.sessions]
    nxt=dict(zip(sessions[:-1],sessions[1:]))
    opens={}
    for b in pq.ParquetFile(stocks).iter_batches(columns=['date','act_symbol','open']):
        for r in b.to_pylist():
            if r['open'] is not None and math.isfinite(r['open']) and r['open']>0:
                opens[r['act_symbol'],date.fromisoformat(r['date'])]=r['open']
    # An expiry at year end can deliver shares in early January. Those future
    # execution prices are outcomes, never inputs to the original selection.
    if stock_csv:
        import pyarrow as pa,pyarrow.csv as csv,pyarrow.compute as pc
        reader=csv.open_csv(stock_csv,read_options=csv.ReadOptions(block_size=16*1024*1024),
            convert_options=csv.ConvertOptions(include_columns=['date','act_symbol','open'],
                column_types={'date':pa.string(),'act_symbol':pa.string(),'open':pa.float64()}))
        for b in reader:
            t=pa.Table.from_batches([b]);d=t['date']
            t=t.filter(pc.and_(pc.greater_equal(d,'2026-01-01'),pc.less(d,'2026-01-16')))
            for r in t.to_pylist():
                if r['open'] is not None and math.isfinite(r['open']) and r['open']>0:
                    opens[r['act_symbol'],date.fromisoformat(r['date'])]=r['open']
    splits={(r['act_symbol'],date.fromisoformat(r['ex_date'])):split_factor(r) for r in split_rows}
    scenarios={}
    for name,fee,oslip,sslip,fx in [('usd_next_open',.65,.01,.001,0.),
                                  ('usd_double_cost',1.3,.02,.002,0.),
                                  ('cad_fx_next_open',.65,.01,.001,.015)]:
        results={};portfolios={}
        for kind,years in report['strategies'].items():
            results[kind]={}
            for year,data in years.items():
                records=[]
                for record in data['records']:
                    if kind=='cash_secured_put':
                        r=next_open_put(record,opens,nxt,splits,fee,oslip,sslip,fx)
                    else:
                        r=copy.deepcopy(record)
                        if 'entry_quotes' in r:
                            r['entry_flow']=entry_cashflow(r['legs'],r['entry_quotes'],fee,oslip,fx)
                            r['cost']=-r['entry_flow']
                        if r['status']=='matched':
                            flow=exit_cashflow(r['legs'],r['exit_quotes'],fee,oslip,fx)
                            r.update(exit_flow=flow,pnl=r['entry_flow']+flow)
                            r['return_fraction']=r['pnl']/r['cost']
                    records.append(r)
                s=summary(records,kind);s.pop('records');results[kind][year]=s
                if kind=='cash_secured_put':portfolios[year]=put_portfolio(records)
        scenarios[name]={'strategies':results,'put_portfolios':portfolios}
    return {'scenarios':scenarios,'action':'NO TRADE',
        'note':'Same selected contracts, not reoptimized. Assignment determined at expiry close; assigned shares sold at next-session open. Early assignment and after-hours exercise ambiguity remain unmodeled.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True);p.add_argument('--stocks',required=True)
    p.add_argument('--splits',required=True);p.add_argument('--report',required=True)
    p.add_argument('--stock-csv',help='Optional raw CSV to supply early-January assignment-sale opens')
    a=p.parse_args()
    r=validate(json.loads(Path(a.input).read_text()),a.stocks,json.loads(Path(a.splits).read_text()),a.stock_csv)
    Path(a.report).write_text(json.dumps(r,indent=2)+'\n')
    for name,scenario in r['scenarios'].items():
        print(name,{y:{k:v for k,v in d.items() if k!='filled_contracts'} for y,d in scenario['put_portfolios'].items()})
