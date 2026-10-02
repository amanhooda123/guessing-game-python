from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from .backtest import Config, choose, run, trend_on_prior_day
from .model import read_quotes, read_stocks
from .theta import download


def main() -> None:
    parser = argparse.ArgumentParser(description="Options research; never places broker orders")
    sub = parser.add_subparsers(dest="command", required=True)
    get = sub.add_parser("fetch-theta", help="Download real EOD data using your local Theta Terminal v3")
    get.add_argument("--symbol", default="RDDT")
    get.add_argument("--start", type=date.fromisoformat, required=True)
    get.add_argument("--end", type=date.fromisoformat, required=True)
    get.add_argument("--out", default="data")
    for name in ("backtest", "signal"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--options", required=True)
        cmd.add_argument("--stocks", required=True)
        cmd.add_argument("--capital", type=float, default=200.0)
        cmd.add_argument("--premium-cap", type=float, default=150.0)
        cmd.add_argument("--fx-fee", type=float, default=0.015)
        if name == "backtest":
            cmd.add_argument("--start", type=date.fromisoformat)
            cmd.add_argument("--end", type=date.fromisoformat)
            cmd.add_argument("--report")
    args = parser.parse_args()
    if args.command == "fetch-theta":
        print("Downloaded:", *download(args.symbol.upper(), args.start, args.end, args.out))
        return
    if args.capital <= 0 or args.premium_cap <= 0 or not 0 <= args.fx_fee < 1:
        parser.error("capital and premium cap must be positive; FX fee must be in [0,1)")
    cfg = replace(Config(), capital=args.capital, premium_cap=args.premium_cap,
                  fx_fee_fraction=args.fx_fee)
    quotes, stocks = read_quotes(args.options), read_stocks(args.stocks)
    if args.command == "backtest":
        result = run(quotes, stocks, cfg, args.start, args.end)
        output = json.dumps(result, indent=2)
        if args.report:
            Path(args.report).write_text(output + "\n", encoding="utf-8")
        print(output)
    else:
        day = max(q.day for q in quotes)
        relevant = [q for q in quotes if q.day == day and trend_on_prior_day(q.symbol, day, stocks)]
        pick = choose(relevant, stocks, cfg)
        print(json.dumps({"as_of": day.isoformat(), "candidate": (
            {"symbol": pick.symbol, "expiry": pick.expiry.isoformat(), "strike": pick.strike,
             "right": pick.right, "ask": pick.ask, "bid": pick.bid,
             "estimated_cost_usd": round(pick.ask * 100 * (1 + cfg.fx_fee_fraction), 2)}
            if pick else None), "action": "manual review only; no order placed",
            "note": "EOD quotes are published after the close; request a fresh tradable quote before any order."}, indent=2))


if __name__ == "__main__":
    main()
