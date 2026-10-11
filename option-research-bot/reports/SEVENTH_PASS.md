# Cross-stock experiment without a contract price ceiling — 2026-10-11

## Correction and data

The earlier US$30 and US$150 ceilings were carried forward from old examples. **This experiment has no contract price cap or ticker allowlist.** It selects the highest-ranked long call or put across every symbol for which the supplied historical files have sufficient point-in-time inputs. Results are one contract per signal, expressed as individual trade returns, with no assumed account balance. This is a research screen; it cannot guarantee a gain or place orders.

The [public options dataset](https://huggingface.co/datasets/siddharthmb/stocks-options) provides historical bid, ask, IV, delta, gamma, theta and vega for many U.S. symbols. Ten available [converted Parquet shards](https://datasets-server.huggingface.co/parquet?dataset=siddharthmb/stocks-options) contained **43,560,000 rows, 1,956 symbols, and 514 snapshot dates from 2019-02-09 to 2023-01-09**. The study used preceding 2020 snapshots to warm the factors, then 2021 as its initial period and 2022 as a later evaluation period. After excluding weekends and requiring at least two near-ATM call/put pairs to infer a contemporaneous underlying spot, there were **1,596 symbols** with a spot proxy and **461 dates** across 2020–2022. Some source dates fall on nontrading holidays; source provenance and snapshot time are not established.

There is **no volume, bid/ask size, or independent underlying stock price** in this archive. The code does not invent them: it relaxes only those unavailable liquidity fields, still requires a positive bid and quoted spread at most 20%, and estimates spot using same-date near-ATM call/put midpoints. Interest and dividends are omitted from that put-call-parity approximation. The 20/60 trend and realized-volatility windows are prior **observed snapshots**, not necessarily 20/60 exchange trading days. Corporate actions, earnings events and news were unavailable.

## Fixed rule and observed result

The rule uses the Greek, IV/realized volatility, trend, expiry and quote-spread factors described in [SIXTH_PASS.md](SIXTH_PASS.md). At most one lowest-score contract is selected per snapshot date from the entire available universe, with no price ceiling. It attempts to buy that exact contract at the **next observed ask**, then sell at its bid five later observed snapshot dates. A hypothetical 1.5% FX charge is applied to each side. A missing entry or exit is **counted and excluded**, not assigned a made-up price. The fixed rule was applied without tuning thresholds against 2022 returns.

| Period | Daily selections | Matched entry and exit | Missing entry | Missing exit | Mean matched trade | Median matched trade | Matched win rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021 | 142 | 49 | 30 | 63 | **−14.91%** | −28.41% | 28.57% |
| 2022 | 137 | 34 | 36 | 67 | **−17.89%** | −39.38% | 35.29% |

The matched 2021 trades span 41 symbols; the matched 2022 trades span 29, including AAPL, AMD, NVDA, GOOGL and other individual companies. Mean matched one-contract debit was about US$376 in 2021 and US$843 in 2022. The 2022 matched winners were outnumbered and outweighed by losers. **Only 35% and 25% of selected signals, respectively, could be matched to both quotes.** Missingness may be systematic, so even these negative matched returns are not a complete portfolio backtest. One signal per date can overlap earlier holdings and buying power was not modeled. There is no current stock recommendation.

This is the first experiment here that actually ranks across a broad **individual-company** universe, rather than using only SPY/QQQ/IWM. It still covers 1,956 available U.S. symbols, not all listed stocks, and the public archive ends in early 2023. The prior three-ETF replays in the repo answer a narrower question and should not be presented as this cross-company result.

## Reproduce and next requirement

```sh
PYTHONPATH=.deps python -m option_lab.broad_study --files data/broad/000*.parquet --train-year 2021 --test-year 2022 --report reports/broad_2021_2022.json
python -m unittest discover -s tests -v
```

Install optional `pyarrow` to replay the public Parquet shards; they are not committed to Git. The detailed [JSON log](broad_2021_2022.json) records each matched contract and its entry/exit. The next credible test needs direct historical underlying prices, bid/ask sizes and timestamps, volume, scheduled earnings known at the decision time, corporate action adjustments, and broader continuous options history with an untouched future period. [Cboe's full-market product](https://datashop.cboe.com/option-eod-summary) can provide U.S. equity option NBBO/size and Greeks for a licensed order. [Wealthsimple currently excludes options on Canadian securities](https://help.wealthsimple.com/hc/en-ca/articles/9606205720987-Enable-options-trading-in-your-investing-account), so a Canadian-options strategy would need a different execution venue.

**Decision: no demonstrated profitable strategy; no live order or signal.**
