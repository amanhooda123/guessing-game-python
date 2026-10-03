# Second strategy study — 2026-10-03

## Decision

**No trade.** The defined-risk put credit spread hypothesis lost money in every examined ticker and year. This is an exploratory second pass, **not a fresh out-of-sample test**: the project previously inspected 2025 long-call results on these same ETFs. The figures below use a separate hypothetical US$200 account for each ticker and each year.

| Ticker | 2024 quote replay | 2025 quote replay | Quote/data issue |
| --- | ---: | ---: | --- |
| SPY | -72.5%, 21 closed trades | -58.0%, 20 closed trades | 2025 has one crossed-leg mark above spread width; its reported maximum drawdown is therefore invalid |
| QQQ | -65.0%, 13 closed trades | -74.5%, 3 closed trades | 2025 has two crossed-leg marks above spread width |
| IWM | -76.0%, 15 closed trades | -47.0%, 12 closed trades | 2025 has a crossed-leg mark above spread width and ends with an open position |

The 2025 returns for SPY and QQQ include suspect quote marks; the IWM final amount includes an open position. Do not treat any of these as a verified fill or a tradable return. Even the apparently cleaner 2024 replays were substantially negative. Raw per-trade traces and anomaly counts are in `*_spread_study.json`.

## Hypothesis and implementation

Discussion in [r/algotrading about credit-spread backtests](https://www.reddit.com/r/algotrading/comments/gyn6dj/) and [r/options about taking half the maximum credit](https://www.reddit.com/r/options/comments/mmvmtd/) motivated the rules; individual posts do not establish profitability. The rules were fixed before this spread study: on Mondays when the underlying is above its preceding 200-close average, seek a $1-wide bull put credit spread with 30–50 days to expiry and the short strike 1–3% below the stock. Require short volume at least 50, long volume at least 10, at least $0.10 credit, and risk no more than half of initial capital. Enter on the next quote date by selling the short put at its bid and buying the long put at its ask. Signal an exit after half the credit can be retained, a quoted close debit reaches twice the entry credit, or expiry is 21 days away; close at the following date's short ask and long bid. Only one spread at a time.

The replay uses the same [public third-party Parquet archive](https://github.com/anahatsingh-ui/options-dataset-hist) as the [first study](RESEARCH.md). It detects a crossed-leg exit debit greater than the spread width and marks that year's quote replay invalid. It excludes stock assignment, exercise, additional spread-order slippage, FX changes and taxes. It assumes no extra commission or FX conversion. Those omissions could worsen real performance. A single-leg end-of-day NBBO pair does not show an executable, simultaneous spread fill.

Under [Wealthsimple's current spread rules](https://help.wealthsimple.com/hc/en-ca/articles/43913330243227-Trade-multi-leg-options-spreads), this strategy requires an eligible margin account with USD accounts enabled. Spreads are unavailable in registered or ordinary non-margin accounts; early assignment can produce large stock transactions. A US$200 hypothetical test balance does not imply that an actual CAD$200 account can trade it. The bot provides no order for this strategy.

## Reproduce

With the same local Parquet files and underlying CSV used in the first study and optional `pyarrow` installed:

```sh
python -m option_lab.spread_study --symbol SPY --options data/spy_options_2024.parquet data/spy_options_2025.parquet --stocks data/SPY_stock.csv --report reports/spy_spread_study.json
python -m unittest discover -s tests -v
```

Repeat with `QQQ` or `IWM`. No threshold was fitted here, so these losses are direct tests of one forum-inspired hypothesis. Any further revised strategy needs fresh data and forward paper execution before a claim of reliability.
