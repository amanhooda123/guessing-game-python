"""Exploratory factor replay on observed bid/ask with explicitly modeled Greeks.

Only a supplement when Cboe's actual Greek history is unavailable. American
equity options, dividends and unknown original quote provenance limit accuracy.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .factors import evaluate, historical_volatility
from .model import Quote, read_quotes, read_stocks


def _cdf(x: float) -> float:
    return .5 * math.erfc(-x / math.sqrt(2))


def modeled_greeks(q: Quote, spot: float, rate: float = .04,
                   dividend_yield: float = .015) -> dict | None:
    """European BSM IV from observed mid; approximation for American options."""
    t = (q.expiry - q.day).days / 365.25
    if not .02 < t < 1 or spot <= 0 or q.strike <= 0:
        return None
    mid = (q.ask + q.bid) / 2
    def price(vol: float) -> float:
        d1 = (math.log(spot / q.strike) + (rate - dividend_yield + vol * vol / 2) * t) / (vol * math.sqrt(t))
        d2 = d1 - vol * math.sqrt(t)
        call = spot * math.exp(-dividend_yield * t) * _cdf(d1) - q.strike * math.exp(-rate * t) * _cdf(d2)
        return call if q.right == "call" else call - spot * math.exp(-dividend_yield * t) + q.strike * math.exp(-rate * t)
    if mid <= price(.0001) or mid >= price(5):
        return None
    lo, hi = .0001, 5.
    for _ in range(36):
        vol = (lo + hi) / 2
        if price(vol) < mid:
            lo = vol
        else:
            hi = vol
    iv = (lo + hi) / 2
    d1 = (math.log(spot / q.strike) + (rate - dividend_yield + iv * iv / 2) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    density = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    delta = math.exp(-dividend_yield * t) * (_cdf(d1) if q.right == "call" else _cdf(d1) - 1)
    gamma = math.exp(-dividend_yield * t) * density / (spot * iv * math.sqrt(t))
    vega = spot * math.exp(-dividend_yield * t) * density * math.sqrt(t) / 100
    common = -spot * math.exp(-dividend_yield * t) * density * iv / (2 * math.sqrt(t))
    if q.right == "call":
        theta = common - rate * q.strike * math.exp(-rate * t) * _cdf(d2) + dividend_yield * spot * math.exp(-dividend_yield * t) * _cdf(d1)
    else:
        theta = common + rate * q.strike * math.exp(-rate * t) * _cdf(-d2) - dividend_yield * spot * math.exp(-dividend_yield * t) * _cdf(-d1)
    return {"implied_volatility_1545": iv, "delta_1545": delta, "gamma_1545": gamma,
            "theta_1545": theta / 365.25, "vega_1545": vega}


def replay(options: str, stocks: str, start: date, end: date, capital: float = 100000.,
           premium_cap: float | None = None) -> dict:
    if capital <= 0 or (premium_cap is not None and premium_cap <= 0):
        raise ValueError("Capital and optional premium cap must be positive")
    quotes = read_quotes(options)
    spots = read_stocks(stocks)
    history: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for (symbol, day), spot in spots.items():
        history[symbol].append((day, spot))
    signals = {}
    for symbol, series in history.items():
        series.sort()
        for i in range(60, len(series)):
            day, _ = series[i]
            prior = [p for _, p in series[:i]]
            ma20, ma60 = sum(prior[-20:]) / 20, sum(prior[-60:]) / 60
            signals[symbol, day] = (historical_volatility(prior),
                                    ma20 > ma60 and prior[-1] > prior[-21],
                                    ma20 < ma60 and prior[-1] < prior[-21])
    chains = defaultdict(dict)
    for q in quotes:
        if start <= q.day <= end:
            chains[q.day][q.key] = q
    days = sorted(chains)
    if len(days) < 2:
        raise ValueError("At least two quote days required")
    cash, position, pending = capital, None, None
    trades, curve = [], []
    counts: Counter[str] = Counter()
    for i, day in enumerate(days):
        chain = chains[day]
        if position and position["exit_reason"]:
            exit_quote = chain.get(position["key"])
            if exit_quote is None or exit_quote.bid_size < 1:
                return {"status": "INCOMPLETE_MISSING_EXIT", "date": day.isoformat(),
                        "closed_trades": trades, "counts": dict(counts)}
            proceeds = exit_quote.bid * 100 * .985
            cash += proceeds
            trades.append({"symbol": exit_quote.symbol, "entry": position["day"].isoformat(),
                           "exit": day.isoformat(), "cost": round(position["cost"], 2),
                           "proceeds": round(proceeds, 2), "pnl": round(proceeds-position["cost"], 2),
                           "reason": position["exit_reason"]})
            position = None
        if not position and pending:
            entry = chain.get(pending)
            pending = None
            available = cash if premium_cap is None else min(cash, premium_cap)
            if entry and entry.ask_size > 0 and entry.bid > 0 and entry.ask * 100 * 1.015 <= available:
                cost = entry.ask * 100 * 1.015
                cash -= cost
                position = {"key": entry.key, "day": day, "cost": cost,
                            "index": i, "exit_reason": None}
                counts["entries"] += 1
            else:
                counts["entry_missing_or_unaffordable"] += 1
        if position:
            held = chain.get(position["key"])
            if held is None or held.bid_size < 1:
                return {"status": "INCOMPLETE_MISSING_MARK", "date": day.isoformat(),
                        "closed_trades": trades, "counts": dict(counts)}
            mark = held.bid * 100 * .985
            gain = mark / position["cost"] - 1
            if gain >= .35:
                position["exit_reason"] = "take_profit"
            elif gain <= -.50:
                position["exit_reason"] = "stop_loss"
            elif i-position["index"] >= 10 or (held.expiry-day).days <= 14:
                position["exit_reason"] = "time_exit"
            equity = cash + mark
        else:
            equity = cash
        curve.append(equity)
        if position or i + 1 >= len(days):
            continue
        candidates = []
        for q in chain.values():
            signal = signals.get((q.symbol, day))
            spot = spots.get((q.symbol, day))
            if signal is None or spot is None or not (signal[1] if q.right == "call" else signal[2]):
                continue
            model = modeled_greeks(q, spot)
            if model is None:
                counts["unmodelable"] += 1
                continue
            row = {"underlying_symbol": q.symbol, "quote_date": day.isoformat(),
                   "expiration": q.expiry.isoformat(), "strike": q.strike,
                   "option_type": "C" if q.right == "call" else "P",
                   "bid_1545": q.bid, "ask_1545": q.ask,
                   "bid_size_1545": q.bid_size, "ask_size_1545": q.ask_size,
                   "trade_volume": q.volume, **model}
            available = cash if premium_cap is None else min(cash, premium_cap)
            candidate, reason = evaluate(row, spot, signal[0], available)
            counts[reason] += 1
            if candidate:
                candidates.append((candidate["score"], q.key))
        if candidates:
            pending = min(candidates)[1]
    peak, drawdown = capital, 0.
    for equity in curve:
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    return {"status": "COMPLETE" if position is None else "OPEN_POSITION",
            "start": days[0].isoformat(), "end": days[-1].isoformat(),
            "quote_days": len(days), "capital_usd_equivalent": capital,
            "final_marked_equity": round(curve[-1], 2),
            "return_fraction": round(curve[-1] / capital - 1, 6),
            "max_drawdown_fraction": round(drawdown, 6), "closed_trades": trades,
            "counts": dict(counts), "warning": "Exploratory only: BSM Greeks modeled from third-party bid/ask with assumed 4% rate and 1.5% dividend yield; no executable fills, rate/dividend history, earnings calendar or FX changes."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--options", required=True)
    parser.add_argument("--stocks", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--capital", type=float, default=100000.,
                        help="Illustrative buying power; research-only")
    parser.add_argument("--premium-cap", type=float,
                        help="Optional contract price limit; omitted by default")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = replay(args.options, args.stocks, args.start, args.end, args.capital, args.premium_cap)
    output = json.dumps(result, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
