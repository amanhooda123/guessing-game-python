# Five percent monthly: findings and implementation

The target has not been achieved or validated. Constant 5% compounded monthly means 79.59% annually. This update measures the existing results, searches additional primary research, implements a new research selector, and audits a new intraday data source. All modules retain `NO TRADE`.

## Existing strategy versus the target

The post hoc one-contract 1% account-cost-cap momentum spread variant used an illustrative US$100,000 account:

| Year | Modeled annual return | Geometric monthly equivalent | Best realized-book month | Worst realized-book month | Months at least 5% |
|---|---:|---:|---:|---:|---:|
| 2024 | 1.31% | 0.108% | 1.23% | -1.03% | 0/12 |
| 2025 | 1.88% | 0.155% | 2.02% | -1.71% | 0/12 |

Monthly diagnostics assign closed-trade profit to exit months and carry outstanding positions at cost. They are **not fully marked liquidation account NAV**. Larger 5% and 10% caps produced one realized-book month above 5% in 2025, but lost money in 2024 and left an unresolved position. Scaling the best historical month does not validate a repeatable target. See `monthly_target.json` and earlier cost/sizing checks in `FORUM_AND_PAPER_RESEARCH.md`.

## Additional research

The strongest concrete new lead is Stocks in Play / opening-range breakout. The [author stock study](https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf) reports 41.6% annual return and 12% maximum drawdown for its relative-volume variant in 2016–2023, using 4x stock leverage and modeled commissions. The geometric monthly equivalent is about 2.94%. These are the authors' stock results, not independently replicated results or evidence for our options adaptation.

Other primary leads include systematic option momentum and half-hour option reversals on [Ilias Filippou's research page](https://sites.google.com/view/iliasfilippou/working-papers), and the published [Option Return Predictability with Machine Learning and Big Data](https://doi.org/10.1093/rfs/hhad017). They require historical option-return factors or intraday quote histories; the current stock-momentum strategy does not reproduce them. The machine-learning source was reviewed at abstract level, with no full model replication.

Reddit's high-return claims remain leads rather than verified records. One inspected SPX-only claim involved substantial account risk, a short self-reported live history and undisclosed exact rules. It cannot establish reproducible all-company performance.

## New code

`option_lab.stocks_in_play` uses prior 14-day average volume and true range, prior 14 opening-bar volumes, and the completed opening five-minute candle. Filters require price above $5, average daily volume at least one million, ATR above $0.50, and relative opening volume at least one. It fixes the top 20 eligible companies by opening volume **before** observing later breakouts. Bullish openings permit call candidates, bearish openings put candidates.

Our adaptation waits for a completed later five-minute close beyond the opening range, differing from the paper's stock stop-entry timing. The options adapter uses the first snapshot within 30 seconds after the signal, timestamped bid/ask and sizes, 14–30 days to expiry, absolute delta 0.45–0.70, and spread at most 10% of ask. There is no premium ceiling. This selects research contracts; it does not simulate fills, option exits, sizing or account returns. The underlying stop is an annotation, not an implemented option-risk model.

`option_lab.monthly_target` distinguishes average monthly performance from achieving 5% every month. Its marked-NAV input requires contiguous monthly records and complete marks, with at least 24 measured months for the historical target check. Cash flows are supported only when explicitly booked at month end; intramonth flows need separate appropriate return accounting. Input marks are not independently verified. A historical pass never enables trading or guarantees future returns.

## Data audit

Audited the entire January 2024 file of [fabhaus/equities_5m_options](https://huggingface.co/datasets/fabhaus/equities_5m_options): 18,830 rows, 44 symbols, 10 dates. All contracts in that file expire in 2026; none is within 30 days of observation. Trade OHLCV bars have no bid, ask or quote sizes.

Every audited row contains January 2024 CPI 308.417 before its release. [BLS published that value February 13, 2024 at 8:30 ET](https://www.bls.gov/news.release/archives/cpi_02132024.htm), after every observation in the file. That feature contains future information. This conclusion applies to the inspected file and feature; uninspected months are not assessed. See `intraday_source_audit.json`.

A credible options test still requires point-in-time five-minute stock history, synchronized option NBBO/Greeks including expired contracts, corporate-action handling, and implemented exits and account equity after costs. The audited file cannot provide that evidence. No data purchase or order placement occurred.

## Reproduce

From `option-research-bot`:

```sh
python -m unittest discover -s tests -v
python -m option_lab.monthly_target --trades reports/momentum_spreads.json --sizing reports/momentum_validation.json --report reports/monthly_target.json
python -m option_lab.intraday_audit --input /path/to/2024-01.jsonl --report reports/intraday_source_audit.json
python -m option_lab.stocks_in_play --bars /path/to/stock_5m.json --daily /path/to/stock_daily.json --quotes /path/to/option_nbbo.json --as-of 2024-01-18T15:00:00Z --report reports/opening_range_candidates.json
```

JSON field schemas follow the module's accesses. Five-minute bars use start timestamps with offsets; prior bars must be actual trading sessions. The timestamp is illustrative, not a recommendation. Raw market files are not committed.

Validation: 37 unit tests pass, including incomplete-bar exclusion, opening rank fixed before breakout, rejection of trade bars as option quotes, rejection of pre-signal quotes, cash-flow accounting, missing-month rejection and incomplete-mark rejection. These verify code behavior, not profitability.
