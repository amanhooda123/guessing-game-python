"""Exploratory, quote-crossing bull put spread replay. Never places orders."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Leg:
    bid: float
    ask: float
    volume: int
    bid_size: int
    ask_size: int


def load_quotes(paths: list[str], stock_path: str, symbol: str) -> tuple[dict, dict]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: python -m pip install pyarrow") from exc
    with open(stock_path, newline="", encoding="utf-8") as handle:
        spots = {date.fromisoformat(r["date"]): float(r["close"])
                 for r in csv.DictReader(handle) if r["symbol"] == symbol}
    quotes = defaultdict(dict)
    excluded = defaultdict(int)
    fields = ["symbol", "date", "expiration", "strike", "type", "bid", "ask",
              "volume", "bid_size", "ask_size"]
    for path in paths:
        reader = pq.ParquetFile(path)
        for batch in reader.iter_batches(batch_size=50000, columns=fields):
            for r in batch.to_pylist():
                if r["symbol"] != symbol or r["type"] != "put":
                    continue
                day, expiry = date.fromisoformat(r["date"]), date.fromisoformat(r["expiration"])
                spot = spots.get(day)
                if not spot or not 2 <= (expiry - day).days <= 60 or not .75 <= r["strike"] / spot <= 1.05:
                    continue
                bid, ask = r["bid"], r["ask"]
                if (bid is None or ask is None or bid < 0 or ask <= 0 or bid > ask
                        or bid + .15 < max(0, r["strike"] - spot)):
                    excluded["bad_quote"] += 1
                    continue
                quotes[day][(expiry, float(r["strike"]))] = Leg(
                    bid, ask, r["volume"] or 0, r["bid_size"] or 0, r["ask_size"] or 0)
    return (spots, quotes), dict(excluded)


def replay(spots: dict, quotes: dict, start: date, end: date, capital: float = 200.) -> dict:
    """Monday 30-50 DTE, ~2% OTM, $1-wide, trend filter, crossed quotes.

    All parameters were set before this spread study. No optimization occurs here.
    """
    if capital <= 0:
        raise ValueError("capital must be positive")
    history = sorted(spots)
    trend = set()
    for i in range(200, len(history)):
        d = history[i]
        if spots[d] > sum(spots[k] for k in history[i - 200:i]) / 200:
            trend.add(d)
    days = sorted(d for d in quotes if start <= d <= end)
    if not days:
        raise ValueError("No quotes in interval")
    cash, position, pending, trades, curve = capital, None, None, [], []
    missed = defaultdict(int)
    anomalous_marks = 0
    for i, day in enumerate(days):
        chain = quotes[day]
        if position and position.get("close"):
            key1, key2 = position["legs"]
            short, long = chain.get(key1), chain.get(key2)
            if not short or not long or not short.ask_size or not long.bid_size:
                raise ValueError(f"Missing tradable exit spread quote on {day}: {key1} {key2}")
            debit = max(0., short.ask - long.bid) * 100
            if debit > (key1[1] - key2[1]) * 100 + .001:
                anomalous_marks += 1
            cash += position["reserve"] + position["credit"] - debit
            trades.append({"entry": position["entry"].isoformat(), "exit": day.isoformat(),
                           "expiry": key1[0].isoformat(), "short_strike": key1[1],
                           "long_strike": key2[1], "credit": round(position["credit"], 2),
                           "debit": round(debit, 2), "pnl": round(position["credit"] - debit, 2),
                           "reason": position["close"]})
            position = None
        if not position and pending:
            key1, key2 = pending
            pending = None
            short, long = chain.get(key1), chain.get(key2)
            if not short or not long or min(short.bid_size, long.ask_size) <= 0:
                missed["missing_next_day_entry"] += 1
            else:
                credit = (short.bid - long.ask) * 100
                width = (key1[1] - key2[1]) * 100
                reserve = width - credit
                if 10 <= credit < width and reserve <= min(cash, capital * .5):
                    cash -= reserve
                    position = {"legs": (key1, key2), "credit": credit,
                                "reserve": reserve, "entry": day, "close": None}
                else:
                    missed["unaffordable_or_small_credit"] += 1
        if position:
            key1, key2 = position["legs"]
            short, long = chain.get(key1), chain.get(key2)
            if not short or not long or not short.ask_size or not long.bid_size:
                raise ValueError(f"Missing spread mark on {day}: {key1} {key2}")
            debit = max(0., short.ask - long.bid) * 100
            if debit > (key1[1] - key2[1]) * 100 + .001:
                anomalous_marks += 1
            if debit <= .5 * position["credit"]:
                position["close"] = "half_profit"
            elif debit >= 2 * position["credit"]:
                position["close"] = "twice_credit"
            elif (key1[0] - day).days <= 21:
                position["close"] = "21_dte"
            equity = cash + position["reserve"] + position["credit"] - debit
        else:
            equity = cash
        curve.append((day, equity))
        if not position and day.weekday() == 0 and day in trend and i + 1 < len(days):
            spot = spots[day]
            candidates = []
            for (expiry, strike), short in chain.items():
                long = chain.get((expiry, strike - 1.))
                dte = (expiry - day).days
                if not (30 <= dte <= 50 and .97 <= strike / spot <= .99 and long):
                    continue
                if (short.volume < 50 or long.volume < 10
                        or min(short.bid_size, long.ask_size) <= 0):
                    continue
                credit = short.bid - long.ask
                if .10 <= credit < 1 and 100 * (1 - credit) <= min(cash, capital * .5):
                    candidates.append((abs(dte - 40), abs(strike / spot - .98),
                                       expiry, strike))
            if candidates:
                _, _, expiry, strike = min(candidates)
                pending = ((expiry, strike), (expiry, strike - 1.))
            else:
                missed["no_eligible_monday_spread"] += 1
    peak, drawdown = capital, 0.
    for _, equity in curve:
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    return {"start": start.isoformat(), "end": end.isoformat(), "capital": capital,
            "final_equity": round(curve[-1][1], 2),
            "return_fraction": round(curve[-1][1] / capital - 1, 6),
            "max_drawdown_fraction": round(drawdown, 6), "closed_trades": len(trades),
            "win_rate": round(sum(t["pnl"] > 0 for t in trades) / len(trades), 4) if trades else None,
            "open_position": bool(position), "missed": dict(missed), "trades": trades,
            "anomalous_marks_above_width": anomalous_marks,
            "valid_quote_replay": anomalous_marks == 0 and position is None,
            "warning": "EOD single-leg NBBO is not an executable spread order; assignment, FX and slippage beyond quoted spreads are excluded."}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=["SPY", "QQQ", "IWM"], required=True)
    parser.add_argument("--options", nargs="+", required=True)
    parser.add_argument("--stocks", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    (spots, quotes), excluded = load_quotes(args.options, args.stocks, args.symbol)
    report = {"symbol": args.symbol, "excluded": excluded,
              "rules": "Monday 30-50 DTE put credit spread; $1 width, short strike 1-3% OTM; 200-day underlying trend; 50% profit, 2x credit stop or 21 DTE; next-day crossed quotes; one position at a time; 50% capital risk cap",
              "2024": replay(spots, quotes, date(2024, 1, 1), date(2024, 12, 31)),
              "2025": replay(spots, quotes, date(2025, 1, 1), date(2025, 12, 15))}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"symbol": args.symbol, "2024": {k: v for k, v in report["2024"].items() if k != "trades"},
                      "2025": {k: v for k, v in report["2025"].items() if k != "trades"}}, indent=2))


if __name__ == "__main__":
    main()
