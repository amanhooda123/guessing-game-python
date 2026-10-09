# Fifth pass: real company option quotes

## Data source and scope

Cboe's [Option EOD Summary](https://datashop.cboe.com/option-eod-summary) covers U.S. listed equity, ETF and index options, with 15:45 ET option NBBO bid/ask and size, underlying bid/ask, expiry and strike. Its [published layout](https://datashop.cboe.com/documents/Option_EOD_Summary_Layout.pdf) documents the fields. Historical full-market files are a purchased product. A 15:45 displayed quote is a better replay input than a post-close synthetic quote, though even a displayed NBBO does not prove an order filled.

The [public sample ZIP](https://datashop.cboe.com/download/sample/217) is explicitly for demonstration. It is dated **2023-08-25** and has two alternative versions of the same date, not two days. The importer selected `cgi_or_historical` and excluded index options, nonstandard contracts, zero bids/sizes, crossed quotes and absent underlying prices.

| Audit | Result |
| --- | ---: |
| Raw option rows | 32,672 |
| Usable SPY quotes | 6,722 |
| Usable TSLA quotes | 3,784 |
| Index or nonstandard rows excluded | 20,804 |
| Invalid/one-sided rows excluded | 1,362 |
| Covered dates | **1** |

On this one date, a simple liquidity screen found 66 SPY and 24 TSLA contracts with 30–90 calendar days to expiry, positive bid, at least 10 daily trades, bid/ask width at most 25% of ask, and premium including 1.5% conversion at most **US$30**. This counts possible contracts, **not successful trades or a probability of profit**. The daily trade volume may reflect trades after 15:45 and must not be used to claim a 15:45 execution decision.

## What the code now does

`python -m option_lab.cboe --files ... --out data/cboe` streams daily Cboe CSV/ZIP files into normalized option and underlying files, filters unusable quotes, rejects duplicate dates and conflicting underlying prices, and prints an audit by symbol. `--symbols` restricts to arbitrary equities; omit it for all standard equity symbols in supplied data. The stock `close` field in the normalized file is the **15:45 underlying midpoint**. It is suitable as a contemporaneous spot proxy but is not the official closing price. The raw files and converted CSV are git-ignored.

## Result and next test

**No new return or profitable algorithm can be measured from this sample.** A broad out-of-sample study needs continuous daily Cboe historical files (or comparable licensed point-in-time option NBBO) across training, validation and untouched test periods. Use company histories with delisted names where available, commission/FX and spread assumptions, missing-quote failures, a precommitted signal rule, then forward paper trading. Choosing rules repeatedly against the same final period would overfit it. The earlier ETF and individual-stock studies also did not validate a profitable edge. The Wealthsimple account remains disconnected and no orders are placed.
