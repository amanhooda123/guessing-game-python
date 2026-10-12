"""Audit free intraday bars before treating them as tradable option quote history."""
import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def audit(path):
    count=0;symbols=set();days=set();expiry_years=Counter();columns=set();short_dated=0
    first=last=None;leaked_cpi=0
    known_cpi_release=datetime.fromisoformat('2024-02-13T13:30:00+00:00')
    for line in Path(path).open():
        r=json.loads(line);count+=1;columns.update(r)
        symbols.add(r.get('underlying_symbol'));days.add(r.get('date'))
        timestamp=datetime.fromisoformat(r['datetime'].replace('Z','+00:00'))
        first=min(first,timestamp) if first else timestamp
        last=max(last,timestamp) if last else timestamp
        expiry=datetime.fromisoformat(r['expiration_date'].replace('Z','+00:00')).date()
        expiry_years[str(expiry.year)]+=1
        if 0<=(expiry-timestamp.date()).days<=30:short_dated+=1
        if r.get('macro_cpi')==308.417 and timestamp<known_cpi_release:leaked_cpi+=1
    quotes={'bid','ask','bid_size','ask_size'}
    missing=sorted(quotes-columns)
    issues=[]
    if missing:issues.append('Trade OHLCV bars do not establish executable bid/ask with size')
    if short_dated==0:issues.append('Audited month has no 0–30 day contracts; unsuitable for short-dated intraday-strategy reproduction')
    if leaked_cpi:issues.append('January 2024 CPI appears before its February 13 publication; macro feature is not point-in-time')
    return {'rows':count,'symbols':len(symbols),'calendar_dates':len(days),
            'first_timestamp':first.isoformat(),'last_timestamp':last.isoformat(),
            'expiration_years':dict(expiry_years),'zero_to_30_day_rows':short_dated,
            'missing_nbbo_fields':missing,'known_cpi_lookahead_rows':leaked_cpi,
            'issues':issues,'preliminary_checks_passed':not issues,
            'approved_for_executable_option_backtest':False,
            'approval_note':'These checks cannot independently verify quote provenance, completeness or executable historical fills.',
            'scope':'Audited file only; does not infer coverage of uninspected months',
            'action':'NO TRADE'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True)
    p.add_argument('--report',required=True);a=p.parse_args();r=audit(a.input)
    Path(a.report).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
