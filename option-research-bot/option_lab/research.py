"""Train on one period, choose once, evaluate untouched later period."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, timedelta
from itertools import product

from .backtest import Config, run
from .model import Quote


def walk_forward(quotes: list[Quote], closes: dict, train_start: date, split: date,
                 test_end: date, config: Config = Config()) -> dict:
    if not train_start < split < test_end:
        raise ValueError("Expected train_start < split < test_end")
    baseline = config
    train_end = split - timedelta(days=1)
    baseline_train = run(quotes, closes, baseline, train_start, train_end)
    baseline_test = run(quotes, closes, baseline, split, test_end)
    # Prespecified small grid; do not add more variants after looking at test.
    trials = []
    for volume, spread, risk, tp, sl in product((50, 100), (.10, .15),
                                                (.25, .50, 1.0), (.20, .35),
                                                (-.25, -.50)):
        cfg = replace(baseline, min_volume=volume, max_spread_fraction=spread,
                      max_position_fraction=risk, take_profit=tp, stop_loss=sl)
        result = run(quotes, closes, cfg, train_start, train_end)
        trials.append({"config": cfg, "result": result})
    trials.sort(key=lambda x: (x["result"]["return_fraction"],
                               x["result"]["max_drawdown_fraction"]), reverse=True)
    eligible = [x for x in trials if len(x["result"]["closed_trades"]) >= 8
                and x["result"]["return_fraction"] > 0
                and x["result"]["max_drawdown_fraction"] >= -.35
                and x["result"]["open_position"] is None]
    chosen = eligible[0] if eligible else None
    test = run(quotes, closes, chosen["config"], split, test_end) if chosen else None
    test_supported = bool(test and len(test["closed_trades"]) >= 8
                          and test["return_fraction"] > 0
                          and test["max_drawdown_fraction"] >= -.35
                          and test["open_position"] is None)

    def compact(r):
        return {"return_fraction": r["return_fraction"],
                "final_equity": r["final_marked_equity"],
                "closed_trades": len(r["closed_trades"]),
                "max_drawdown_fraction": r["max_drawdown_fraction"],
                "win_rate_closed": r["win_rate_closed"],
                "open_position": r["open_position"]}

    return {"train_start": train_start.isoformat(), "split": split.isoformat(),
            "test_end": test_end.isoformat(), "capital_usd_equivalent": config.capital,
            "symbols": sorted({q.symbol for q in quotes}),
            "configurations_tried_on_train": len(trials),
            "baseline_train": compact(baseline_train), "baseline_test": compact(baseline_test),
            "best_train_config": asdict(trials[0]["config"]),
            "best_train_result": compact(trials[0]["result"]),
            "qualification": "At least 8 closed trades, positive training return, drawdown <= 35%, no open position",
            "qualified_count": len(eligible),
            "selected_config": asdict(chosen["config"]) if chosen else None,
            "selected_train": compact(chosen["result"]) if chosen else None,
            "selected_test": compact(test) if test else None,
            "decision": "PAPER_TEST_ONLY" if test_supported
            else "NO_VALIDATED_EDGE; DO_NOT_TRADE",
            "test_requirement": "At least 8 closed trades, positive return, drawdown <= 35%, no open position",
            "warning": "Historical EOD quote marks are not executable fills; test selection can still overfit."}
