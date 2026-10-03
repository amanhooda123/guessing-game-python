"""Daily EOD research replay. Quotes after the close are non-executable proxies."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable

from .model import Quote


@dataclass(frozen=True)
class Config:
    capital: float = 200.0                 # USD-equivalent starting buying power
    premium_cap: float = 150.0             # USD per 100-share contract
    max_position_fraction: float = 1.0     # maximum cost / initial account value
    min_dte: int = 45
    max_dte: int = 100
    min_volume: int = 10
    max_spread_fraction: float = 0.20
    min_otm_fraction: float = 0.0
    max_otm_fraction: float = 0.12
    take_profit: float = 0.35
    stop_loss: float = -0.50
    exit_dte: int = 10
    max_hold_days: int = 45
    fx_fee_fraction: float = 0.015         # CAD-only account, each conversion
    commission_per_side: float = 0.0


@dataclass
class Position:
    key: tuple
    entry_day: date
    entry_ask: float
    cost: float
    pending_exit: str = ""


def trend_on_prior_day(symbol: str, day: date, closes: dict) -> bool:
    history = [p for (s, d), p in sorted(closes.items(), key=lambda item: item[0][1])
               if s == symbol and d <= day]
    if len(history) < 61:
        return False
    # Signal uses only information available on the previous completed date.
    return (sum(history[-20:]) / 20 > sum(history[-60:]) / 60
            and history[-1] > history[-21])


def precompute_trends(closes: dict) -> set[tuple[str, date]]:
    histories = defaultdict(list)
    for (symbol, day), close in sorted(closes.items(), key=lambda item: item[0][1]):
        histories[symbol].append((day, close))
    signals = set()
    for symbol, history in histories.items():
        prefix = [0.0]
        for _, price in history:
            prefix.append(prefix[-1] + price)
        for i in range(60, len(history)):
            last20 = (prefix[i + 1] - prefix[i - 19]) / 20
            last60 = (prefix[i + 1] - prefix[i - 59]) / 60
            if last20 > last60 and history[i][1] > history[i - 20][1]:
                signals.add((symbol, history[i][0]))
    return signals


def eligible(q: Quote, underlying: float, cfg: Config) -> bool:
    dte = (q.expiry - q.day).days
    otm = q.strike / underlying - 1
    return (q.right == "call" and cfg.min_dte <= dte <= cfg.max_dte
            and cfg.min_otm_fraction <= otm <= cfg.max_otm_fraction
            and 100 * q.ask <= cfg.premium_cap and q.volume >= cfg.min_volume
            and q.bid > 0 and q.bid_size > 0 and q.ask_size > 0
            and q.spread_fraction <= cfg.max_spread_fraction)


def choose(quotes: Iterable[Quote], closes: dict, cfg: Config,
           max_cost: float | None = None) -> Quote | None:
    picks = [q for q in quotes if (q.symbol, q.day) in closes
             and eligible(q, closes[q.symbol, q.day], cfg)
             and (max_cost is None or q.ask * 100 * (1 + cfg.fx_fee_fraction)
                  + cfg.commission_per_side <= max_cost)]
    # Prefer closer to 3% OTM, then 70 DTE, then a tighter spread.
    return min(picks, key=lambda q: (abs(q.strike / closes[q.symbol, q.day] - 1.03),
                                     abs((q.expiry - q.day).days - 70),
                                     q.spread_fraction, q.key)) if picks else None


def run(quotes: list[Quote], closes: dict, cfg: Config = Config(),
        start: date | None = None, end: date | None = None) -> dict:
    by_day = defaultdict(dict)
    for q in quotes:
        if (start is None or q.day >= start) and (end is None or q.day <= end):
            by_day[q.day][q.key] = q
    days = sorted(by_day)
    if not days:
        raise ValueError("No option quotes in test interval")
    cash, pos, pending_buy = cfg.capital, None, None
    trends = precompute_trends(closes)
    trades, curve, rejected = [], [], 0
    for i, day in enumerate(days):
        chain = by_day[day]
        # Orders decided on the previous day are priced at today's quote proxy.
        if pos and pos.pending_exit:
            q = chain.get(pos.key)
            if q is None or q.bid < 0 or q.bid_size <= 0:
                raise ValueError(f"Missing exit bid for {pos.key} on {day}; cannot value replay")
            proceeds = q.bid * 100 * (1 - cfg.fx_fee_fraction) - cfg.commission_per_side
            cash += proceeds
            trades.append({"symbol": q.symbol, "expiry": q.expiry.isoformat(),
                           "strike": q.strike, "entry": pos.entry_day.isoformat(),
                           "exit": day.isoformat(), "buy_ask": pos.entry_ask,
                           "sell_bid": q.bid, "cost": round(pos.cost, 2),
                           "proceeds": round(proceeds, 2),
                           "pnl": round(proceeds - pos.cost, 2),
                           "reason": pos.pending_exit})
            pos = None
        if pos is None and pending_buy is not None:
            q = chain.get(pending_buy)
            pending_buy = None
            if q and (q.symbol, day) in closes and eligible(q, closes[q.symbol, day], cfg):
                cost = q.ask * 100 * (1 + cfg.fx_fee_fraction) + cfg.commission_per_side
                if cost <= cash and cost <= cfg.capital * cfg.max_position_fraction:
                    cash -= cost
                    pos = Position(q.key, day, q.ask, cost)
                else:
                    rejected += 1
        if pos:
            q = chain.get(pos.key)
            if q is None or q.bid < 0 or q.bid_size <= 0:
                raise ValueError(f"Missing mark bid for {pos.key} on {day}; cannot value replay")
            mark = max(0, q.bid * 100 * (1 - cfg.fx_fee_fraction) - cfg.commission_per_side)
            gain = mark / pos.cost - 1
            dte = (q.expiry - day).days
            if gain >= cfg.take_profit:
                pos.pending_exit = "take_profit"
            elif gain <= cfg.stop_loss:
                pos.pending_exit = "stop_loss"
            elif dte <= cfg.exit_dte or (day - pos.entry_day).days >= cfg.max_hold_days:
                pos.pending_exit = "time_exit"
            equity = cash + mark
        else:
            equity = cash
        curve.append({"date": day.isoformat(), "equity": round(equity, 2)})
        if not pos and i + 1 < len(days):
            candidates = [q for q in chain.values() if (q.symbol, day) in trends]
            pick = choose(candidates, closes, cfg,
                          max_cost=min(cash, cfg.capital * cfg.max_position_fraction))
            pending_buy = pick.key if pick else None

    peak, max_drawdown = cfg.capital, 0.0
    for point in curve:
        peak = max(peak, point["equity"])
        max_drawdown = min(max_drawdown, point["equity"] / peak - 1)
    return {"config": asdict(cfg), "start": days[0].isoformat(),
            "end": days[-1].isoformat(), "quote_days": len(days),
            "closed_trades": trades, "open_position": (
                {"key": [str(v) for v in pos.key], "entry": pos.entry_day.isoformat(),
                 "pending_exit": pos.pending_exit} if pos else None),
            "rejected_for_cash": rejected, "final_marked_equity": curve[-1]["equity"],
            "return_fraction": round(curve[-1]["equity"] / cfg.capital - 1, 6),
            "win_rate_closed": (round(sum(t["pnl"] > 0 for t in trades) / len(trades), 4)
                                if trades else None),
            "max_drawdown_fraction": round(max_drawdown, 6), "equity_curve": curve,
            "warning": "EOD NBBO after market close is not an executable fill; results are indicative only."}
