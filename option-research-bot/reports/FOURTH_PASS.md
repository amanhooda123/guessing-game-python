# Individual-company universe correction — 2026-10-09

The first three studies tested **SPY, QQQ and IWM**, which are ETFs. They did **not** test every stock or every trading day. This pass adds a research-only scanner for arbitrary lists of up to 200 stock tickers per request. It does **not** establish profitability or connect to a brokerage.

## Data sources and coverage

The earlier public Parquet archive holds only three ETFs. A claimed 104-symbol static archive was unreachable at its advertised file URL (HTTP 404), so it was not used. [OnclickMedia](https://www.onclickmedia.com/About) advertises much wider historical options coverage, but its public backtest endpoint returned HTTP 502 during this pass. The [DoltHub historical options database](https://www.dolthub.com/repositories/post-no-preference/options) responded to point queries for individual companies. Its snapshots are irregular and its option-chain table lacks trading volume and bid/ask size. It does not provide today's executable option orders.

For a sample **2025-06-02** snapshot, the scanner requested eight individual names under a US$150 equivalent two-leg premium limit. Complete options and volatility responses arrived for **NVDA (120 rows), PLTR (124), TSLA (138), UBER (122)**. AAPL, AMD and BAC option queries timed out, although their volatility queries responded. RDDT returned no chain or volatility rows on that date. The exact [coverage result](company_sample_screen.json) records every ticker and error. There were **zero historical research candidates** among the four complete responses under the fixed screen. A timeout is unknown coverage, not a failed strategy.

## Scanner behavior

`option_lab.universe` accepts a snapshot date and any specified list of valid stock symbols in batches of at most 200. It filters same-expiry long calls and puts 30–75 days out with approximate +0.20/−0.20 delta, positive bids, quoted relative spreads at most 25%, total ask debit plus modeled 1.5% conversion at most US$150, and historical volatility at least 1.25 times implied volatility. The ratio is a **hypothesis**, not a probability or verified edge. Because this source lacks volume, size, recent executable quotes, and complete daily histories, the scanner always returns `NO TRADE`. Its ranked rows, when any exist, are historical research candidates only. An old snapshot can never be shown as a current trade.

```sh
python -m option_lab.universe --date 2025-06-02 --symbols AAPL AMD BAC NVDA PLTR TSLA UBER RDDT --budget-usd 150 --output data/dolthub_2025-06-02_raw.json --report reports/company_sample_screen.json
python -m unittest discover -s tests -v
```

An actual all-company, every-day historical test would require complete point-in-time option chains for the whole stock universe, contemporaneous underlying prices and corporate actions, coverage of expired/delisted symbols, and a fresh untouched evaluation period. A current scanner would additionally need a live licensed option quote feed and account-specific CAD/USD costs and permissions. No source verified in this pass provided all of those ingredients. Raw API snapshots stay local under `data/`; the small coverage summary is published.
