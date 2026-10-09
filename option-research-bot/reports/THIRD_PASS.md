# Buying a call and put together — exploratory study, 2026-10-09

## Outcome

**No validated edge; no live order.** A long strangle buys one out-of-the-money call and one out-of-the-money put with the same expiry. Both premiums can be lost if the underlying does not move far enough. This fixed-rule test uses a fresh hypothetical US$200 equivalent balance for each ticker and each calendar period. The 2025 data had already been examined for other strategies, so this is **not an untouched holdout**. The public source's quote provenance is unverified.

| ETF | 2024 final marked return | 2025 final marked return | Evidence limit |
| --- | ---: | ---: | --- |
| SPY | +54.62%, 22 closed trades | -70.91%, 2 closed trades | 2024 ends with an open position and had -67.14% maximum drawdown; 2025 assumed zero proceeds for one leg without a displayed exit bid/size |
| QQQ | -79.34%, 7 closed trades | -38.05%, 1 closed trade | Very few opportunities remained affordable |
| IWM | -79.83%, 10 closed trades | -63.81%, 3 closed trades | Very few opportunities remained affordable |

These are separate calendar replays that reset the balance on January 1. They are not a continuous two-year account return. SPY's positive 2024 mark is **not realized or validated** because the year ends with an open position. JSON files `*_two_sided.json` include every closed trade, open-position flag and missing-quote count. The prior [long-call](RESEARCH.md) and [credit-spread](SECOND_PASS.md) ideas also failed to establish a repeatable net edge.

## Exact rule

On each Monday, choose the same 30–45 day expiry for a liquid call 8–12% above the underlying and a liquid put 8–12% below it; prefer strikes near 10% from spot. Each leg must have positive bid, at least 10 contracts of reported volume, a positive bid/ask size, and a quoted relative spread at most 25%. Combined ask premium plus 1.5% modeled purchase conversion must be no more than the lesser of available capital and US$150 equivalent. Buy both at the **next quote date's asks** if the budget still holds. On the fifth subsequent quote date, sell both at their **bids**, less 1.5% modeled conversion on proceeds. Only one pair is held at once. If a leg has no displayed bid/size at the scheduled exit, the model assigns that leg zero proceeds and flags the entire calendar result as unverified. Mark an open pair at the latest displayed bids.

This rule was set before the call/put replay. No parameters were fitted in this third study, although the prior studies had already examined these symbols and years. The backtest uses end-of-day single-leg snapshots as price proxies, not executable multi-leg orders, and does not simulate partial fills, taxes, exchange-rate movement, or the broker's actual conversion charges on a combined order. It uses US$200 equivalent, **not CAD$200**.

Buying both sides can benefit from a large move in either direction, but the stock can remain between the strikes and both options can lose their premiums. [Wealthsimple explains the strategy and its web-only combined order](https://help.wealthsimple.com/hc/en-ca/articles/37860194950299-Trade-multi-leg-options-Straddles-strangles-and-rolling-options). [Peer-reviewed research on option spreads and tick-level execution](https://research.monash.edu/en/publications/the-profitability-of-volatility-spread-trading-on-asx-equity-opti/) finds that transaction costs can eliminate apparent volatility-strategy profits. Neither source supplies a guaranteed profit rule.

## Reproduce

Use the public Parquet files identified in [the first study](RESEARCH.md), the previously converted stock CSV, and optional `pyarrow`:

```sh
python -m option_lab.two_sided_study --symbol SPY --options data/spy_options_2024.parquet data/spy_options_2025.parquet --stocks data/SPY_stock.csv --report reports/spy_two_sided.json
python -m unittest discover -s tests -v
```

Repeat with `QQQ` and `IWM`. The source options files were restored and checked against the SHA-256 values in the original local import manifests before this run. The project does not turn this study into a trade signal.
