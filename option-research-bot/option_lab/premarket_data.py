"""Reproducible public research-input downloads; no broker credentials.

Downloads are not a certification of source quality. Intraday import drops
all engineered features, including the macro lookahead found in the archive.
"""
import argparse
import csv
import hashlib
import json
import urllib.request
from pathlib import Path

DAILY_REV = 'de36a6a731b5ff46857146123d4624bed6e87419'
INTRADAY_REV = 'f17c0b0c3cf6a455994f93d6a85e76274172ab03'


def daily(output):
    url = f'https://huggingface.co/datasets/siddharthmb/stocks-ohlcv/resolve/{DAILY_REV}/ohlcv.csv?download=true'
    size, sha = 0, hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as r, Path(output).open('wb') as w:
        while block := r.read(8*1024*1024):
            w.write(block)
            sha.update(block)
            size += len(block)
    return {'dataset': 'siddharthmb/stocks-ohlcv', 'revision': DAILY_REV,
            'bytes': size, 'sha256': sha.hexdigest()}


def one_day(output, day='2024-01-02', max_bytes=2_000_000_000):
    month = day[:7]
    url = f'https://huggingface.co/datasets/fabhaus/equities_5m_stockprices/resolve/{INTRADAY_REV}/{month}.jsonl'
    request = urllib.request.Request(url, headers={'Range': f'bytes=0-{max_bytes-1}'})
    fields = ['datetime', 'symbol', 'open', 'high', 'low', 'close', 'volume']
    count, size, first, last, finished = 0, 0, None, None, False
    with urllib.request.urlopen(request, timeout=60) as r, Path(output).open('w') as w:
        writer = csv.DictWriter(w, fieldnames=fields)
        writer.writeheader()
        for line in r:
            size += len(line)
            if size > max_bytes:
                break
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                break  # The bounded byte range can end midway through a record.
            if row['date'] > day:
                finished = True
                break
            if row['date'] != day:
                continue
            first = first or row['datetime']
            last = row['datetime']
            writer.writerow({k: row[k] for k in fields})
            count += 1
    return {'dataset': 'fabhaus/equities_5m_stockprices', 'revision': INTRADAY_REV,
        'bytes_read': size, 'rows': count, 'first_timestamp': first,
        'last_timestamp': last, 'next_day_observed': finished,
        'discarded_all_engineered_macro_technical_fundamental_fields': True,
        'note': 'Reads a bounded prefix of a date-sorted month; later target dates may exceed the byte budget.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', choices=['daily', 'intraday-day'], required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--report', required=True)
    p.add_argument('--day', default='2024-01-02')
    a = p.parse_args()
    r = daily(a.out) if a.kind == 'daily' else one_day(a.out, a.day)
    Path(a.report).write_text(json.dumps(r, indent=2)+'\n')
    print(json.dumps(r, indent=2))
