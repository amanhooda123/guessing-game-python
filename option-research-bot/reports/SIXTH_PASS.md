# Sixth pass: Greek factor hypothesis and replay — 2026-10-11

## Scope and factor research

An options screen cannot literally observe every determinant of future profit. The [Options Industry Council](https://www.optionseducation.org/advancedconcepts/volatility-the-greeks) explains that delta (price sensitivity), gamma (change in delta), theta (time decay), vega (volatility sensitivity) and implied volatility are model estimates, not a probability of a winning trade. A quoted delta of 0.30 does **not** mean a 30% chance of making money.

This **predeclared, unoptimized hypothesis** buys one long call when its stock's prior 20-day average exceeds its prior 60-day average and the last prior close exceeds the prior close 20 sessions earlier. Long puts require the reverse. It requires 45–90 calendar days to expiry, absolute delta 0.15–0.55, positive gamma/vega, negative theta with per-day theta/ask at most 3.5%, implied volatility no more than 1.5 times 20-return realized volatility, bid/ask width at most 20% of ask, positive displayed sizes, at least 10 daily trades, and one-contract ask plus modeled 1.5% FX at most the budget. It ranks surviving contracts by proximity to 0.30 absolute delta, spread, theta decay and IV/realized volatility. These thresholds were chosen as a plausible screen **before** this pass's replay; they are not fitted to maximize the reported return. The last 20/60 underlying observations for a signal are strictly earlier than the option quote date.

The [official Cboe 15:45 ET feed](https://datashop.cboe.com/option-eod-summary) can supply contemporaneous bid/ask/size and, with the additional paid calculations, the Greeks. The one-day public sample includes actual Greeks but **no prior 60-day underlying history and no exit dates**. The code correctly reports zero backtestable candidates from it, rather than fabricating a trend, realized volatility or return.

Individual company earnings dates, other news and macro announcements, corporate actions, changing rates/dividends, actual order fills, and contemporaneous CAD/USD are **not in the available research archive**. An earnings-event gate requires a point-in-time calendar before company signals can be trusted. Screening every U.S. company requires continuous full-universe historical files; this archive does not have them. [TMX has historical Montréal Exchange option quote products](https://www.tmx.com/en/newsroom/press-releases?id=279&month=2&year=2015), but [Wealthsimple states Canadian security options are currently unavailable](https://help.wealthsimple.com/hc/en-ca/articles/9606205720987-Enable-options-trading-in-your-investing-account), so Canadian contracts are outside the intended Wealthsimple workflow.

## Exploratory replay on available 2024–2025 files

The only continuous local bid/ask files cover **SPY, QQQ and IWM**, not individual companies. The archived quotes have no Greeks. `option_lab.factor_replay` estimates Black–Scholes–Merton IV/Greeks from the observed bid/ask midpoint, assuming a fixed 4% interest rate and 1.5% dividend yield. U.S. stock options are American style, so this is an imperfect approximation. The archive's original provenance and fill quality remain unverified. Entry signals use the prior day's quote and buy at the following observed ask; exits follow a signal at +35% net marked gain, −50% loss, 10 quote days or 14 DTE, then sell at the following day's bid. Both sides deduct a hypothetical 1.5% FX conversion. A missing mark or exit stops the replay. Each line uses a **separate US$200-equivalent starting account**, not one combined portfolio.

| Symbol | 2024 result at US$150 premium cap | 2025 result at US$150 premium cap | 2025 result at US$30 premium cap |
| --- | --- | --- | --- |
| SPY | +46.60% marked, **1** closed trade | 0%, **0** trades | 0%, **0** trades |
| QQQ | 0%, **0** trades | 0%, **0** trades | 0%, **0** trades |
| IWM | +114.04% **marked with an open position**, 15 closed trades, −39.03% maximum drawdown | +54.50%, **6** closed trades, −30.69% maximum drawdown | 0%, **0** trades |

IWM's 2024 return includes an unclosed position, and the 2025 result has only six trades. These are *not* evidence of a repeatable profit for a broad-company portfolio. The 2025 ETF archive has already been inspected in earlier passes, so it is **not an untouched holdout** for this new hypothesis. With a US$30 cap this screen bought nothing in the available 2025 archive. The combination of affordability and moderate delta is especially restrictive; relaxing it just to show a return would be post-hoc fitting.

## Reproduce and next gate

```sh
python -m unittest discover -s tests -v
python -m option_lab.factors --files data/cboe_sample.zip --budget-usd 150
python -m option_lab.factor_replay --options data/IWM_options.csv --stocks data/IWM_stock.csv --start 2025-01-01 --end 2025-12-15 --capital 200 --premium-cap 150 --report reports/iwm_factor_2025.json
```

Detailed ETF JSON reports are included. Historic source details and instructions for obtaining the public archive are in [RESEARCH.md](RESEARCH.md). The actual Cboe ZIP is obtainable from its [official sample link](https://datashop.cboe.com/download/sample/217); raw data remain excluded from git. The research gate remains **NO TRADE** until continuous, licensed multi-company option and underlying histories, point-in-time corporate events, and a future untouched period can support a properly powered test. Neither a backtest nor Greek thresholds can guarantee a profit.
