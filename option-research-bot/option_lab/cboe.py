"""Stream licensed Cboe Option EOD Summary files into the research CSV format.

Uses the 15:45 ET quote (a tradable-time snapshot), not the EOD quote.
The free demonstration ZIP is a subset on one date and is not a backtest.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from .model import quote_to_csv_fields

REQUIRED = {
    "underlying_symbol", "quote_date", "root", "expiration", "strike",
    "option_type", "bid_size_1545", "bid_1545", "ask_size_1545",
    "ask_1545", "underlying_bid_1545", "underlying_ask_1545", "trade_volume",
    "delivery_code",
}


def _members(path: Path, sample_variant: str):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if len(names) > 1:
                names = [n for n in names if sample_variant in n]
                if len(names) != 1:
                    raise ValueError(f"Ambiguous ZIP CSV members in {path}; select one variant")
            if not names:
                raise ValueError(f"No CSV in {path}")
            with archive.open(names[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as source:
                yield names[0], csv.DictReader(source)
    else:
        with path.open(encoding="utf-8-sig", newline="") as source:
            yield path.name, csv.DictReader(source)


def convert(paths: list[str], out: str, symbols: set[str] | None = None,
            sample_variant: str = "cgi_or_historical") -> dict:
    """Write normalized options/stocks CSV and return a data-quality audit.

    Process one file at a time, so memory grows with daily stock count rather
    than the option universe. Duplicate dates across inputs fail closed.
    """
    destination = Path(out)
    destination.mkdir(parents=True, exist_ok=True)
    opts_path, stocks_path = destination / "cboe_options.csv", destination / "cboe_stocks.csv"
    selected = {s.upper() for s in symbols} if symbols else None
    counts: Counter[str] = Counter()
    by_symbol: Counter[str] = Counter()
    seen_dates: set[str] = set()
    with opts_path.open("w", newline="", encoding="utf-8") as option_file, \
            stocks_path.open("w", newline="", encoding="utf-8") as stock_file:
        options = csv.DictWriter(option_file, fieldnames=quote_to_csv_fields())
        stocks = csv.DictWriter(stock_file, fieldnames=["date", "symbol", "close"])
        options.writeheader(); stocks.writeheader()
        for path in paths:
            for member, rows in _members(Path(path), sample_variant):
                if not REQUIRED <= set(rows.fieldnames or []):
                    raise ValueError(f"Missing Cboe columns in {member}: {sorted(REQUIRED - set(rows.fieldnames or []))}")
                daily_spots: dict[tuple[str, str], float] = {}
                file_dates: set[str] = set()
                for row in rows:
                    counts["raw_rows"] += 1
                    symbol = row["underlying_symbol"].upper()
                    if selected is not None and symbol not in selected:
                        continue
                    if symbol.startswith("^") or row["root"].upper() != symbol or row["delivery_code"].strip():
                        counts["index_or_nonstandard"] += 1
                        continue
                    try:
                        day, expiry = date.fromisoformat(row["quote_date"]), date.fromisoformat(row["expiration"])
                        strike = float(row["strike"])
                        bid, ask = float(row["bid_1545"]), float(row["ask_1545"])
                        bsize, asize = int(row["bid_size_1545"]), int(row["ask_size_1545"])
                        under_bid = float(row["underlying_bid_1545"])
                        under_ask = float(row["underlying_ask_1545"])
                        volume = int(row["trade_volume"] or 0)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"Malformed Cboe value in {member}, row {counts['raw_rows']}") from exc
                    if (expiry <= day or strike <= 0 or row["option_type"] not in ("C", "P")
                            or bid <= 0 or ask < bid or bsize <= 0 or asize <= 0
                            or under_bid <= 0 or under_ask < under_bid):
                        counts["unusable_quote"] += 1
                        continue
                    day_text = day.isoformat()
                    if day_text in seen_dates:
                        raise ValueError(f"Duplicate date across input files: {day_text}")
                    file_dates.add(day_text)
                    spot_key = (day_text, symbol)
                    mid = (under_bid + under_ask) / 2
                    if spot_key in daily_spots and abs(daily_spots[spot_key] - mid) > .011:
                        raise ValueError(f"Conflicting underlying quote: {spot_key}")
                    daily_spots[spot_key] = mid
                    options.writerow({"date": day_text, "symbol": symbol, "expiration": expiry.isoformat(),
                                      "strike": strike, "right": "call" if row["option_type"] == "C" else "put",
                                      "bid": bid, "ask": ask, "volume": volume,
                                      "bid_size": bsize, "ask_size": asize})
                    by_symbol[symbol] += 1
                    counts["usable_rows"] += 1
                for (day, symbol), mid in sorted(daily_spots.items()):
                    stocks.writerow({"date": day, "symbol": symbol, "close": mid})
                seen_dates.update(file_dates)
    return {"source": "Cboe Option EOD Summary 15:45 ET NBBO", "dates": sorted(seen_dates),
            "symbols": dict(by_symbol.most_common()), "counts": dict(counts),
            "options_csv": str(opts_path), "stocks_csv": str(stocks_path),
            "limitations": "Stock close column is the 15:45 underlying mid, not a close. Trade volume may include later trades. NBBO is not a fill; spreads, FX, fees and omitted quotes affect results."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", required=True, help="Cboe daily CSV/ZIP files")
    parser.add_argument("--out", default="data/cboe")
    parser.add_argument("--symbols", nargs="+", help="Optional stock symbols; default all standard equities")
    parser.add_argument("--sample-variant", default="cgi_or_historical",
                        choices=["cgi_or_historical", "no_cgi_subscription"])
    args = parser.parse_args()
    print(json.dumps(convert(args.files, args.out, set(args.symbols) if args.symbols else None,
                             args.sample_variant), indent=2))


if __name__ == "__main__":
    main()
