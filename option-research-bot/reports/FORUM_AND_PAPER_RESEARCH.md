# Forum and published-strategy research — 2026-10-12

**A small historical candidate emerged, but no proven live strategy.** One-contract momentum call spreads under a 1% position limit produced positive modeled account returns in both 2024 and 2025. That position limit was selected after inspecting the same history. Higher costs almost eliminated the 2025 profit; other sizes lost money or had unresolved contracts. The candidate remains **NO TRADE**, suitable for further research rather than a recommendation to buy or sell.

## What was investigated

| Source | Idea or evidence | What this project did |
|---|---|---|
| [r/algotrading: calendar spreads before earnings](https://www.reddit.com/r/algotrading/comments/1kxx0uv/calendar_spreads_before_earnings_feedback_wanted/) | A trader describes buying a later-expiry call and selling a nearer call, using IV term structure and earnings timing. The claimed live success is not an independently audited result. | Tested a fixed calendar rule and an earnings-calendar adaptation on the available companies. |
| [r/options: calendar variations](https://www.reddit.com/r/options/comments/1k66arx/) | Located discussion of different expiry choices and losses from volatility falling in the longer leg. | Did not assume the longer leg was protected from an earnings volatility drop. |
| [r/algotrading: broad strategy tests](https://www.reddit.com/r/algotrading/comments/1x2owmo/i_backtested_100_retail_trading_strategies_700/) | The poster reports that costs, missing delisted stocks and testing many variants weakened apparent edges. The claims are self-reported. | Kept rejected variants, executed after the signal, and separated trade averages from capital-constrained accounts. |
| [ORATS earnings-strategy study](https://orats.com/blog/earnings-options-strategies-backtest) | ORATS reported a positive long-calendar result on 54 selected out-of-sample earnings trades in 2021. Its 0.91% measure is profit divided by stock price, **not an annual account return**. Proprietary forecasts and execution assumptions were not supplied here. | Used the strategy family as a hypothesis, not as proof or an exact replication of its proprietary screen. |
| [Chung and Louis: earnings announcements and option returns](https://www.sciencedirect.com/science/article/pii/S0927539816300743) | The paper reports different straddle behavior before and after earnings, with volatility conditioning. | Tested a pre-earnings long-straddle adaptation; did not claim a full replication. |
| [Cboe put-writing explanation](https://www.cboe.com/insights/posts/generating-income-and-managing-risk-cash-secured-put-writing-in-a-low-equity-return-environment/) and [OIC cash-secured puts](https://www.optionseducation.org/strategies/all-strategies/cash-secured-put) | Collecting premium requires accepting downside stock risk and reserving collateral. Cboe's index evidence does not prove a single-stock screen. | Included assigned-stock losses, cash collateral, integer contracts and one open position per company. |
| [Jegadeesh and Titman stock-momentum paper](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) | Historical evidence for stock return continuation; it does not establish that an option adaptation is profitable. | Ranked stocks on prior 12-minus-one-month returns and tested call debit spreads separately. |

The research did not find an independently reproducible Reddit strategy that guarantees profit. It also did not substitute the earlier three-ETF tests for a company-selection algorithm.

## Improved historical inputs

The available option source still contains **16,167,068 rows across 1,612 symbols in 2024** and **23,667,966 rows across 1,599 symbols in 2025**. It contains ETFs as well as companies and is not every U.S. or Canadian listing. No ticker allowlist or fixed US$30/US$150 premium ceiling was used in the research rankers.

A separate [raw stock OHLCV archive](https://huggingface.co/datasets/siddharthmb/stocks-ohlcv) was downloaded: 1,210,415,158 bytes, source revision `de36a6a731b5ff46857146123d4624bed6e87419`. Joining the available option symbols supplied **1,272,937 underlying rows across 1,804 symbols for 2023–2025**. The momentum study additionally used 2022 warmup, for 1,703,884 rows. Unlike the earlier study, these models use direct raw stock prices, not parity-inferred spot.

The [DoltHub earnings database](https://www.dolthub.com/repositories/post-no-preference/earnings) supplied **58,078 earnings records**: 20,321 in 2023, 19,724 in 2024 and 18,033 in 2025. The [stocks database](https://www.dolthub.com/repositories/post-no-preference/stocks) supplied **1,995 split records**. Pagination and duplicate keys were checked. Three records had invalid split factors: PHG and IEP in May 2024, and SONG in December 2025. They reset indicator warmup rather than producing division by zero or invented adjustments.

Known split factors adjust preceding stock-price history only when the ex-date is reached. Trades crossing a split are retained as unresolved/nonstandard outcomes; their option deliverables are not invented. Earnings dates are retrospectively known, **not verified as announced and confirmed before each signal**. Consequently, pre-earnings findings cannot pass a point-in-time live-validation gate with these inputs alone.

## Fixed new strategy families

Before the first replay, the four event hypotheses used stock price at least US$10 and preceding average daily dollar volume at least US$10 million, positive two-sided option quotes and quoted spreads at most 10%.

- **Calendar term structure:** same-strike call or put calendar, nearer expiry 14–45 days, later expiry 45–90 days and at least 14 days farther out; near IV at least 1.2 times far IV. Select the strongest qualifying IV ratio and hold five calendar days after the next-observation entry.
- **Earnings calendar:** the same structure with the retrospectively recorded earnings event 3–10 calendar days after the signal. Enter before the event and attempt to exit at the first observation after its date. This is not the Reddit trader's intraday entry/next-morning execution.
- **Pre-earnings long straddle:** an ATM call and put expiring after the event, 14–45 days to expiry, combined mean IV at most 1.5 times prior stock RV. Enter before the event and attempt to exit after it.
- **Cash-secured put:** a stock above its prior 200-observation mean; sell a 30–60-day OTM put with delta magnitude 0.15–0.30 and IV/RV at least 1.2. Rank by closeness to 0.20 delta and then premium yield. Reserve the full assignment value, not just the option premium.

The fifth family was then added from stock-momentum research, **after seeing the event-strategy results**. Its rules were set before its first replay:

- On the first available option snapshot each month, rank eligible stocks by their prior 252-to-21-observation price return, adjusted for then-known splits. Require a positive score, price above the prior 200-observation mean and the same stock-liquidity filters.
- Take up to five eligible companies. Buy a 0.55–0.80 delta call and sell a higher-strike 0.20–0.45 delta call, same expiry 45–75 days away. Short strike must be at least 2% above spot; spread width 3–20% of spot; displayed debit 10–90% of width. Prefer long delta 0.65, short delta 0.30 and 60-day expiry by a fixed score.
- Attempt entry at the **next source snapshot**, no more than five calendar days later. Reject expiry outside the modeled calendar year; do not clip a future expiry to the final available date.
- Use an expiry stock-price payoff approximation. Nonstandard or missing settlement outcomes remain unresolved. This is an options adaptation, **not a replication of the stock-momentum paper**.

## Frictions and capital

The USD-funded base case crosses actual displayed ask/bid, adds 1% adverse option-price slippage and US$0.65 per leg. These are explicit hypothetical frictions, not a statement that Wealthsimple charges US$0.65. Wealthsimple currently [states a zero option contract fee](https://help.wealthsimple.com/hc/en-ca/articles/43198629134235-Sell-a-secured-put), but zero commission does not remove spread or execution costs.

Put assignment is initially evaluated at expiry-close prices, then checked by selling assigned shares at the **next exchange-session open**, with 10 basis points stock-sale slippage and a US$0.65 sale fee. Whether assignment occurred is determined from expiry close, not re-decided after a favorable Monday rebound. Calendar and straddle exits use observed leg quotes. Quote-only calendar closing costs can exceed the initial debit when crossing both leg spreads; these are not ideal theoretical spread payoffs or independently verified executable package prices.

Cash-secured puts use an illustrative US$100,000 starting account and a 20% per-company collateral limit, one contract and one open position per company. Momentum spreads initially used one contract and a 10% per-company cost limit. Capital cannot be spent twice. Missing held trades keep their collateral. No daily option mark-to-market drawdown or Sharpe is claimed; these are terminal/realized cash replays. Idle cash earns zero; taxes, interest, dividends, early assignment, broker exercise charges and after-hours exercise ambiguity are omitted.

## Results of the event hypotheses

Mean returns below use matched quote records and the strategy's own cost/collateral denominator. They are not annual account returns, and overlapping records are not independent trials.

| Hypothesis | 2024 matched/selected | 2024 matched mean | 2025 matched/selected | 2025 matched mean |
|---|---:|---:|---:|---:|
| Calendar term structure | 104/155 | −68.42% | 111/224 | −72.96% |
| Earnings calendar | 32/126 | −140.46% | 40/196 | −97.13% |
| Pre-earnings long straddle | 59/143 | −11.38% | 62/223 | −17.36% |
| Cash-secured put | 110/137 | +0.004% | 162/213 | +0.130% |

Cash-secured puts show why a profitable trade average is insufficient. Their expiry-close capital replay returned **+2.68% in 2024 and −7.83% in 2025**. Using next-open sale prices for assigned shares changed that to **+1.09% and −5.26%**. Doubling modeled frictions gave **+0.82% and −5.56%**. This family did not produce a robust profitable account strategy.

The [event records](events_2024_2025.json) and [assignment/cost scenarios](events_validation.json) preserve both the matched and missing outcomes. A year-end expiry bug was caught during account review: an option expiring in 2026 must never be assigned a synthetic December 2025 expiry. It was fixed, a regression test added, and the full replay rerun before these figures were reported.

## Momentum spread results and the positive candidate

The initial momentum-spread replay selected **48 records in 2024 and 55 in 2025**. It matched 27 and 52, respectively. The matched mean was **−16.30% in 2024 and +2.40% in 2025**. At the initial 10% cost limit, the 2024 account had a −US$10,089 realized result and an unresolved US$1,475.60 contract; 2025 was fully resolved at **+10.59%**. That initial version did not pass.

After reviewing these outcomes, four one-contract position limits and three integer-contract equal-risk sizes were inspected. **This was a post hoc sensitivity analysis on already-examined 2024–2025 data.** The winning size is not an untouched holdout result or evidence adjusted for this search.

| One-contract maximum cost per company | 2024 outcome | 2025 outcome |
|---|---:|---:|
| 1% of account equity | **+1.31%, fully resolved** | **+1.88%, fully resolved** |
| 2% | +US$348 realized; one unresolved contract | +0.05% |
| 5% | −US$2,019 realized; one unresolved contract | +10.59% |
| 10% | −US$10,089 realized; one unresolved contract | +10.59% |

The **small positive candidate** is exactly: an illustrative USD-funded US$100,000 account, one contract per selected company, one open position per company and a new spread costing no more than 1% of the account's realized-cost equity. This is a capital constraint, not an independent US$30 or US$150 contract cap. The research ranker still examines expensive contracts; the account cannot purchase a contract that violates its risk allocation.

It filled **12 trades in 2024 and 24 in 2025**, with no unresolved positions in that size variant. Modeled final cash was **US$101,307.55** and **US$101,876.84**, starting each year's cohort at US$100,000. Worst closed-trade losses were **US$948.10** and **US$927.60**. These are small results on small samples and do not establish a probability of future profit.

| One-percent candidate cost scenario | 2024 modeled account return | 2025 modeled account return |
|---|---:|---:|
| USD-funded base frictions | +1.31% | +1.88% |
| Double fees/slippage | +1.15% | **+0.06%** |
| 1.5% FX sensitivity | +1.03% | **−0.19%** |

The FX sensitivity applies conversion to a synthetic net payoff and is **not a full gross-assignment-cashflow broker model**. Wealthsimple's [spread guidance requires USD accounts](https://help.wealthsimple.com/hc/en-ca/articles/43913330243227-Trade-multi-leg-options-spreads). Changing costs can also change whether an integer contract fits the position limit; the double-cost 2025 scenario filled 23 trades rather than 24.

Integer equal-risk sizing did not rescue robustness: at 1% risk with multiple contracts when affordable, 2024 returned **−0.40%** and 2025 **+3.33%**. At 0.5%, results were −1.30%/+0.86%; at 2%, the 2024 cohort had an unresolved contract. Thus the positive one-contract result is **not scale invariant** and is sensitive to nominal contract cost and position-sizing convention. All seven size variants are in the [validation file](momentum_validation.json); the [momentum contract records](momentum_spreads.json) retain the full selections.

**Decision:** retain the one-contract, 1% size as a historical research candidate, not a proven profitable bot. Lock it before any new evaluation. It needs better quote coverage, actual contract/exercise accounting, full capital mark-to-market, a cash-interest benchmark and genuinely new forward data. The implementation emits **NO TRADE** and places no orders. No default-branch merge or brokerage action occurred.

## Reproduce and verify

Use Python with `pyarrow==26.0.0` and `exchange-calendars==4.13.2`. Option Parquet conversion is described in [RECENT_COMPARISON.md](RECENT_COMPARISON.md). Download the stock CSV from the source revision above; raw data and event JSON inputs remain outside Git.

```sh
python -m option_lab.event_data --out data/events --stock-csv /path/to/ohlcv.csv --option-files data/recent/options_2023.parquet data/recent/options_2024.parquet data/recent/options_2025.parquet
python -m option_lab.event_study --files data/recent/options_2024.parquet data/recent/options_2025.parquet --stocks data/events/optionable_stocks.parquet --earnings data/events/earnings.json --splits data/events/splits.json --report reports/events_2024_2025.json
python -m option_lab.event_validation --input reports/events_2024_2025.json --stocks data/events/optionable_stocks.parquet --splits data/events/splits.json --stock-csv /path/to/ohlcv.csv --report reports/events_validation.json
python -m option_lab.event_data --skip-events --out data/momentum --stock-start 2022-01-01 --stock-csv /path/to/ohlcv.csv --symbols data/events/symbols.json
python -m option_lab.momentum_spreads --files data/recent/options_2024.parquet data/recent/options_2025.parquet --stocks data/momentum/optionable_stocks.parquet --splits data/events/splits.json --report reports/momentum_spreads.json
python -m option_lab.momentum_validation --input reports/momentum_spreads.json --report reports/momentum_validation.json
python -m unittest discover -s tests -v
```

All **29 tests pass**, including opposite-side calendar closing cashflows, assigned-stock losses, collateral reuse, unresolved positions, zero split factors, future-expiry bounds, next-open assignment sale after a rebound, bounded vertical intrinsic payoffs and integer contract sizing. Report accounting, finite values and expiry identities were also checked. Tests verify the implementation's stated model; they do not validate original quote provenance or live profitability.
