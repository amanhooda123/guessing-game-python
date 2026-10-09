"""Fixed-rule long call plus put study on historical option quotes; no orders."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from .spread_study import Leg


def load_quotes(paths: list[str], stock_path: str, symbol: str) -> tuple[dict, dict, dict]:
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
        for batch in pq.ParquetFile(path).iter_batches(batch_size=50000, columns=fields):
            for r in batch.to_pylist():
                if r["symbol"] != symbol or r["type"] not in ("call", "put"):
                    continue
                day, expiry = date.fromisoformat(r["date"]), date.fromisoformat(r["expiration"])
                spot = spots.get(day)
                if not spot or not 2 <= (expiry - day).days <= 55 or not .65 <= r["strike"] / spot <= 1.35:
                    continue
                bid, ask = r["bid"], r["ask"]
                intrinsic = max(0, spot - r["strike"]) if r["type"] == "call" else max(0, r["strike"] - spot)
                if (bid is None or ask is None or bid < 0 or ask <= 0 or bid > ask
                        or bid + .15 < intrinsic):
                    excluded["bad_quote"] += 1
                    continue
                quotes[day][(expiry, float(r["strike"]), r["type"])] = Leg(
                    bid, ask, r["volume"] or 0, r["bid_size"] or 0, r["ask_size"] or 0)
    return spots, quotes, dict(excluded)


def choose_pair(chain: dict, spot: float, cash: float, capital: float) -> tuple | None:
    by_expiry = defaultdict(lambda: {"call": [], "put": []})
    for (expiry, strike, right), q in chain.items():
        if (q.bid <= 0 or q.volume < 10 or min(q.bid_size, q.ask_size) <= 0
                or (q.ask - q.bid) / q.ask > .25):
            continue
        ratio = strike / spot
        if right == "call" and 1.08 <= ratio <= 1.12:
            by_expiry[expiry]["call"].append((abs(ratio - 1.10), strike, q))
        elif right == "put" and .88 <= ratio <= .92:
            by_expiry[expiry]["put"].append((abs(ratio - .90), strike, q))
    pairs = []
    for expiry, sides in by_expiry.items():
        # The caller already restricts entry chains to 30–45 DTE.
        if not sides["call"] or not sides["put"]:
            continue
        call = min(sides["call"])
        put = min(sides["put"])
        cost = (call[2].ask + put[2].ask) * 100 * 1.015
        if cost <= min(cash, capital * .75):
            pairs.append((call[0] + put[0], cost, expiry, call[1], put[1]))
    if not pairs:
        return None
    _, _, expiry, call_strike, put_strike = min(pairs)
    return ((expiry, call_strike, "call"), (expiry, put_strike, "put"))


def replay(spots: dict, quotes: dict, start: date, end: date, capital: float = 200.) -> dict:
    """Monday signal, next-date ask entry, five quote-day hold, bid exit; 1.5% FX per side."""
    if capital <= 0:
        raise ValueError("capital must be positive")
    days = sorted(day for day in quotes if start <= day <= end)
    if not days:
        raise ValueError("No quotes in interval")
    cash, position, pending = capital, None, None
    trades, equity_curve = [], []
    missed = defaultdict(int)
    for i, day in enumerate(days):
        chain = quotes[day]
        if position and i - position["index"] >= 5:
            call, put = (chain.get(k) for k in position["keys"])
            if not call or not call.bid_size:
                missed["zero_assumed_call_exit"] += 1
            if not put or not put.bid_size:
                missed["zero_assumed_put_exit"] += 1
            # Conservative zero when a leg has no displayed bid/size. Such a
            # replay cannot claim a verified execution or fair market value.
            proceeds = ((call.bid if call and call.bid_size else 0)
                        + (put.bid if put and put.bid_size else 0)) * 100 * .985
            cash += proceeds
            trades.append({"entry": position["day"].isoformat(), "exit": day.isoformat(),
                           "expiry": position["keys"][0][0].isoformat(),
                           "call_strike": position["keys"][0][1],
                           "put_strike": position["keys"][1][1],
                           "cost": round(position["cost"], 2),
                           "proceeds": round(proceeds, 2),
                           "pnl": round(proceeds - position["cost"], 2)})
            position = None
        if not position and pending:
            call, put = (chain.get(k) for k in pending)
            if (call and put and min(call.ask_size, put.ask_size) > 0
                    and call.bid > 0 and put.bid > 0):
                cost = (call.ask + put.ask) * 100 * 1.015
                if cost <= min(cash, capital * .75):
                    cash -= cost
                    position = {"keys": pending, "index": i, "day": day, "cost": cost}
                else:
                    missed["unaffordable_at_entry"] += 1
            else:
                missed["missing_entry_quote"] += 1
            pending = None
        if position:
            call, put = (chain.get(k) for k in position["keys"])
            if not call or not put:
                missed["incomplete_mark"] += 1
            equity = cash + ((call.bid if call and call.bid_size else 0)
                             + (put.bid if put and put.bid_size else 0)) * 100 * .985
        else:
            equity = cash
        equity_curve.append(equity)
        if not position and day.weekday() == 0 and i + 1 < len(days):
            # Historical chain quote observed after the close; order prices use the next date.
            entry_chain = {k: v for k, v in chain.items() if 30 <= (k[0] - day).days <= 45}
            pending = choose_pair(entry_chain, spots[day], cash, capital)
            if not pending:
                missed["no_affordable_liquid_pair"] += 1
    peak, max_drawdown = capital, 0.
    for equity in equity_curve:
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
    return {"start": start.isoformat(), "end": end.isoformat(),
            "capital_usd_equivalent": capital, "final_marked_equity": round(equity_curve[-1], 2),
            "return_fraction": round(equity_curve[-1] / capital - 1, 6),
            "max_drawdown_fraction": round(max_drawdown, 6),
            "closed_trades": len(trades), "open_position": bool(position),
            "valid_quote_replay": (position is None and not any(
                missed.get(key) for key in ("zero_assumed_call_exit", "zero_assumed_put_exit", "incomplete_mark"))),
            "win_rate": round(sum(t["pnl"] > 0 for t in trades) / len(trades), 4) if trades else None,
            "missed": dict(missed), "trades": trades,
            "warning": "End-of-day quotes cannot establish fill prices; two-leg execution, taxes and FX rate changes are omitted."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=["SPY", "QQQ", "IWM"], required=True)
    parser.add_argument("--options", nargs="+", required=True)
    parser.add_argument("--stocks", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    spots, quotes, excluded = load_quotes(args.options, args.stocks, args.symbol)
    report = {"symbol": args.symbol, "excluded": excluded,
              "rules": "Buy 8-12% OTM call and put, same expiry 30-45 DTE, on Tuesday after Monday selection; max $150 USD-equivalent combined cost; sell both at bid on fifth subsequent quote date; 1.5% conversion each side",
              "2024": replay(spots, quotes, date(2024, 1, 1), date(2024, 12, 31)),
              "2025": replay(spots, quotes, date(2025, 1, 1), date(2025, 12, 15))}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"symbol": args.symbol, "2024": {k: v for k, v in report["2024"].items() if k != "trades"},
                      "2025": {k: v for k, v in report["2025"].items() if k != "trades"}}, indent=2))


if __name__ == "__main__":
    main()
