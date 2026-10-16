"""Read-only historical event retrieval and raw-stock import; no credentials.

Current earnings records are not a verified point-in-time calendar.
"""
import urllib.request,urllib.parse,json,concurrent.futures,datetime
from pathlib import Path
def sql(repo,q):
 u='https://www.dolthub.com/api/v1alpha1/post-no-preference/'+repo+'/master?'+urllib.parse.urlencode({'q':q})
 with urllib.request.urlopen(u,timeout=60) as f:x=json.load(f)
 if x['query_execution_status']!='Success':raise RuntimeError(x['query_execution_status'])
 return x['rows']
def task(v):
 kind,start,end=v;rows=[];offset=0
 while True:
  if kind=='earnings':q=f"SELECT act_symbol,date,`when` FROM earnings_calendar WHERE date >= '{start}' AND date < '{end}' ORDER BY date,act_symbol LIMIT 500 OFFSET {offset}";repo='earnings'
  else:q=f"SELECT * FROM split WHERE ex_date >= '{start}' AND ex_date < '{end}' ORDER BY ex_date,act_symbol LIMIT 500 OFFSET {offset}";repo='stocks'
  batch=sql(repo,q);rows.extend(batch)
  if len(batch)<500:break
  offset+=500
 return kind,rows

def fetch_events(output):
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 jobs=[]
 for y in (2023,2024,2025):
  for m in range(1,13):
   a=datetime.date(y,m,1);b=datetime.date(y+1,1,1) if m==12 else datetime.date(y,m+1,1)
   jobs.append(('earnings',a,b))
 for y in (2023,2024,2025):jobs.append(('splits',datetime.date(y,1,1),datetime.date(y+1,1,1)))
 data={'earnings':[],'splits':[]}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
  for kind,rows in ex.map(task,jobs):data[kind].extend(rows)
 for kind,rows in data.items():
  (out/(kind+'.json')).write_text(json.dumps(rows))
 return {kind:len(rows) for kind,rows in data.items()}


def import_stocks(source, output, symbols, start='2023-01-01'):
 import pyarrow as pa,pyarrow.csv as csv,pyarrow.compute as pc,pyarrow.parquet as pq
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 cols=['date','act_symbol','open','high','low','close','volume']
 reader=csv.open_csv(source,read_options=csv.ReadOptions(block_size=16*1024*1024),
  convert_options=csv.ConvertOptions(column_types={c:pa.string() if c in cols[:2] else pa.float64() for c in cols}))
 writer=None;n=0
 try:
  for b in reader:
   t=pa.Table.from_batches([b]);dates=t['date']
   keep=pc.and_(pc.greater_equal(dates,start),pc.less(dates,'2026-01-01'))
   keep=pc.and_(keep,pc.is_in(t['act_symbol'],value_set=pa.array(symbols)))
   t=t.filter(keep)
   if not len(t):continue
   if writer is None:writer=pq.ParquetWriter(out/'optionable_stocks.parquet',t.schema,compression='zstd')
   writer.write_table(t);n+=len(t)
 finally:
  if writer:writer.close()
 return n


if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description='Retrieve research event data and import raw underlying CSV')
 p.add_argument('--out',required=True);p.add_argument('--stock-csv');p.add_argument('--symbols')
 p.add_argument('--option-files',nargs='+',help='Derive unique symbols from option Parquet inputs')
 p.add_argument('--stock-start',default='2023-01-01');p.add_argument('--skip-events',action='store_true')
 a=p.parse_args()
 Path(a.out).mkdir(parents=True,exist_ok=True)
 if not a.skip_events:print(fetch_events(a.out))
 if a.stock_csv:
  if a.symbols:syms=json.loads(Path(a.symbols).read_text())
  elif a.option_files:
   import pyarrow.parquet as pq,pyarrow.compute as pc
   syms=sorted({s for path in a.option_files for s in pc.unique(pq.read_table(path,columns=['act_symbol'])['act_symbol']).to_pylist()})
   (Path(a.out)/'symbols.json').write_text(json.dumps(syms))
  else:p.error('--symbols or --option-files required for importing stocks')
  print('Stock rows',import_stocks(a.stock_csv,a.out,syms,a.stock_start))
