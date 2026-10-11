"""Predeclared Greek and liquidity screen for long U.S. equity options.

Greeks are sensitivities, not probabilities of a profitable trade. This module
does not make orders or present historical candidates as live recommendations.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


def historical_volatility(prices: list[float]) -> float | None:
    if len(prices) < 21 or any(p <= 0 for p in prices[-21:]):
        return None
    returns = [math.log(b / a) for a, b in zip(prices[-21:-1], prices[-20:])]
    mean = sum(returns) / len(returns)
    return math.sqrt(252 * sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))


def evaluate(row: dict, spot: float, rv20: float | None, budget: float | None = None,
             fx_fee: float = .015, require_size_volume: bool = True) -> tuple[dict | None, str]:
    """Evaluate at the stated snapshot, without inferring missing Greek data."""
    day = date.fromisoformat(row["quote_date"])
    expiry = date.fromisoformat(row["expiration"])
    dte = (expiry - day).days
    if not 45 <= dte <= 90:
        return None, "expiry"
    if row["option_type"] not in ("C", "P"):
        return None, "right"
    bid, ask = float(row["bid_1545"]), float(row["ask_1545"])
    if (spot <= 0 or bid <= 0 or ask < bid or (ask - bid) / ask > .20):
        return None, "liquidity"
    if require_size_volume and (int(row["bid_size_1545"]) < 1
                                or int(row["ask_size_1545"]) < 1
                                or int(row["trade_volume"] or 0) < 10):
        return None, "liquidity"
    if budget is not None and ask * 100 * (1 + fx_fee) > budget:
        return None, "budget"
    iv = float(row["implied_volatility_1545"] or 0)
    delta = float(row["delta_1545"] or 0)
    gamma = float(row["gamma_1545"] or 0)
    theta = float(row["theta_1545"] or 0)
    vega = float(row["vega_1545"] or 0)
    if (iv <= 0 or gamma <= 0 or theta >= 0 or vega <= 0
            or not (.15 <= delta <= .55 if row["option_type"] == "C"
                    else -.55 <= delta <= -.15)):
        return None, "greeks"
    if rv20 is None or rv20 <= 0 or iv / rv20 > 1.5:
        return None, "volatility_history"
    if -theta / ask > .035:
        return None, "daily_decay"
    # Fixed ranking only, not fitted against returns; favor moderate delta,
    # tighter spread, slower decay and lower IV relative to realized volatility.
    score = (abs(abs(delta) - .30) + .2 * (ask - bid) / ask
             + .05 * (-theta / ask) + .01 * iv / rv20)
    return {"symbol": row["underlying_symbol"], "day": day.isoformat(),
            "expiration": expiry.isoformat(), "strike": float(row["strike"]),
            "right": "call" if row["option_type"] == "C" else "put",
            "ask": ask, "bid": bid, "estimated_cost_usd_equivalent": round(ask * 100 * (1 + fx_fee), 2),
            "delta": delta, "gamma": gamma, "theta": theta, "vega": vega,
            "iv": iv, "rv20": rv20, "score": round(score, 6)}, "eligible"


def screen_cboe(files: list[str], stock_history: str | None, budget: float | None = None) -> dict:
    """Screen a dated Cboe sample or daily files; require prior underlying history."""
    if budget is not None and budget <= 0:
        raise ValueError("Budget must be positive")
    histories: dict[str, list[tuple[date, float]]] = defaultdict(list)
    if stock_history:
        with open(stock_history, newline="", encoding="utf-8") as source:
            for row in csv.DictReader(source):
                histories[row["symbol"].upper()].append((date.fromisoformat(row["date"]), float(row["close"])))
    for series in histories.values():
        series.sort()
    counts: Counter[str] = Counter()
    candidate_by_date: dict[str, list[dict]] = defaultdict(list)
    seen_dates: set[str] = set()
    prior_cache: dict[tuple[str, date], tuple[float | None, bool, bool]] = {}
    for path in files:
        file_dates: set[str] = set()
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".csv")]
            if len(names) > 1:
                names = [n for n in names if "cgi_or_historical.csv" in n]
            if len(names) != 1:
                raise ValueError(f"Ambiguous Cboe ZIP members: {path}")
            with archive.open(names[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig") as source:
                for row in csv.DictReader(source):
                    counts["rows_seen"] += 1
                    sym = row["underlying_symbol"].upper()
                    if sym.startswith("^") or row["root"].upper() != sym or row["delivery_code"].strip():
                        counts["index_or_nonstandard"] += 1
                        continue
                    day = date.fromisoformat(row["quote_date"])
                    if day.isoformat() in seen_dates and day.isoformat() not in file_dates:
                        raise ValueError(f"Duplicate date across Cboe files: {day}")
                    seen_dates.add(day.isoformat())
                    file_dates.add(day.isoformat())
                    spot = (float(row["underlying_bid_1545"]) + float(row["underlying_ask_1545"])) / 2
                    cache_key = (sym, day)
                    if cache_key not in prior_cache:
                        prior = [p for d, p in histories[sym] if d < day]
                        if len(prior) >= 60:
                            ma20, ma60 = sum(prior[-20:]) / 20, sum(prior[-60:]) / 60
                            prior_cache[cache_key] = (historical_volatility(prior),
                                                      ma20 > ma60 and prior[-1] > prior[-21],
                                                      ma20 < ma60 and prior[-1] < prior[-21])
                        else:
                            prior_cache[cache_key] = (None, False, False)
                    rv, uptrend, downtrend = prior_cache[cache_key]
                    if rv is None:
                        counts["no_prior_trend"] += 1
                        continue
                    if not (uptrend if row["option_type"] == "C" else downtrend):
                        counts["opposite_direction"] += 1
                        continue
                    candidate, reason = evaluate(row, spot, rv, budget)
                    counts[reason] += 1
                    if candidate:
                        candidate_by_date[day.isoformat()].append(candidate)
    picks = {d: min(rows, key=lambda r: (r["score"], r["symbol"], r["strike"]))
             for d, rows in sorted(candidate_by_date.items())}
    return {"source": "Cboe 15:45 ET snapshot plus prior underlying history",
            "dates": sorted(seen_dates), "counts": dict(counts), "best_historical_candidate_each_day": picks,
            "action": "NO TRADE", "reason": "Historical screen only; no tested edge or current quote"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--stock-history", help="Date/symbol/close CSV with at least 60 preceding dates")
    parser.add_argument("--budget-usd", type=float, help="Optional contract price ceiling; omitted by default")
    parser.add_argument("--report")
    args = parser.parse_args()
    if args.budget_usd is not None and args.budget_usd <= 0:
        parser.error("Budget must be positive")
    result = screen_cboe(args.files, args.stock_history, args.budget_usd)
    output = json.dumps(result, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
