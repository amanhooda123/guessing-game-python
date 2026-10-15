# Premarket reversal: implemented research model and measured checks

The requested 4–5% account profit every month has **not been achieved or validated**. The new hypothesis is now implemented as a stock/option scanner, a past-only empirical calibration module, and an observed-quote option replay. Historical checks below test stock components only; the complete options strategy has no measured performance yet. No broker orders or purchases occurred.

## The hypothesis and decision rule

A negative premarket move permits a call candidate; a positive move permits a put candidate. At 09:45 America/New_York, wait for the three opening five-minute bars to finish. Require movement in the reversal direction and a close on the appropriate side of the opening VWAP proxy. Do not buy merely because the premarket sign is positive or negative.

The setup is ranked 0–100. A score of 80 means 80 ranking points, **not an 80% probability of profit**. The default research decision requires score at least 75 plus sufficient earlier net option outcomes with a positive empirical expectancy and a win-rate interval lower bound above 50%. The result is a paper candidate, never an order.

A thesis on 2011–2024 U.S. stocks found overnight-to-intraday reversal, but its modeled trading costs removed the net alpha. This is supporting evidence for investigating the direction effect, not evidence for a profitable options adaptation: [University of Turku primary research record](https://www.utupub.fi/items/094ffc24-ca98-482d-bd18-a469ca028791). Related author research includes [Overnight-Intraday Reversal Everywhere](https://guofuzhou.github.io/zworkingpapers.html). No published returns are substituted for our tests.

## Market universe and coverage

Read current official underlying directories from Cboe C1, BZX, C2 and EDGX, Nasdaq PHLX, and Montréal Exchange. After country/symbol deduplication:

| Current directory classification | U.S. | Canada |
|---|---:|---:|
| All underlying entries, including non-company instruments | 5,627 | 365 |
| Classified company equities accepted by this scanner | 3,945 | 273 |

These are a broad **current** directory snapshot, not certified entire-market completeness or historical eligibility. CDRs, ETFs, indices and other instruments are excluded from the company-equity scanner. Adjusted roots/deliverables still require quote-level verification. U.S. and Canadian symbols, currencies and option contracts remain separate even when ticker letters coincide.

Every supplied universe company is checked; missing observations produce exclusion counts rather than a fabricated score. There is no fixed ticker watchlist or absolute option-premium ceiling. Full market historical options coverage has not been obtained. In particular, Canadian premarket and intraday option-quote history are absent; U.S. prices are never used to invent Canadian observations.

[Official Cboe reference data](https://www.cboe.com/markets/us/options/market-statistics/reference-data), [Nasdaq directory definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs), [MX options list](https://www.m-x.ca/en/trading/data/options-list). Directory hashes and counts are in `premarket_universe_audit.json`. Wealthsimple's [current options guidance](https://help.wealthsimple.com/hc/en-ca/articles/9606205720987-Enable-options-trading-in-your-investing-account) says Canadian securities' options are not available there yet; the Canadian research adapter does not establish broker eligibility.

## Fixed parameters and score

| Component | Default rule | Maximum ranking points |
|---|---|---:|
| Premarket move | Previous close to latest completed 09:25–09:30 bar; absolute gap 0.5–8%; stretch 0.25–2.5 prior ATR | 15 |
| Premarket liquidity | At least six positive-volume bars; at least 100,000 local currency of traded-value proxy | 10 |
| Opening reversal | Completed 09:30–09:45 move against premarket direction, normalized by prior ATR | 20 |
| VWAP confirmation | Close above opening VWAP proxy for calls, below for puts | 10 |
| Opening volume | Opening volume divided by prior 20-day average daily volume; a proxy, not same-time relative volume | 10 |
| Market/sector context | Directional alignment from timestamped same-session context | 5 |
| Option liquidity | Positive bid/ask; spread at most 10% of ask; sizes at least one; OI at least 100; current volume at least 10 | 15 |
| IV versus prior RV | Compare quoted IV with annualized prior 20-close realized volatility | 10 |
| Theta drag | Daily theta relative to ask, with explicit units | 5 |

Additional filters: stock price at least 5 local currency, prior 20-day average daily traded-value proxy at least 10 million, at least 61 valid earlier daily bars, verified previous exchange-session close and price basis. Earnings within one day, major news, corporate action or halt flags must be explicitly false and known before the signal. Unknown event status blocks a candidate.

Options must be standard 100-share contracts, matching currency, 14–45 calendar days to expiry, delta magnitude 0.45–0.70 with the correct call/put sign, nonnegative gamma/vega, nonpositive theta, and synchronized underlying price. Theta units must be per calendar day and vega per volatility percentage point. Delta, gamma, theta and vega exposures per contract are recorded; larger gamma/vega are not automatically treated as evidence of an edge. Prior 20/60-day trend is recorded as context.

Use only the first observed chain strictly after the completed signal, within 30 seconds and no later than the scanner's as-of time. Missing quote fields fail closed. A scan later than the decision window cannot emit a stale candidate. Holidays and previous session dates are checked against separate U.S./Canadian exchange calendars.

## Confidence calibration

Use only completed net option outcomes from earlier calendar days. Match strategy version, exact parameter fingerprint, exit/cost-policy fingerprint, country, call/put direction and ten-point score bucket. Deduplicate each company/session. Require at least 100 observations across at least 30 distinct days. Report empirical net win frequency, its descriptive 95% Wilson interval, and mean net option return.

The interval does not eliminate correlation among companies on the same day. It is not a guaranteed probability, and positive estimated expectancy is not a monthly-profit guarantee. There are currently no qualifying historical option outcomes for this new model, so calibrated confidence is **unavailable**. Existing monthly momentum trades cannot calibrate a different intraday hypothesis.

## Quote-based options replay

`premarket_replay` buys one contract at observed ask plus 1% adverse option-price slippage and a hypothetical 0.65 local-currency fee. It monitors observed liquidation-at-bid net return for +30% target, −20% stop or 11:00 ET time exit. Execution uses the first valid later quote after a one-second latency and within 60 seconds. Stops may lose more than 20%; no fill is invented at a threshold between quotes. Missing exits invalidate full-account return measurement.

Full premium, rather than the nominal stop, is limited to 0.5% of account equity per entry; total open premium is limited to 2%. Each company trades at most once per day. A 1% realized daily account loss blocks new entries. These are research defaults, not fitted optimums or broker fees. USD and CAD accounts are separate and assume funding already in their respective currencies; FX, taxes and funding costs are omitted.

A session-coverage manifest is required before the replay can report account returns for the evaluation period. Missing sessions, invalid held entries or unresolved exits prevent a complete monthly account-return claim. A historical measurement never enables orders or validates future monthly returns.

## Measured check 1: broad 2024–2025 opening-gap stock diagnostic

Downloaded the full pinned `siddharthmb/stocks-ohlcv` CSV: 1,210,415,158 bytes and 26,716,798 rows scanned. The 2023–2025 window contains 7,753,750 rows before cleaning; 73,252 malformed/nonpositive OHLCV rows were removed and no duplicate keys were found. The filtered source includes 15,801 symbols. Current option directories were **not** used to select historical survivors.

Use an opening-gap proxy, prior liquidity/ATR filters, long gap-down stocks or short gap-up stocks, open-to-close returns, and equal capital per eligible company each session at 1x gross stock notional. This omits premarket observation, opening confirmation, news filters and options. Candidate observations are correlated and overlap; their count is not an independent-trial count.

| Stock component | 2024 | 2025 |
|---|---:|---:|
| Qualifying company/ETF-session observations | 218,288 | 238,522 |
| Symbols with qualifying observations | 3,609 | 4,173 |
| Sessions with opportunities | 250 | 250 |
| Gross directional win rate | 50.99% | 53.68% |
| Mean gross stock trade return | +0.040% | +0.227% |

| Assumed round-trip stock cost | 2024 stock-proxy annual return | 2025 stock-proxy annual return |
|---|---:|---:|
| 0 basis points | +5.95% | +43.77% |
| 5 basis points | −6.50% | +26.90% |
| 10 basis points | −17.49% | +11.99% |
| 20 basis points | −35.76% | −12.78% |

At 20 basis points, monthly equivalents were −3.62%/−1.13%, with 0/12 and 2/12 months reaching 4%. Even at zero cost, only 2/12 and 4/12 months reached 4%. These are illustrative stock proxies, not option results. Borrow availability/costs, actual opening fills, corporate actions, and complete historical eligibility are not established. Full monthly records and cost sensitivities are in `premarket_gap_stock_diagnostic.json`.

## Measured check 2: actual premarket bars on one session

Read 761,755,463 bytes of the pinned January 2024 `fabhaus/equities_5m_stockprices` file until the next date appeared. Retained only raw timestamp/symbol/OHLCV: 453,875 five-minute bars across 8,407 symbols on January 2, 2024. Discarded every engineered macro, fundamental and technical field; the earlier audit identified future CPI information in this source family.

Apply premarket gap/liquidity filters and completed opening price/VWAP reversal. Delay the stock proxy entry to 09:50 and exit at 11:00. There were **89 qualifying stock cases**. This diagnostic does not apply the full options/news/sector model.

| One-session stock result | Gross | After 5 bps | After 10 bps | After 20 bps |
|---|---:|---:|---:|---:|
| Directional win rate | 56.18% | 50.56% | 43.82% | 39.33% |
| Equal-weight stock return that day | +0.306% | +0.256% | +0.206% | +0.106% |

A profitable one-day mean with a lower win rate is possible because win/loss magnitudes differ. Do not annualize this day. It establishes neither stable confidence nor any monthly target. Source price provenance and adjustment basis are not independently certified. Details and exclusions are retained in `premarket_stock_one_day.json` and `premarket_data_audit.json`.

## Reproduce

Use Python with pandas, `pyarrow==26.0.0` and `exchange-calendars==4.13.2`. From the project directory:

```sh
python -m option_lab.option_universe --fetch --directory data/premarket --out data/premarket/current_universe.json --report reports/premarket_universe_audit.json
python -m option_lab.premarket_data --kind daily --out data/premarket/ohlcv.csv --report data/premarket/daily_import.json
python -m option_lab.premarket_data --kind intraday-day --out data/premarket/2024-01-02.csv --report data/premarket/intraday_import.json
python -m option_lab.gap_diagnostic --stocks data/premarket/ohlcv.csv --report reports/premarket_gap_stock_diagnostic.json
python -m option_lab.premarket_stock_check --bars data/premarket/2024-01-02.csv --daily data/premarket/ohlcv.csv --report reports/premarket_stock_one_day.json
python -m option_lab.premarket_reversal --input /path/to/point_in_time_input.json --report reports/premarket_candidates.json
python -m option_lab.premarket_replay --candidates /path/to/historical_candidates.json --quotes /path/to/real_intraday_nbbo.json --currency USD --report reports/premarket_replay.json
python -m unittest discover -s tests -v
```

Scanner JSON has `as_of`, `universe`, `daily`, `bars`, `context`, `quotes`, and optional `completed_history`. Explicit field examples are in `tests/test_premarket_reversal.py`; those fixtures are synthetic test inputs and never included in research performance. Market data arrays require country/symbol identities. Replay input additionally needs `covered_sessions` listing dates with verified complete historical scan/quote input coverage. Raw market files are not committed.

Validation: 53 tests pass. New checks cover both directions, future-bar exclusion, expired signal windows, stale/event context, future OI, quote spread, country/currency identity, calibration purging/deduplication/policy matching, adverse later-quote stops, unresolved exits, missing session coverage, account sizing, and PHLX's duplicate symbol headers. Tests verify implementation behavior, not an investment edge.

The remaining blocker is synchronized historical option NBBO/Greeks, premarket stock history and point-in-time event coverage for the intended companies and markets. The inspected public sources cannot support a complete 2024–2025 full-market options evaluation. The target remains unvalidated; no monthly return or confidence probability has been fabricated.
