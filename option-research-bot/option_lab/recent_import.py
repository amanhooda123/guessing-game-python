"""Stream a full-source CSV byte slice into year-partitioned research Parquet.

A slice must start before 2023 and end after 2025. Its first partial row is
discarded explicitly; importing a slice does not establish full-market coverage.
"""
import argparse
import json
from pathlib import Path

COLUMNS = ['date', 'act_symbol', 'expiration', 'strike', 'call_put', 'bid',
           'ask', 'vol', 'delta', 'gamma', 'theta', 'vega', 'rho']


def convert(source, output):
    import pyarrow as pa
    import pyarrow.csv as csv
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    types = {c: pa.string() if c in COLUMNS[:3] + ['call_put'] else pa.float64()
             for c in COLUMNS}
    reader = csv.open_csv(source, read_options=csv.ReadOptions(
        column_names=COLUMNS, skip_rows=1, block_size=16 * 1024 * 1024),
        convert_options=csv.ConvertOptions(column_types=types))
    writers, audit = {}, {}
    try:
        for batch in reader:
            table = pa.Table.from_batches([batch])
            for year in (2023, 2024, 2025):
                dates = table['date']
                keep = pc.and_(pc.greater_equal(dates, str(year) + '-01-01'),
                               pc.less(dates, str(year + 1) + '-01-01'))
                part = table.filter(keep)
                if not len(part):
                    continue
                if year not in writers:
                    writers[year] = pq.ParquetWriter(output / f'options_{year}.parquet',
                                                    part.schema, compression='zstd')
                    audit[year] = {'rows': 0, 'dates': set(), 'symbols': set()}
                writers[year].write_table(part)
                audit[year]['rows'] += len(part)
                audit[year]['dates'].update(pc.unique(part['date']).to_pylist())
                audit[year]['symbols'].update(pc.unique(part['act_symbol']).to_pylist())
    finally:
        for writer in writers.values():
            writer.close()
    summary = {str(y): {'rows': a['rows'], 'dates': len(a['dates']),
                        'symbols': len(a['symbols']), 'first': min(a['dates']),
                        'last': max(a['dates'])} for y, a in audit.items()}
    (output / 'coverage.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    print(json.dumps(convert(args.source, args.out), indent=2))
