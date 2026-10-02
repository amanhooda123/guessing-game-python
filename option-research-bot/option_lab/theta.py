"""Import licensed historical EOD reports from the user's local Theta Terminal v3."""
from __future__ import annotations

import csv
import json
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .model import quote_to_csv_fields

BASE = "http://127.0.0.1:25503"


def fetch(endpoint: str, parameters: dict) -> list[dict]:
    url = BASE + endpoint + "?" + urlencode({**parameters, "format": "json"})
    try:
        with urlopen(url, timeout=90) as response:
            result = json.load(response)
    except URLError as exc:
        raise RuntimeError("Theta Terminal v3 is unavailable on localhost:25503; start it with your own account") from exc
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected Theta response for {endpoint}: {str(result)[:200]}")
    return result


def download(symbol: str, start: date, end: date, directory: str | Path) -> tuple[Path, Path]:
    if end < start or (end - start).days > 366:
        raise ValueError("Choose a range of at most one year for the free data tier")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    options_path = directory / f"{symbol}_options.csv"
    stock_path = directory / f"{symbol}_stock.csv"
    stock = fetch("/v3/stock/history/eod", {"symbol": symbol, "start_date": start.strftime("%Y%m%d"),
                                            "end_date": end.strftime("%Y%m%d")})
    if not stock:
        raise RuntimeError("No stock EOD data returned")
    with stock_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "symbol", "close"])
        writer.writeheader()
        for row in stock:
            writer.writerow({"date": row["created"][:10], "symbol": symbol, "close": row["close"]})
    with options_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=quote_to_csv_fields())
        writer.writeheader()
        cursor, count = start, 0
        while cursor <= end:
            last = min(cursor + timedelta(days=6), end)
            rows = fetch("/v3/option/history/eod", {
                "symbol": symbol, "expiration": "*", "right": "call", "max_dte": 105,
                "strike_range": 20, "start_date": cursor.strftime("%Y%m%d"),
                "end_date": last.strftime("%Y%m%d")})
            for row in rows:
                writer.writerow({"date": row["created"][:10], "symbol": row.get("symbol", symbol),
                                 "expiration": row["expiration"], "strike": row["strike"],
                                 "right": row["right"], "bid": row["bid"], "ask": row["ask"],
                                 "volume": row.get("volume", 0), "bid_size": row.get("bid_size", 0),
                                 "ask_size": row.get("ask_size", 0)})
            count += len(rows)
            cursor = last + timedelta(days=1)
            if cursor <= end:
                time.sleep(3.2)  # stay below documented free rate of 20/minute
    if count == 0:
        raise RuntimeError("No option EOD quotes returned; check account entitlements and dates")
    return options_path, stock_path
