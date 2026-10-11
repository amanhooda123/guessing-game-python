"""Cross-stock factor experiment on public historical option-chain Parquet shards.

The public mirror lacks quote size, trade volume, underlying prices and an
exchange timestamp. It supports exploratory selection and quote matching,
not an executable return claim or a live Wealthsimple signal.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .factors import evaluate, historical_volatility

FIELDS = ["date", "act_symbol", "expiration", "strike", "call_put", "bid", "ask",
          "vol", "delta", "gamma", "theta", "vega"]


def _dates_and_rows(paths: list[str], earliest: date, latest: date):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: python -m pip install pyarrow") from exc
    current, rows = None, []
    for path in paths:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=50000, columns=FIELDS):
            for row in batch.to_pylist():
                day_text = row["date"][:10]
                if current is not None and day_text < current:
                    raise ValueError("Sort source shards by date before replay")
                if day_text != current:
                    if rows:
                        yield date.fromisoformat(current), rows
                    current, rows = day_text, []
                day = date.fromisoformat(day_text)
                if earliest <= day <= latest and day.weekday() < 5:
                    rows.append(row)
    if rows:
        yield date.fromisoformat(current), rows


def _key(row: dict) -> tuple:
    return (row["act_symbol"], row["expiration"][:10], float(row["strike"]), row["call_put"])


def _spot_from_parity(rows: list[dict], day: date) -> dict[str, float]:
    """Approximate spot from matched near-ATM call/put mids, no future prices."""
    pairs: dict[tuple, dict[str, float]] = defaultdict(dict)
    for r in rows:
        if r["call_put"] not in ("Call", "Put") or not 30 <= (date.fromisoformat(r["expiration"][:10]) - day).days <= 90:
            continue
        bid, ask = r["bid"], r["ask"]
        if bid is None or ask is None or bid <= 0 or ask < bid or (ask - bid) / ask > .25:
            continue
        delta = r["delta"]
        if delta is None or not (.35 <= abs(delta) <= .65):
            continue
        pairs[(r["act_symbol"], r["expiration"][:10], float(r["strike"]))][r["call_put"]] = (ask + bid) / 2
    by_symbol: dict[str, list[float]] = defaultdict(list)
    for (symbol, expiry, strike), sides in pairs.items():
        if "Call" in sides and "Put" in sides:
            # Carry/dividends are omitted; use the median of near-ATM pairs.
            proxy = strike + sides["Call"] - sides["Put"]
            if proxy > 0:
                by_symbol[symbol].append(proxy)
    return {symbol: statistics.median(values) for symbol, values in by_symbol.items()
            if len(values) >= 2}


def _signals(series: list[tuple[date, float]]) -> dict[tuple[str, date], tuple]:
    history: dict[str, list[float]] = defaultdict(list)
    signals = {}
    for day, spots in series:
        for symbol, spot in spots.items():
            prior = history[symbol]
            if len(prior) >= 60:
                rv = historical_volatility(prior)
                ma20, ma60 = sum(prior[-20:]) / 20, sum(prior[-60:]) / 60
                signals[symbol, day] = (spot, rv,
                                        ma20 > ma60 and prior[-1] > prior[-21],
                                        ma20 < ma60 and prior[-1] < prior[-21])
            prior.append(spot)
    return signals


def run(paths: list[str], train_year: int = 2021, test_year: int = 2022) -> dict:
    if test_year <= train_year:
        raise ValueError("Test year must follow train year")
    first = date(train_year - 1, 1, 1)
    last = date(test_year, 12, 31)
    daily_spots = [(day, _spot_from_parity(rows, day))
                   for day, rows in _dates_and_rows(paths, first, last)]
    daily_spots = [(day, values) for day, values in daily_spots if values]
    signals = _signals(daily_spots)
    days = [day for day, _ in daily_spots]
    index = {day: i for i, day in enumerate(days)}
    years = {y: {"signals": [], "trades": [], "missed_entries": 0,
                 "missed_exits": 0, "candidates": 0} for y in (train_year, test_year)}
    pending: dict[int, list[dict]] = defaultdict(list)
    for day, rows in _dates_and_rows(paths, first, last):
        if day not in index:
            continue
        i = index[day]
        # Match old selections to the actual contract at this snapshot.
        due = pending.pop(i, [])
        needed = {record["key"] for record in due}
        found = {_key(r): r for r in rows if _key(r) in needed}
        for record in due:
            q = found.get(record["key"])
            annual = years[record["year"]]
            if record["stage"] == "entry":
                if q is None or q["ask"] is None or q["bid"] is None or q["bid"] <= 0 or q["ask"] < q["bid"]:
                    annual["missed_entries"] += 1
                    continue
                record.update(stage="exit", entry=day.isoformat(), cost=q["ask"] * 100 * 1.015)
                pending[i + 5].append(record)
            else:
                if q is None or q["bid"] is None or q["bid"] <= 0:
                    annual["missed_exits"] += 1
                    continue
                proceeds = q["bid"] * 100 * .985
                annual["trades"].append({"symbol": record["key"][0], "right": record["key"][3],
                                         "strike": record["key"][2], "expiry": record["key"][1],
                                         "entry": record["entry"], "exit": day.isoformat(),
                                         "cost": round(record["cost"], 2),
                                         "proceeds": round(proceeds, 2),
                                         "return_fraction": round(proceeds / record["cost"] - 1, 6)})
        if day.year not in years or i + 6 >= len(days) or days[i + 6].year != day.year:
            continue
        choices = []
        annual = years[day.year]
        for r in rows:
            signal = signals.get((r["act_symbol"], day))
            if signal is None or not (signal[2] if r["call_put"] == "Call" else signal[3]):
                continue
            if r["bid"] is None or r["ask"] is None:
                continue
            row = {"underlying_symbol": r["act_symbol"], "quote_date": day.isoformat(),
                   "expiration": r["expiration"][:10], "strike": r["strike"],
                   "option_type": "C" if r["call_put"] == "Call" else "P",
                   "bid_1545": r["bid"], "ask_1545": r["ask"],
                   "implied_volatility_1545": r["vol"], "delta_1545": r["delta"],
                   "gamma_1545": r["gamma"], "theta_1545": r["theta"],
                   "vega_1545": r["vega"]}
            if any(row[k] is None for k in ("implied_volatility_1545", "delta_1545", "gamma_1545", "theta_1545", "vega_1545")):
                continue
            candidate, reason = evaluate(row, signal[0], signal[1],
                                         require_size_volume=False)
            if candidate:
                choices.append((candidate["score"], r["act_symbol"], _key(r)))
        annual["candidates"] += len(choices)
        if choices:
            _, _, key = min(choices)
            annual["signals"].append({"date": day.isoformat(), "symbol": key[0],
                                      "strike": key[2], "expiry": key[1], "right": key[3]})
            pending[i + 1].append({"stage": "entry", "key": key, "year": day.year})
    summary = {}
    for year, data in years.items():
        returns = [t["return_fraction"] for t in data["trades"]]
        summary[str(year)] = {"signals": len(data["signals"]), "eligible_contract_rows": data["candidates"],
                              "matched_trades": len(returns), "missing_entries": data["missed_entries"],
                              "missing_exits": data["missed_exits"],
                              "mean_trade_return_fraction": round(statistics.mean(returns), 6) if returns else None,
                              "median_trade_return_fraction": round(statistics.median(returns), 6) if returns else None,
                              "win_fraction": round(sum(x > 0 for x in returns) / len(returns), 4) if returns else None,
                              "trades": data["trades"]}
    return {"source": "Community copy of DoltHub option_chain via Hugging Face converted Parquet",
            "option_rows_research_scope": "All available equity symbols in supplied shards; no symbol allowlist or contract cap",
            "covered_dates": len(days), "symbols_with_parity_spot": len({s for _, values in daily_spots for s in values}),
            "train_year": train_year, "later_year": test_year, "years": summary,
            "caveats": "Sparse and sometimes off-market calendar dates; no NBBO timestamp, quote size, trade volume, original provenance or direct underlying data. Spot inferred by approximate put-call parity. Five observed snapshot days is not necessarily five trading days. Missing fills excluded from matched returns. Per-trade returns are not a self-financing portfolio or live fills."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--train-year", type=int, default=2021)
    parser.add_argument("--test-year", type=int, default=2022)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    result = run(args.files, args.train_year, args.test_year)
    Path(args.report).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for year, data in result["years"].items():
        print(year, {k: v for k, v in data.items() if k != "trades"})
    print("symbols_with_parity_spot", result["symbols_with_parity_spot"],
          "covered_dates", result["covered_dates"])


if __name__ == "__main__":
    main()
