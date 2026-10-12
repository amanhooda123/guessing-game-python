"""Measure the 5% monthly target without confusing trade returns with account NAV.

Closed-trade bookkeeping is diagnostic only. A target claim needs complete
month-end liquidation valuations, costs and correctly timed external flows.
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def month_number(month):
    year,number=map(int,month.split('-'))
    if not 1<=number<=12:raise ValueError('Invalid calendar month')
    return year*12+number-1


def metrics(returns,target=.05):
    if not returns:return {'months':0,'target_achieved':False}
    if any(not math.isfinite(r) or r<=-1 for r in returns):
        raise ValueError('Returns must be finite and account equity must remain positive')
    growth=math.prod(1+r for r in returns)
    return {'months':len(returns),'total_return':growth-1,
            'geometric_average_monthly_return':growth**(1/len(returns))-1,
            'arithmetic_average_monthly_return':sum(returns)/len(returns),
            'worst_month':min(returns),'best_month':max(returns),
            'losing_months':sum(r<0 for r in returns),
            'months_at_or_above_target':sum(r>=target-1e-12 for r in returns),
            'meets_geometric_average_target':growth**(1/len(returns))-1>=target-1e-12,
            'meets_every_month_target':min(returns)>=target-1e-12}


def marked_monthly_nav(rows,target=.05,minimum_months=24):
    """Evaluate supplied month-end net liquidation values, conditional on inputs.

    First row is the preceding month-end anchor. All entry/exit commissions,
    FX and funding must already be reflected in NAV. Only flows explicitly at
    month end are supported; intramonth flows require unitized daily NAV.
    """
    if len(rows)<2:raise ValueError('Provide an anchor plus month-end NAV records')
    rows=sorted(rows,key=lambda r:month_number(r['month']))
    returns=[]
    for before,after in zip(rows,rows[1:]):
        if month_number(after['month'])-month_number(before['month'])!=1:
            raise ValueError('Missing or duplicate calendar month')
        old,new=float(before['net_liquidation_value']),float(after['net_liquidation_value'])
        if not all(math.isfinite(n) and n>0 for n in (old,new)):
            raise ValueError('Invalid or nonpositive net liquidation value')
        flow=float(after.get('external_flow_at_month_end',0.))
        if not math.isfinite(flow):raise ValueError('Invalid external flow')
        if flow and after.get('flow_timing')!='month_end':
            raise ValueError('Intramonth flow needs daily unitized account NAV')
        returns.append((new-flow)/old-1)
    result=metrics(returns,target)
    complete=all(r.get('complete_position_marks') is True for r in rows)
    enough=len(returns)>=minimum_months
    result.update(target_monthly=target,complete_marks=complete,sufficient_months=enough,
                  historical_each_month_target_pass=complete and enough and result['meets_every_month_target'],
                  historical_average_target_pass=complete and enough and result['meets_geometric_average_target'],
                  monthly_returns=[{'month':r['month'],'return':v} for r,v in zip(rows[1:],returns)],
                  action='NO TRADE',
                  note='Conditional historical measurement; this does not verify input provenance, fresh validation or future returns.')
    return result


def realized_diagnostic(trade_report,validation,target=.05):
    results={}
    for allocation,years in validation['one_contract_allocations'].items():
        results[allocation]={}
        for year,portfolio in years.items():
            selected={(r['entry'],json.dumps(r['legs'])) for r in portfolio['filled_contracts']}
            pnl=defaultdict(float)
            for r in trade_report['years'][year]['records']:
                if r['status']=='matched' and (r['entry'],json.dumps(r['legs'])) in selected:
                    pnl[r['exit'][:7]]+=r['pnl']
            equity=portfolio['initial_capital'];months=[];returns=[]
            for number in range(1,13):
                month=f'{year}-{number:02}';value=pnl[month]/equity
                equity+=pnl[month];returns.append(value)
                months.append({'month':month,'realized_pnl':pnl[month],
                               'realized_cost_book_return':value,'realized_cost_book_equity':equity})
            d=metrics(returns,target)
            d.update(monthly_records=months,unresolved_positions=portfolio['unresolved'],
                     classification='Realized-cost bookkeeping, NOT fully marked account NAV',
                     target_validated=False)
            results[allocation][year]=d
    return {'action':'NO TRADE','target_monthly':target,
            'constant_target_compounded_annual_return':(1+target)**12-1,
            'existing_strategy_diagnostics':results,
            'target_achieved_or_validated':False,
            'reason':'Existing variants do not meet the monthly target and have no complete monthly liquidation-NAV series. Unresolved positions cannot be treated as profits.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trades');p.add_argument('--sizing');p.add_argument('--marked-nav')
    p.add_argument('--report',required=True);p.add_argument('--target',type=float,default=.05)
    a=p.parse_args()
    if not 0<a.target<1:p.error('Target must lie between 0 and 1')
    if a.marked_nav:r=marked_monthly_nav(json.loads(Path(a.marked_nav).read_text()),a.target)
    else:
        if not a.trades or not a.sizing:p.error('Provide --marked-nav or both --trades and --sizing')
        r=realized_diagnostic(json.loads(Path(a.trades).read_text()),
                             json.loads(Path(a.sizing).read_text()),a.target)
    Path(a.report).write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='existing_strategy_diagnostics'},indent=2))
