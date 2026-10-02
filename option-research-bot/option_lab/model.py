from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class Quote:
    day: date
    symbol: str
    expiry: date
    strike: float
    right: str
    bid: float
    ask: float
    volume: int
    bid_size: int
    ask_size: int

    @property
    def key(self) -> tuple:
        return (self.symbol, self.expiry, self.strike, self.right)

    @property
    def spread_fraction(self) -> float:
        return (self.ask - self.bid) / self.ask


def parse_day(value: str) -> date:
    return date.fromisoformat(value[:10])


def read_quotes(path: str | Path) -> list[Quote]:
    quotes = []
    with open(path, newline="", encoding="utf-8") as source:
        for line, row in enumerate(csv.DictReader(source), 2):
            try:
                day = parse_day(row.get("date") or row["created"])
                quote = Quote(day, row["symbol"].upper(), parse_day(row["expiration"]),
                              float(row["strike"]), row["right"].lower(), float(row["bid"]),
                              float(row["ask"]), int(float(row.get("volume") or 0)),
                              int(float(row.get("bid_size") or 0)),
                              int(float(row.get("ask_size") or 0)))
                if (quote.right not in ("call", "put") or quote.expiry <= day
                        or quote.bid < 0 or quote.ask <= 0 or quote.bid > quote.ask):
                    continue
                quotes.append(quote)
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"Bad options row {line}: {error}") from error
    if not quotes:
        raise ValueError("No valid option quotes")
    if len({(q.day, q.key) for q in quotes}) != len(quotes):
        raise ValueError("Duplicate daily contract quotes")
    return sorted(quotes, key=lambda q: (q.day, q.key))


def read_stocks(path: str | Path) -> dict[tuple[str, date], float]:
    prices = {}
    with open(path, newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            key = (row["symbol"].upper(), parse_day(row.get("date") or row["created"]))
            value = float(row["close"])
            if value <= 0 or key in prices:
                raise ValueError(f"Invalid or duplicate stock close: {key}")
            prices[key] = value
    return prices


def quote_to_csv_fields() -> list[str]:
    return ["date", "symbol", "expiration", "strike", "right", "bid", "ask",
            "volume", "bid_size", "ask_size"]
