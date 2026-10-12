"""Research-only intraday stock selector and option-NBBO adapter.

Opening-range/relative-volume filters are motivated by published stock research.
Waiting for a completed breakout bar and mapping to options are new adaptations,
not a replication of the authors' stock stop-order performance.
"""
import math
from collections import defaultdict
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

NY=ZoneInfo('America/New_York')


def timestamp(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Timestamp must include a time-zone offset')
    return result


def select_stocks(bars,daily_history,as_of,limit=20):
    now=timestamp(as_of);day=now.astimezone(NY).date()
    opens,by_symbol={},defaultdict(list)
    for r in bars:
        start=timestamp(r['datetime']);local=start.astimezone(NY)
        if start+timedelta(minutes=5)>now:continue
        if local.hour==9 and local.minute==30:
            key=(r['symbol'],local.date())
            if key in opens:raise ValueError('Duplicate opening-range bar')
            opens[key]=r
        if local.date()==day and 9*60+35<=local.hour*60+local.minute<16*60:
            by_symbol[r['symbol']].append(r)
    histories=defaultdict(list)
    for r in daily_history:
        d=datetime.fromisoformat(r['date']).date()
        if d<day:histories[r['symbol']].append(r)
    eligible=[]
    candidates=[]
    for (symbol,d),opening in opens.items():
        if d!=day:continue
        history=sorted(histories[symbol],key=lambda r:r['date'])[-15:]
        if len(history)<15:continue
        values=[r[k] for r in history for k in ('high','low','close','volume')]
        values += [opening[k] for k in ('open','high','low','close','volume')]
        if any(v is None or not math.isfinite(v) or v<0 for v in values):continue
        if opening['open']<=5:continue
        if sum(r['volume'] for r in history[-14:])/14<1_000_000:continue
        tr=[max(r['high']-r['low'],abs(r['high']-prev['close']),abs(r['low']-prev['close']))
            for prev,r in zip(history[:-1],history[1:])]
        atr=sum(tr)/14
        if atr<=.50:continue
        prior_opening=[opens.get((symbol,datetime.fromisoformat(r['date']).date())) for r in history[-14:]]
        if any(r is None for r in prior_opening):continue
        baseline=sum(r['volume'] for r in prior_opening)/14
        if baseline<=0:continue
        relative=opening['volume']/baseline
        if relative<1 or opening['close']==opening['open']:continue
        direction='call' if opening['close']>opening['open'] else 'put'
        level=opening['high'] if direction=='call' else opening['low']
        eligible.append((relative,symbol,opening,atr,direction,level))
    # Fix the opening-volume universe before observing later breakouts.
    ranked=sorted(eligible,key=lambda r:(-r[0],r[1]))[:limit]
    for relative,symbol,opening,atr,direction,level in ranked:
        for bar in sorted(by_symbol[symbol],key=lambda r:timestamp(r['datetime'])):
            if (bar['close']>level if direction=='call' else bar['close']<level):
                signal=timestamp(bar['datetime'])+timedelta(minutes=5)
                candidates.append({'symbol':symbol,'direction':direction,
                    'signal_time':signal.isoformat(),'relative_opening_volume':relative,
                    'atr14':atr,'opening_range_high':opening['high'],
                    'opening_range_low':opening['low'],'signal_stock_close':bar['close'],
                    'research_underlying_stop':bar['close']+(-.1*atr if direction=='call' else .1*atr)})
                break
    return candidates


def select_options(stock_candidates,quotes):
    """Select from the first eligible NBBO snapshot after the completed signal.

    This only proposes historical research contracts. No fills are inferred.
    """
    records=[]
    for stock in stock_candidates:
        signal=timestamp(stock['signal_time'])
        same=[q for q in quotes if q.get('underlying_symbol')==stock['symbol']]
        required=('bid','ask','bid_size','ask_size','quote_timestamp','delta','expiration','right','option_symbol')
        if not same or any(any(k not in q for k in required) for q in same):
            records.append({**stock,'contract':None,'reason':'No complete option NBBO/Greek snapshot'})
            continue
        eligible_times=[timestamp(q['quote_timestamp']) for q in same
                        if signal<=timestamp(q['quote_timestamp'])<=signal+timedelta(seconds=30)]
        if not eligible_times:
            records.append({**stock,'contract':None,'reason':'No synchronized quote within 30 seconds of signal'})
            continue
        first=min(eligible_times);choices=[]
        for q in same:
            if timestamp(q['quote_timestamp'])!=first or q['right']!=stock['direction']:continue
            bid,ask,delta=q['bid'],q['ask'],q['delta']
            if any(v is None or not math.isfinite(v) for v in (bid,ask,delta)):continue
            if bid<=0 or ask<bid or (ask-bid)/ask>.10 or q['bid_size']<1 or q['ask_size']<1:continue
            expiry=datetime.fromisoformat(q['expiration']).date()
            if not 14<=(expiry-first.astimezone(NY).date()).days<=30:continue
            if not .45<=abs(delta)<=.70:continue
            choices.append((abs(abs(delta)-.60)+(ask-bid)/ask,q['option_symbol'],q))
        if choices:
            q=min(choices,key=lambda v:v[:2])[2]
            records.append({**stock,'contract':q['option_symbol'],'quote_time':q['quote_timestamp'],
                            'quoted_ask':q['ask'],'reason':'Historical research selection only; fill unverified'})
        else:records.append({**stock,'contract':None,'reason':'No contract passes the fixed NBBO/expiry/delta screen'})
    return {'action':'NO TRADE','research_candidates':records,'target_5_percent_monthly_validated':False,
            'reason':'New intraday hypothesis; no verified account-level performance or live execution.'}


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bars',required=True,help='JSON list of 5-minute stock bars, including prior opening bars')
    p.add_argument('--daily',required=True,help='JSON list of earlier stock daily bars')
    p.add_argument('--quotes',required=True,help='JSON list of synchronized option NBBO and Greek snapshots')
    p.add_argument('--as-of',required=True,help='Timezone-aware timestamp')
    p.add_argument('--report',required=True)
    a=p.parse_args()
    stocks=select_stocks(json.loads(Path(a.bars).read_text()),json.loads(Path(a.daily).read_text()),a.as_of)
    result=select_options(stocks,json.loads(Path(a.quotes).read_text()))
    Path(a.report).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
