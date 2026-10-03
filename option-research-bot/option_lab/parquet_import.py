"""Convert third-party research Parquet to the compact CSV schema; optional pyarrow."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .model import quote_to_csv_fields


def convert(options: list[str], underlying: str, out: str, symbol: str) -> tuple[Path, Path]:
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("Install optional dependency: python -m pip install pyarrow") from error
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    stock = pq.read_table(underlying, columns=["symbol", "date", "close"]).to_pylist()
    stock = [r for r in stock if r["symbol"].upper() == symbol.upper()]
    spots = {(r["symbol"].upper(), str(r["date"])[:10]): float(r["close"]) for r in stock}
    if not spots:
        raise ValueError("Underlying prices missing")
    stock_path = folder / f"{symbol}_stock.csv"
    with stock_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "symbol", "close"])
        writer.writeheader()
        for row in sorted(stock, key=lambda r: r["date"]):
            writer.writerow({"date": row["date"], "symbol": symbol, "close": row["close"]})
    # Build the historical contract universe from all dates, then include every
    # available quote for selected contracts (including later ITM exit quotes).
    paths = [Path(p) for p in options]
    keys = set()
    for path in paths:
        table = pq.read_table(path, columns=["contract_id", "symbol", "date", "expiration", "strike",
                                             "type", "bid", "ask", "volume", "bid_size", "ask_size"])
        for r in table.to_pylist():
            day, expiry = str(r["date"])[:10], str(r["expiration"])[:10]
            spot = spots.get((symbol.upper(), day))
            if not spot or r["symbol"].upper() != symbol.upper() or r["type"].lower() != "call":
                continue
            from datetime import date
            dte = (date.fromisoformat(expiry) - date.fromisoformat(day)).days
            if (45 <= dte <= 100 and 1 <= r["strike"] / spot <= 1.12
                    and 0 < (r["ask"] or 0) <= 2.0 and 0 < (r["bid"] or 0) <= r["ask"]
                    and (r["volume"] or 0) >= 10 and (r["bid_size"] or 0) > 0
                    and (r["ask_size"] or 0) > 0):
                keys.add((r["contract_id"], expiry, float(r["strike"])))
    if not keys:
        raise ValueError("No affordable entry contracts found in source files")
    options_path = folder / f"{symbol}_options.csv"
    count, suspicious = 0, 0
    with options_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=quote_to_csv_fields())
        writer.writeheader()
        for path in paths:
            table = pq.read_table(path, columns=["contract_id", "symbol", "date", "expiration", "strike",
                                                 "type", "bid", "ask", "volume", "bid_size", "ask_size"])
            for r in table.to_pylist():
                day, expiry = str(r["date"])[:10], str(r["expiration"])[:10]
                if (r["contract_id"], expiry, float(r["strike"])) not in keys:
                    continue
                spot = spots.get((symbol.upper(), day))
                bid, ask = r["bid"], r["ask"]
                if not spot or bid is None or ask is None or bid < 0 or ask <= 0 or bid > ask:
                    suspicious += 1
                    continue
                # A call bid materially below intrinsic signals stale/misaligned data.
                if bid + .15 < max(0, spot - r["strike"]):
                    suspicious += 1
                    continue
                writer.writerow({"date": day, "symbol": symbol, "expiration": expiry,
                                 "strike": r["strike"], "right": "call", "bid": bid, "ask": ask,
                                 "volume": r["volume"] or 0, "bid_size": r["bid_size"] or 0,
                                 "ask_size": r["ask_size"] or 0})
                count += 1
    manifest = {"source": "third-party research Parquet (verify provenance independently)",
                "symbol": symbol, "rows": count, "excluded_suspicious_quotes": suspicious,
                "files_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [*paths, Path(underlying)]}}
    (folder / f"{symbol}_import_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return options_path, stock_path
