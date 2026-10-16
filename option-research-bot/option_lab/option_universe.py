"""Read current official option directories; never use them as historical lists.

Cboe's four exchange underlying lists plus PHLX and MX are a broad current
directory, not an independently certified complete OPRA/Canadian history.
Raw directories remain local; reports contain coverage counts and hashes.
"""
import argparse
import csv
import hashlib
import io
import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.table, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.table = []
        elif tag == 'tr' and self.table is not None:
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = ''

    def handle_data(self, text):
        if self.cell is not None:
            self.cell += text

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(self.cell.split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def normalize(raw):
    merged = {}
    for r in raw:
        key = r['country'], r['symbol']
        if key not in merged:
            merged[key] = {**r, 'sources': [], 'option_roots': []}
        item = merged[key]
        # Explicit exchange classifications take priority over name inference.
        if r['source'].startswith('cboe_'):
            item['kind'] = r['kind']
        if r['source'] not in item['sources']:
            item['sources'].append(r['source'])
        if r['option_root'] not in item['option_roots']:
            item['option_roots'].append(r['option_root'])
    return [merged[k] for k in sorted(merged)]


def parse_sources(directory):
    rows, details = [], []
    directory = Path(directory)
    for path in sorted(directory.glob('*-underlying.csv')):
        text = path.read_text()
        n = 0
        for r in csv.DictReader(io.StringIO(text)):
            if not r.get('Symbol'):
                continue
            kind = 'equity' if r.get('Symbol Type') == 'Equity' else 'other'
            rows.append({'country': 'US', 'symbol': r['Symbol'], 'name': r['Company'],
                'currency': 'USD', 'kind': kind, 'option_root': r['Symbol'],
                'source': 'cboe_' + path.stem})
            n += 1
        details.append({'file': path.name, 'rows': n, 'sha256': hashlib.sha256(text.encode()).hexdigest()})
    path = directory / 'phlxoptions.csv'
    if path.exists():
        text = path.read_text()
        lines = text.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith('Company,Cycle,'))
        n = 0
        # PHLX has a two-row header: both symbol columns are named "Symbol".
        # Read columns by position so DictReader cannot silently overwrite one.
        for r in list(csv.reader(io.StringIO('\n'.join(lines[start:]))))[1:]:
            if len(r) < 4 or not r[2] or not r[3]:
                continue
            rows.append({'country': 'US', 'symbol': r[3], 'name': r[0],
                'currency': 'USD', 'kind': 'other' if r[1] == 'OTH' else 'equity',
                'option_root': r[2], 'source': 'nasdaq_phlx'})
            n += 1
        details.append({'file': path.name, 'rows': n, 'sha256': hashlib.sha256(text.encode()).hexdigest()})
    path = directory / 'mx.html'
    if path.exists():
        text = path.read_text()
        parser = Tables()
        parser.feed(text)
        if len(parser.tables) < 6:
            raise ValueError('MX table layout changed; inspect the source')
        # First six tables are equities, CDRs, CEFs, ETFs, currency, indices.
        # Weekly-options table repeats many of these and is intentionally ignored.
        for index, table in enumerate(parser.tables[:6]):
            if not table or 'Underlying' not in ' '.join(table[0]):
                raise ValueError('Unexpected MX header')
            for r in table[1:]:
                if len(r) != 3:
                    continue
                rows.append({'country': 'CA', 'symbol': r[2], 'name': r[0],
                    'currency': 'CAD', 'kind': 'equity' if index == 0 else 'other',
                    'option_root': r[1], 'source': 'montreal_exchange'})
        details.append({'file': path.name, 'rows': sum(len(t)-1 for t in parser.tables[:6]),
                        'sha256': hashlib.sha256(text.encode()).hexdigest()})
    return normalize(rows), details


def fetch(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    urls = {p+'-underlying.csv': 'https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/'+p+'-underlying.csv'
            for p in ('cone', 'opt', 'ctwo', 'exo')}
    urls.update({'phlxoptions.csv': 'https://www.nasdaqtrader.com/dynamic/SymDir/phlxoptions.csv',
                 'mx.html': 'https://www.m-x.ca/en/trading/data/options-list'})
    errors = {}
    for name, url in urls.items():
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                (directory/name).write_bytes(r.read())
        except (OSError, ValueError) as e:
            errors[name] = str(e)
    return errors


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', required=True)
    p.add_argument('--fetch', action='store_true')
    p.add_argument('--out', required=True, help='Local current directory JSON, not historical eligibility')
    p.add_argument('--report', required=True)
    a = p.parse_args()
    errors = fetch(a.directory) if a.fetch else {}
    rows, details = parse_sources(a.directory)
    report = {'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'unique_underlyings': len(rows), 'by_country': dict(Counter(r['country'] for r in rows)),
        'company_equities_by_country': dict(Counter(r['country'] for r in rows if r['kind'] == 'equity')),
        'sources': details, 'fetch_errors': errors, 'historical_eligibility_verified': False,
        'entire_market_completeness_verified': False,
        'note': 'Current exchange directories. Counts include ETFs/index/adjusted roots unless classified equity. Country is part of identity.'}
    Path(a.out).write_text(json.dumps(rows, indent=2)+'\n')
    Path(a.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
