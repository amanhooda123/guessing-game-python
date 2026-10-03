# Option Lab

Research and manual paper signals for **long U.S. equity call options**, plus a separate exploratory credit-spread study. It never logs into Wealthsimple or places an order. The initial hypothesis is a trend-following purchase of a liquid call 45–100 calendar days from expiry, with a one-contract budget and rules for taking gains, limiting losses, and closing before expiry. A [2024 training / 2025 holdout study](reports/RESEARCH.md) of three ETFs found **no validated profitable strategy**; a [second spread study](reports/SECOND_PASS.md) also lost money. All current reports disable the paper signal.

## Why this design

- A quoted option premium of $1.10 costs about **US$110** for a standard 100-share contract; $1.50 in sale proceeds is US$150, or US$40 gross before spread, currency conversion and any other charges. A cheap premium does not imply a high probability of profit.
- The scanner filters zero bids, low volume, wide spreads, and options outside the specified budget. A trend check uses 20 versus 60 prior daily closes; it does not use future prices or news published later.
- Exits are considered at 35% *net mark-to-bid* gain, 50% loss, 10 days to expiry, or 45 calendar days held. An exit signal is priced on the **following observed date**, not retroactively at the signal price.
- A CAD-only Wealthsimple account may incur a 1.5% currency conversion charge on both purchase and sale; the default model includes it. Set `--fx-fee 0` only if a USD account and funding arrangement actually avoids per-trade conversion. All amounts in reports are USD-equivalent, without exchange-rate movement. The code does not model taxes, exchange-rate fluctuations, partial fills, earnings surprises, dividends, corporate actions, or changing Wealthsimple terms.

## Run

Python 3.10+, standard library for the core CSV replay. From the project root:

```sh
python -m unittest discover -s tests -v
python -m option_lab.cli fetch-theta --symbol RDDT --start 2025-10-01 --end 2026-09-30
python -m option_lab.cli backtest --options data/RDDT_options.csv --stocks data/RDDT_stock.csv --capital 200 --premium-cap 150 --report reports/rddt.json
python -m option_lab.cli walk-forward --options data/RDDT_options.csv --stocks data/RDDT_stock.csv --train-start 2025-01-01 --split 2026-01-01 --test-end 2026-09-30 --report reports/rddt_walk_forward.json
python -m option_lab.cli signal --options data/RDDT_options.csv --stocks data/RDDT_stock.csv --research-report reports/rddt_walk_forward.json
```

The fetch command requires **your own ThetaData free account and the v3 Theta Terminal running locally on port 25503**. No credentials are stored in this repository. The free tier advertises one year of historical end-of-day U.S. stock and options data. A two-year evaluation needs a suitable paid entitlement or another historical bid/ask dataset. Requests are paced for the documented free limit. Data files are ignored by Git; check your data license before distributing. The example RDDT dates are illustrative and require data coverage and sufficient history; no RDDT historical performance is claimed here.

For the public 2024–2025 SPY, QQQ and IWM archive, install optional `pyarrow` and follow the exact commands and source details in [the research report](reports/RESEARCH.md). The three small JSON summaries are committed in `reports/`. The `signal` command requires a matching research report that passes the qualification gate; otherwise it prints `NO TRADE`. It never places an order.

The separate `option_lab.spread_study` module replays one fixed forum-inspired bull put spread rule against the raw Parquet archive. [Its report](reports/SECOND_PASS.md) explains the losing results, unreliable quotes, and Wealthsimple account eligibility. It emits no trade signal.

Alternatively supply your own option CSV with columns `date,symbol,expiration,strike,right,bid,ask,volume,bid_size,ask_size`, and stock CSV with `date,symbol,close`. Dates are ISO `YYYY-MM-DD`. Include the stock history before the option test window for the 60-close warmup. Use *point-in-time* option chains including delisted/expired contracts, not today's chain or split-adjusted quotes paired with raw strikes.

## What a result means

Theta's EOD option NBBO is generated at 17:15 ET **after options trading has closed**. The next-day ask/bid in this replay is therefore a pricing proxy, **not an executable historical fill**. Even minute NBBO would only bound a hypothetical order; your real limit order might not fill. A backtest cannot report exactly what a live account would have earned. A more credible next phase uses intraday timestamped NBBO at a fixed tradable time, quotes with size, brokerage fill logs, contemporaneous FX, and forward paper trading. Do not optimize thresholds on the same period used for final evaluation.

The report shows marked account equity, closed trades, win rate, and drawdown. An open position is marked at the bid. Missing exit quotes cause an error rather than a fabricated return. Test several symbols, regimes, and out-of-sample months before interpreting performance; also count eligible opportunities and missing data. The public historical archive was accessible, but its original provenance and executable quote quality were not independently verified. The actual study found no validated edge.

## Sources and research notes

- [ThetaData subscriptions](https://thetadata.net/docs/Articles/Getting-Started/Subscriptions.html) and [EOD option endpoint](https://thetadata.net/docs/operations/option_history_eod.html): free historical EOD access, terminal requirement, 17:15 ET generated quote; [stock EOD endpoint](https://thetadata.net/docs/operations/stock_history_eod.html).
- [Wealthsimple currency conversion](https://help.wealthsimple.com/hc/en-ca/articles/4415548242971-Convert-funds-between-CAD-and-USD) and [options fee overview](https://help.wealthsimple.com/hc/en-ca/articles/38797083728923-Options-trading-fees-and-taxes). Check your specific account and order preview for fees.
- [Wealthsimple expiry/exercise rules](https://help.wealthsimple.com/hc/en-ca/articles/39056801816859-Understand-exercising-options-and-assignment): an in-the-money long option can be automatically exercised; closing early matters for small accounts.
- [SEC investor bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-63): a long option buyer can lose the entire premium.

No supported public Wealthsimple trading API was verified during this build. Do not use unofficial private endpoints or paste your brokerage credentials into the bot. The `signal` command is for manual review with fresh quotes in your brokerage app.
