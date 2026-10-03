from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from .backtest import Config, choose, run, trend_on_prior_day
from .model import read_quotes, read_stocks
from .theta import download
from .parquet_import import convert
from .research import walk_forward


def main() -> None:
    parser = argparse.ArgumentParser(description="Options research; never places broker orders")
    sub = parser.add_subparsers(dest="command", required=True)
    get = sub.add_parser("fetch-theta", help="Download real EOD data using your local Theta Terminal v3")
    get.add_argument("--symbol", default="RDDT")
    get.add_argument("--start", type=date.fromisoformat, required=True)
    get.add_argument("--end", type=date.fromisoformat, required=True)
    get.add_argument("--out", default="data")
    imp = sub.add_parser("import-parquet", help="Convert historical option-chain Parquet files")
    imp.add_argument("--options", nargs="+", required=True)
    imp.add_argument("--underlying", required=True)
    imp.add_argument("--symbol", required=True)
    imp.add_argument("--out", default="data")
    for name in ("backtest", "signal", "walk-forward"):
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
        if name == "walk-forward":
            cmd.add_argument("--train-start", type=date.fromisoformat, required=True)
            cmd.add_argument("--split", type=date.fromisoformat, required=True)
            cmd.add_argument("--test-end", type=date.fromisoformat, required=True)
            cmd.add_argument("--report")
        if name == "signal":
            cmd.add_argument("--research-report", required=True)
    args = parser.parse_args()
    if args.command == "fetch-theta":
        print("Downloaded:", *download(args.symbol.upper(), args.start, args.end, args.out))
        return
    if args.command == "import-parquet":
        print("Converted:", *convert(args.options, args.underlying, args.out, args.symbol.upper()))
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
    elif args.command == "walk-forward":
        result = walk_forward(quotes, stocks, args.train_start, args.split,
                              args.test_end, cfg)
        output = json.dumps(result, indent=2)
        if args.report:
            Path(args.report).write_text(output + "\n", encoding="utf-8")
        print(output)
    else:
        research = json.loads(Path(args.research_report).read_text(encoding="utf-8"))
        if research.get("decision") != "PAPER_TEST_ONLY" or sorted({q.symbol for q in quotes}) != research.get("symbols"):
            print(json.dumps({"candidate": None, "action": "NO TRADE",
                              "reason": "No qualified research result for these symbols; paper signals disabled"}, indent=2))
            return
        cfg = Config(**research["selected_config"])
        day = max(q.day for q in quotes)
        relevant = [q for q in quotes if q.day == day and trend_on_prior_day(q.symbol, day, stocks)]
        pick = choose(relevant, stocks, cfg,
                      max_cost=cfg.capital * cfg.max_position_fraction)
        print(json.dumps({"as_of": day.isoformat(), "candidate": (
            {"symbol": pick.symbol, "expiry": pick.expiry.isoformat(), "strike": pick.strike,
             "right": pick.right, "ask": pick.ask, "bid": pick.bid,
             "estimated_cost_usd": round(pick.ask * 100 * (1 + cfg.fx_fee_fraction), 2)}
            if pick else None), "action": "manual review only; no order placed",
            "note": "EOD quotes are published after the close; request a fresh tradable quote before any order."}, indent=2))


if __name__ == "__main__":
    main()
