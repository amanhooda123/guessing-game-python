"""Post hoc position-size sensitivity; retain losing variants and all costs.

The allocation sweep is explicitly research on repeatedly examined history.
A positive variant is not an untouched validation result or a live signal.
"""
import argparse
import copy
import json
import math
from collections import Counter,defaultdict
from pathlib import Path
from .event_study import entry_cashflow,put_portfolio
from .momentum_spreads import vertical_payoff


def integer_risk_replay(records,allocation,capital=100000.):
    entries=defaultdict(list)
    for r in records:
        if 'cost' in r:entries[r['entry']].append(r)
    days=sorted(set(entries)|{r['planned_exit'] for r in records if 'cost' in r})
    cash,held,realized,filled,skipped=capital,{},[],[],Counter()
    for day in days:
        for symbol,r in list(held.items()):
            if r['planned_exit']==day and r['status']=='matched':
                cash+=r['cost']+r['pnl'];realized.append(r['pnl']);del held[symbol]
        for unit in entries[day]:
            symbol=unit['legs'][0][0][0]
            if symbol in held:skipped['symbol_already_held']+=1;continue
            equity=cash+sum(r['cost'] for r in held.values())
            count=math.floor(min(allocation*equity,cash)/unit['cost'])
            if count<1:skipped['risk_or_cash']+=1;continue
            r=copy.deepcopy(unit);r['contracts']=count;r['cost']*=count
            if 'pnl' in r:r['pnl']*=count
            cash-=r['cost'];held[symbol]=r;filled.append(r)
    return {'initial_capital':capital,'position_allocation':allocation,
            'trade_entries':len(filled),'contracts':sum(r['contracts'] for r in filled),
            'unresolved':len(held),'realized_pnl':sum(realized),
            'terminal_return_if_fully_resolved':cash/capital-1 if not held else None,
            'unresolved_full_loss_equity':cash,'worst_closed_trade_pnl':min(realized) if realized else None,
            'skipped':dict(skipped)}


def reprice(records,fee,slip,fx):
    rs=copy.deepcopy(records)
    for r in rs:
        if 'entry_quotes' not in r:continue
        flow=entry_cashflow(r['legs'],r['entry_quotes'],fee,slip,fx)
        r.update(entry_flow=flow,cost=-flow)
        if r['status']=='matched':
            proceeds=vertical_payoff(r['legs'],r['exit_spot'])*(1-.001*(fee/.65))*(1-fx)-2*fee
            r.update(proceeds=proceeds,pnl=flow+proceeds,return_fraction=(flow+proceeds)/-flow)
    return rs


def validate(report):
    single={str(a):{y:put_portfolio(d['records'],allocation=a) for y,d in report['years'].items()}
            for a in (.01,.02,.05,.10)}
    equal_risk={str(a):{y:integer_risk_replay(d['records'],a) for y,d in report['years'].items()}
                for a in (.005,.01,.02)}
    scenarios={}
    for label,fee,slip,fx in [('base',.65,.01,0.),('double_cost',1.3,.02,0.),
                             ('fx_sensitivity',.65,.01,.015)]:
        scenarios[label]={y:put_portfolio(reprice(d['records'],fee,slip,fx),allocation=.01)
                          for y,d in report['years'].items()}
    return {'action':'NO TRADE',
        'classification':'Post hoc inspection of 7 position-sizing variants after reviewing the same 2024/2025 history',
        'one_contract_allocations':single,'integer_equal_risk_allocations':equal_risk,
        'one_percent_cost_scenarios':scenarios,
        'candidate':'One contract, maximum 1% of illustrative USD100,000 account equity per new spread',
        'limitations':['Selected after outcome review; no fresh or multiple-testing-adjusted evidence',
            'Only 12 and 24 filled trades at the candidate sizing; not independent replicated annual samples',
            'Not scale invariant: changing account size or integer-contract sizing changes selections',
            'Double-cost scenario nearly eliminates the 2025 gain; FX sensitivity loses in 2025',
            'FX sensitivity applies conversion to net synthetic payout, not gross American assignment cashflows',
            'Broker spread trading requires USD accounts; actual exercise and early assignment remain omitted',
            'No daily option mark-to-market drawdown or Sharpe; idle cash earns zero in the model']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True);p.add_argument('--report',required=True)
    a=p.parse_args();r=validate(json.loads(Path(a.input).read_text()))
    Path(a.report).write_text(json.dumps(r,indent=2)+'\n')
    for name,ys in r['one_percent_cost_scenarios'].items():
        print(name,{y:d['terminal_return_if_fully_resolved'] for y,d in ys.items()})
