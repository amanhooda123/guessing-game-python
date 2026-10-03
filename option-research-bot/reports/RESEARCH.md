# Public options archive study — 2026-10-03

## Result

**No validated profitable algorithm emerged.** The bot refuses to emit a candidate for all three ETFs in this study. Percentages are returns on a separate starting US$200 equivalent account per ticker, not a combined portfolio.

| Ticker | 2024 baseline | 2025 baseline | 2024 selected training | 2025 selected holdout | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| IWM | -66.10% (11 trades) | -69.24% (12 trades) | None qualified | Not run | No validated edge |
| SPY | -75.03% (31 trades) | -96.90% (9 trades) | +164.85% (36 trades, -34.11% max drawdown) | **-92.56%** (8 trades, -95.02% max drawdown) | No validated edge |
| QQQ | +31.89% (27 trades, -69.52% max drawdown) | -90.92% (4 trades) | +25.61% (8 trades, -26.61% max drawdown) | +16.31% (2 trades, -3.39% max drawdown) | Only two holdout trades; no validated edge |

Training dates: 2024-01-01 through 2024-12-31. Holdout dates: 2025-01-01 through 2025-12-15. The matching JSON files give exact values and parameters. The apparent SPY success in training failed dramatically in untouched 2025 data. QQQ's two winning holdout trades do not establish a repeatable edge.

## Method

Long calls, 45–100 calendar days to expiry, 0–12% out of the money, premium at most US$1.50 per share, with a US$200 equivalent starting balance. The daily trend signal compares 20 and 60 underlying closes and the prior 20-day move. Entry decisions use a completed day; the replay buys at the next observed day's ask. Exit decisions use net bid marks, and the replay sells at the following observed day's bid. The model deducts a hypothetical 1.5% currency conversion on each side, assumes no additional commission, and limits each position to available cash. It does not infer fills from same-day signals.

Forty-eight threshold combinations were ranked **only on 2024**: volume 50/100, maximum relative spread 10%/15%, fraction of initial capital per position 25%/50%/100%, take-profit 20%/35%, stop-loss -25%/-50%. A configuration could be selected if it had at least eight closed 2024 trades, a positive return, at most 35% drawdown, and no open position. The selected configuration was then evaluated without tuning on 2025. The paper-signal gate additionally requires at least eight closed holdout trades, positive return, at most 35% holdout drawdown, and no open position. Neither a historical pass nor this gate would guarantee future profitability.

The experiments cover three related U.S. ETFs and two calendar periods. They do not cover individual Reddit (RDDT) contracts, all volatility regimes, tax and changing brokerage fees, or real order execution. Cross-symbol inspection also introduces selection risk. The public mirror's original chain provenance and quote quality were not independently verified. The importer excluded quotes whose bid was materially below intrinsic value, but that check cannot establish the remaining quotes were executable. EOD snapshots cannot reproduce an intraday $1.10-to-$1.50 fill. Intraday bid/ask, contemporaneous FX, order size, and forward paper orders would be needed before making claims about live performance.

## Reproduction

The source is the public [historical options Parquet mirror](https://github.com/anahatsingh-ui/options-dataset-hist), repository commit `37f6c456fe1a4775c875673fb8ef907d5cd2fd66`. Obtain `options_2024.parquet`, `options_2025.parquet`, and `underlying_prices.parquet` for each of `iwm`, `spy`, and `qqq`; place each ticker's files under `data/<ticker>/`. Install the optional `pyarrow` dependency. The importer writes local compact CSVs and a SHA-256 manifest. Raw source and converted quotes are omitted from this repository; check upstream data rights and quality before use.

```sh
python -m pip install pyarrow
python -m option_lab.cli import-parquet --options data/spy/options_2024.parquet data/spy/options_2025.parquet --underlying data/spy/underlying_prices.parquet --symbol SPY
python -m option_lab.cli walk-forward --options data/SPY_options.csv --stocks data/SPY_stock.csv --capital 200 --premium-cap 150 --train-start 2024-01-01 --split 2025-01-01 --test-end 2025-12-15 --report reports/spy_walk_forward.json
python -m option_lab.cli signal --options data/SPY_options.csv --stocks data/SPY_stock.csv --research-report reports/spy_walk_forward.json
```

Repeat with `IWM` and `QQQ`. The last command currently returns `NO TRADE` for each report. The study was informed by [trader discussion about taking profits and spreads](https://www.reddit.com/r/options/comments/1e4wefv/what_is_a_realistic_to_take_profit_on_options/) as hypothesis generation, not proof. An [academic study of option returns and trading costs](https://pmc.ncbi.nlm.nih.gov/articles/PMC10786414/) explains why gross option winners do not establish a net long-call edge. Evaluate new ideas in a fresh, untouched period rather than rewriting these 2025 holdout decisions after seeing their results.
