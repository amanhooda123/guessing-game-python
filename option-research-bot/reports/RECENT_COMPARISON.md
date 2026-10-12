# Cross-symbol 2024–2025 options comparison — 2026-10-12

This continues the shared conversation using the years requested and **no contract premium cap or ticker allowlist**. It ranks individual-company options across the available source, which also contains ETFs. This is not every listed company, and no Canadian-option history was supplied. It does not place orders.

## Data recovered and audited

The public source's automatic Parquet preview ended in early 2023, but its **full CSV contains 2024 and 2025**. The repository previously contained only the older cross-symbol comparison. The newer comparison described in the shared conversation was not present on its default branch when this continuation began, so this report rebuilds a reproducible comparison rather than claiming those unpublished results were verified.

Source: [siddharthmb/stocks-options](https://huggingface.co/datasets/siddharthmb/stocks-options), source repository revision `049b66a8e54ee7f9b0bba141fb8b6cae1ba73d1a`. CSV size: 9,131,259,945 bytes. Retrieved byte range 3,950,000,000–9,131,259,944; discarded the first partial record. That slice begins in December 2022 and ends January 2026, encompassing the requested years and the preceding warmup year.

| Year | Option rows | Source snapshot dates | Symbols | First/last source dates |
|---|---:|---:|---:|---|
| 2023 warmup | 14,352,823 | 155 | 1,635 | Jan 2 / Dec 29 |
| 2024 | 16,167,068 | 183 | 1,612 | Jan 1 / Dec 31 |
| 2025 | 23,667,966 | 259 | 1,599 | Jan 1 / Dec 31 |

The exchange-calendar filter leaves **148 snapshots in 2023, 174 in 2024 and 249 in 2025**, with **1,433 symbols** having at least one usable parity spot proxy across the three years. Indicator warmup requirements further reduce eligibility.

Dates include market holidays. The replay filters them with the XNYS exchange calendar. There is no trade volume, quote size, executable timestamp, independent stock price, corporate action history, or contemporaneous news in these option files. Spot is approximated from at least two near-ATM call/put pairs using put-call parity, omitting carry and dividends. These limitations can distort both signals and hypothetical returns.

## Fixed hypotheses

All thresholds below were set before running this rebuilt comparison. **2025 has already been examined in prior work; it is not an untouched holdout.** No threshold search or claim of a fresh validation period is made.

1. **Trend:** long calls when the mean of 20 preceding spot-proxy observations exceeds the 60-observation mean; otherwise long puts. Use the existing delta, gamma, theta, vega, IV/realized-volatility, expiry and spread screen. Delta magnitude 0.15–0.55, 45–90 calendar days to expiry, spread at most 20%, IV/RV at most 1.5, and theta/premium decay at most 3.5% per day. Lowest fixed factor score wins across symbols.
2. **Reversal:** the same single-option screen, but take the opposite direction after a prior five-observation move exceeding 1.5 estimated standard deviations. Lowest fixed factor score wins.
3. **Discounted long straddle:** buy the same-strike, same-expiry call and put with 30–60 days to expiry, delta magnitude 0.35–0.65, strike within 3% of spot proxy, each spread at most 10%, and each IV at most 0.8 times RV. Rank by mean IV/RV plus distance from spot.
4. **Rich-volatility credit spread:** sell a put spread in an uptrend or a call spread in a downtrend; short delta magnitude 0.15–0.30 and short IV at least 1.3 times RV. Both legs have 30–60 days to expiry and spreads at most 10%. Width is 2–8% of spot; displayed entry credit is 15–60% of width. Rank by distance from 0.20 delta minus 0.1 times credit/width.

RV is an elapsed-calendar-time diffusion variance estimate over 20 prior returns, annualized by 365. It does not count a multi-day gap as one trading day. Trends use observations, not a complete daily-close history. A gap over 10 days or a spot-proxy jump over 25% resets the symbol's warmup. This discards possible corporate-action distortions and genuine large moves; it does not resolve their cause.

## Quote matching and interpretation

Each hypothesis selects at most one candidate per source session. Buy legs use the **next observed ask**, sell legs the **next observed bid**. The exit uses the first observed session at least 14 calendar days after entry. Entry gaps over seven days, exit delays over seven days, and exits beyond the signal calendar year are not selected. No position is held through expiry.

A hypothetical 1.5% FX fee applies to each incoming/outgoing option-leg cashflow; it is configurable and is not a statement about the user's current account. Missing, zero-bid, nonfinite or crossed quotes remain visible as missing/invalid entries or exits. Impossible credit-spread marks are rejected. There is no invented observed exit price.

Long-option returns use premium paid as the denominator. Credit-spread returns use width less net entry credit, the hypothetical reserved maximum risk. Their return percentages therefore have different capital bases. For credit spreads, the JSON `proceeds` field is the equivalent ending reserve, not actual option sale proceeds; `credit` and `close_debit` identify the cashflows. Short-option early assignment, dividends, exercise costs and stock obligations are omitted.

The full-loss stress assumes every entered position with a missing exit loses its entire premium or reserved spread risk. This is a sensitivity calculation, not an observed loss or proof of a strict worst case including assignment and charges. Average matched returns and pooled P&L **are not annual account returns**: overlapping trades, account buying power and portfolio mark-to-market drawdown are not modeled.

## Results

**No hypothesis passed the historical gate; the action remains NO TRADE.** All four rules had negative equally weighted matched mean returns in both years. Reversal had positive pooled matched P&L in 2024 because contract sizes differed, but this did not survive 2025 or missing-exit stress. That distinction is why a selected summary metric alone cannot establish an edge.

### 2024

| Rule | Selected | Matched | Missing/invalid entry | Missing/invalid exit | Mean matched return | Matched win rate | Full-loss stress mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trend calls/puts | 97 | 25 | 22 | 50 | -3.03% | 36.0% | -67.68% |
| Reversal | 93 | 36 | 19 | 38 | -2.01% | 33.3% | -52.33% |
| Discounted long straddle | 98 | 55 | 11 | 32 | -10.87% | 25.5% | -43.65% |
| Rich-volatility credit spread | 95 | 17 | 37 | 41 | -5.32% | 70.6% | -72.25% |

### 2025

| Rule | Selected | Matched | Missing/invalid entry | Missing/invalid exit | Mean matched return | Matched win rate | Full-loss stress mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trend calls/puts | 238 | 66 | 69 | 103 | -5.59% | 36.4% | -63.13% |
| Reversal | 227 | 91 | 47 | 89 | -21.42% | 24.2% | -60.27% |
| Discounted long straddle | 233 | 136 | 23 | 74 | -17.17% | 16.2% | -46.36% |
| Rich-volatility credit spread | 212 | 42 | 79 | 91 | -16.58% | 19.0% | -73.66% |

In 2025, matching coverage ranged from **19.8% to 58.4%**; the missingness is too large to interpret matched returns as complete performance. Matched contracts span 45 symbols for trend, 76 for reversal, 46 for straddles and 32 for credit spreads. The [JSON records](recent_2024_2025.json) include individual selected contracts, outcomes, costs and cashflow details.

These rules do not supply a profitable live strategy. More credible work needs timestamped quote coverage, direct underlying/corporate-action data, a capital-constrained portfolio replay, and a genuinely fresh forward period. Repeatedly adjusting this same history until a result turns positive would not create fresh evidence.

## Reproduce

```sh
python -m pip install pyarrow==26.0.0 exchange-calendars==4.13.2
# Retrieve the full CSV, or the documented range, from the pinned source revision.
python -m option_lab.recent_import --source /path/to/options-recent.csv --out data/recent
python -m option_lab.recent_study --files data/recent/options_2023.parquet data/recent/options_2024.parquet data/recent/options_2025.parquet --spot-cache data/recent/spot_cache.json --report reports/recent_2024_2025.json
python -m unittest discover -s tests -v
```

`recent_import` deliberately discards its first line: for a full CSV that is the header; for the documented range it is a partial record. Raw files and spot caches are not committed. The spot-cache flag writes an audit output and never reads an old cache. All 18 tests pass, including next-observation pricing, fees on both sides, credit-spread risk accounting, elapsed-gap variance, prior-only features, invalid quotes and missing-exit stress.

A historical hypothesis passes the exploratory gate only with at least 30 matched trades, at least 80% matching coverage, positive matched mean and positive full-loss stress in **both** years. Even a pass keeps `NO TRADE`: a fresh forward evaluation and trustworthy execution data would still be required.

The strategy motivation distinguishes [implied from realized volatility](https://www.cmegroup.com/education/courses/introduction-to-cvol/understanding-the-cvol-index). A [long straddle](https://www.cmegroup.com/education/lessons/straddles) can lose both premiums when movement is insufficient. Those educational sources motivate hypotheses, not evidence that these stock rules are profitable.
