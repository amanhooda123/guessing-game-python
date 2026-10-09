"""Research-only call/put screen across arbitrary symbols and snapshot dates."""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

API = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")


def _query(sql: str) -> list[dict]:
    with urlopen(API + "?" + urlencode({"q": sql}), timeout=35) as response:
        body = json.load(response)
    if body.get("query_execution_status") != "Success":
        raise RuntimeError(f"DoltHub query failed: {body.get('query_execution_message')}")
    return body["rows"]


def fetch_symbol(symbol: str, day: date) -> dict:
    if not SYMBOL.fullmatch(symbol):
        raise ValueError(f"Invalid ticker: {symbol}")
    d = day.isoformat()
    errors = []
    try:
        options = _query("SELECT date,act_symbol,expiration,strike,call_put,bid,ask,delta "
                         f"FROM option_chain WHERE act_symbol = '{symbol}' AND date = '{d}' LIMIT 1000")
    except (OSError, RuntimeError, TimeoutError) as exc:
        options = []
        errors.append(f"option query failed: {type(exc).__name__}")
    try:
        volatility = _query("SELECT date,act_symbol,hv_current,iv_current FROM volatility_history "
                            f"WHERE act_symbol = '{symbol}' AND date = '{d}' LIMIT 1")
    except (OSError, RuntimeError, TimeoutError) as exc:
        volatility = []
        errors.append(f"volatility query failed: {type(exc).__name__}")
    return {"symbol": symbol, "date": d, "options": options,
            "volatility": volatility[0] if volatility else None,
            "truncated": len(options) >= 1000, "errors": errors}


def fetch_snapshot(symbols: list[str], day: date) -> dict:
    symbols = list(dict.fromkeys(s.upper() for s in symbols))
    if not symbols or len(symbols) > 200 or any(not SYMBOL.fullmatch(s) for s in symbols):
        raise ValueError("Provide 1–200 valid ticker symbols per batch")
    with ThreadPoolExecutor(max_workers=3) as pool:
        snapshots = list(pool.map(lambda s: fetch_symbol(s, day), symbols))
    return {"source": "DoltHub post-no-preference/options; sparse public snapshots, no volume/size",
            "date": day.isoformat(), "requested_symbols": symbols, "snapshots": snapshots}


def scan(snapshot: dict, budget_usd: float = 150., today: date | None = None) -> dict:
    if budget_usd <= 0:
        raise ValueError("budget must be positive")
    day = date.fromisoformat(snapshot["date"])
    current = today or date.today()
    candidates = []
    coverage = []
    for entry in snapshot["snapshots"]:
        symbol = entry["symbol"]
        rows, vol = entry["options"], entry["volatility"]
        coverage.append({"symbol": symbol, "option_rows": len(rows),
                         "volatility_available": bool(vol), "truncated": entry["truncated"],
                         "errors": entry.get("errors", [])})
        if entry["truncated"] or entry.get("errors") or not vol or not rows:
            continue
        hv, iv = float(vol["hv_current"] or 0), float(vol["iv_current"] or 0)
        if iv <= 0 or hv / iv < 1.25:
            continue
        grouped = {}
        for row in rows:
            expiry = date.fromisoformat(row["expiration"])
            if not 30 <= (expiry - day).days <= 75:
                continue
            bid, ask = float(row["bid"] or 0), float(row["ask"] or 0)
            if bid <= 0 or ask < bid or (ask - bid) / ask > .25:
                continue
            delta = float(row["delta"] or 0)
            kind = row["call_put"].lower()
            if not ((kind == "call" and .10 <= delta <= .30)
                    or (kind == "put" and -.30 <= delta <= -.10)):
                continue
            grouped.setdefault(expiry, {"call": [], "put": []})[kind].append(row)
        for expiry, sides in grouped.items():
            if not sides["call"] or not sides["put"]:
                continue
            calls = sorted(sides["call"], key=lambda r: abs(float(r["delta"]) - .20))
            puts = sorted(sides["put"], key=lambda r: abs(float(r["delta"]) + .20))
            call, put = calls[0], puts[0]
            debit = (float(call["ask"]) + float(put["ask"])) * 100 * 1.015
            if debit <= budget_usd:
                candidates.append({"symbol": symbol, "expiry": expiry.isoformat(),
                                   "call_strike": float(call["strike"]),
                                   "put_strike": float(put["strike"]),
                                   "estimated_ask_cost_usd_equivalent": round(debit, 2),
                                   "historical_to_implied_volatility_ratio": round(hv / iv, 3)})
    candidates.sort(key=lambda c: (-c["historical_to_implied_volatility_ratio"],
                                   c["estimated_ask_cost_usd_equivalent"], c["symbol"]))
    return {"as_of": day.isoformat(), "evaluated_on": current.isoformat(),
            "coverage": coverage, "historical_research_candidates": candidates,
            "action": "NO TRADE", "reason": (
                "Snapshot is stale; no current executable quotes" if day != current
                else "No validated out-of-sample edge and source lacks volume, size and executable fills"),
            "note": "HV > IV is a research hypothesis, not a forecast or probability of profit."
            " The $150 budget is USD-equivalent, not CAD."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--budget-usd", type=float, default=150.)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()
    raw = fetch_snapshot(args.symbols, args.date)
    result = scan(raw, args.budget_usd)
    Path(args.output).write_text(json.dumps({"snapshot": raw, "screen": result}, indent=2) + "\n")
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
