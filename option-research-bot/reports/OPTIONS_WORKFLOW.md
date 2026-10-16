# Options workflow for the same premarket-reversal strategy

The strategy now has one options-focused interface: `premarket-options plan`, `monitor`, and `evaluate`. The underlying premarket reversal determines which option direction is eligible. Contract selection, sizing, exit signals and profit/loss use option data. No broker order or market-data connection is created by these commands.

## Same signal, options implementation

| Underlying observation | Confirmation at 09:45 ET | Options intent |
|---|---|---|
| Premarket down versus previous session close | Completed opening bars move up and reclaim the opening VWAP proxy | Buy to open a call |
| Premarket up versus previous session close | Completed opening bars move down and break below the opening VWAP proxy | Buy to open a put |
| No valid confirmation, missing data or event risk | No qualified setup | No entry plan |

The [existing rule specification](PREMARKET_REVERSAL.md) still applies: score at least 75; separately sufficient earlier net option outcomes for empirical calibration; same first observed post-signal chain; 14–45 DTE; delta magnitude 0.45–0.70; liquidity, IV/RV, Greek and news/event checks. The ranking score is not a win probability. Current U.S./Canadian company-directory support is retained, and absent Canadian observations are not filled using U.S. contracts.

## What each options trade card contains

- Exact option symbol, call/put, strike, expiration, currency and multiplier.
- Buy-to-open limit intent at the observed ask, with the feed-supplied tick size. It is an indicative plan, not an execution.
- One contract when account cash, existing premium exposure, daily loss limit, setup score and past-outcome calibration permit it; otherwise zero proposed contracts and explicit blocking reasons.
- Full-premium reserve using the existing research model's 1% option-price allowance and hypothetical 0.65 per-contract fee. The indicative limit does not authorize a fill above that limit. Actual fill/fee inputs replace estimates when monitoring a position.
- Option-bid thresholds corresponding to +30% / −20% net return, after modeled exit costs, plus the existing 11:00 ET time exit. Thresholds are observations, not guaranteed stop prices.
- Separate setup ranking, historical empirical calibration information and Greek exposures.

Accounts are in native USD/CAD. Full premium is limited to 0.5% of equity per proposal and 2% total open/reserved premium. Several cards cannot reuse the same available cash. A 1% realized daily account loss blocks new proposals. These are unchanged research defaults, not proven optimums. There is no absolute $30 or $150 premium cap.

## Monitor the option itself

Supply actual entry premium, contract quantity and total entry fee. The monitor uses the latest observed bid, explicit exit-fee/slippage assumptions and the 100-share multiplier. It reports modeled net liquidation P&L and return on the actual all-in entry debit. It never substitutes the stock's percentage move for the option's return.

Both long calls and long puts close with a **sell-to-close** intent for the same contract. A favorable underlying move can coexist with an option loss. Missing, stale, future, wrong-country/currency or insufficient-size quotes cannot establish a current exit value. A time exit that is overdue remains visible even when a usable quote is missing. Exit signals are for paper/manual review, not orders or realized fills.

For illustration only: one standard option filled at 2.00 with a 0.65 entry fee has a 200.65 entry debit. With 1% adverse exit slippage and a 0.65 exit-fee assumption, the observed bid needed for +30% net is approximately 2.6414; the −20% net threshold is approximately 1.6280. These are mathematical thresholds, not valid exchange order increments or historical trade results. The monitor recalculates them from each actual entry.

OIC primary references explain [premium and contract units](https://www.optionseducation.org/optionsoverview/options-basics) and [closing the same option position](https://www.optionseducation.org/optionsoverview/leverage-risk). Nonstandard deliverables remain excluded.

## Run

From `option-research-bot`, install the package to obtain the short command, or use the module form below. The existing scanner needs `exchange-calendars==4.13.2`; the full research-test suite also uses `pyarrow==26.0.0`.

```sh
python -m option_lab.premarket_options plan --input /path/to/point_in_time_input.json --accounts /path/to/accounts.json --positions /path/to/open_positions.json --report reports/options_plans.json
python -m option_lab.premarket_options monitor --positions /path/to/open_positions.json --quotes /path/to/observed_option_quotes.json --as-of 2024-01-18T15:00:00Z --report reports/options_monitor.json
python -m option_lab.premarket_options evaluate --candidates /path/to/historical_candidates.json --quotes /path/to/observed_option_quotes.json --currency USD --report reports/options_replay.json
```

The plan command accepts the existing scanner input (`as_of`, `universe`, `daily`, `bars`, `context`, `quotes`, optional `completed_history`). Its option quotes additionally require `strike` and `tick_size`; it does not infer either from an ambiguous symbol. `--positions` is optional for a new account with no positions.

`accounts.json` is an object keyed by `USD` and/or `CAD`. Each supplied account needs numeric `equity`, `available_cash`, `daily_start_equity` and `realized_pnl_today`. Use the actual account's values; the software does not assume the earlier illustrative US$100,000 account.

Each open-position record needs `country`, `symbol`, `currency`, `option_symbol`, `right`, `multiplier` (100), positive integer `contracts`, timezone-aware `entry_time`, actual `filled_premium` per share and explicit `entry_fee_total`. Strike and expiration can be retained for recordkeeping. Quote records use country, symbol, currency, option symbol, timezone-aware `quote_timestamp`, bid, ask and displayed sizes. Monitoring quotes must be newer than the entry and at most ten seconds old at the supplied as-of time. Values are conditional on the supplied observations, not independently verified broker data.

The evaluate command uses the existing real-quote option replay and its historical coverage manifest. It does not accept daily-stock proxy returns as evidence of option profitability. It still requires complete session coverage and held exits for account-return measurement.

## Validation and current state

65 tests pass. New tests check net option P&L when the stock rises but the option loses, closing a profitable put by selling it, fees/multiplier/slippage in thresholds, stale/future/cross-country quotes, insufficient size, shared cash, existing exposure, account loss limits, missing metadata and absent empirical confidence.

The previous 2024–2025 opening-gap stock diagnostics and one-day stock check remain research about the signal only. No new options backtest result is claimed. The full-market historical option-quote and calibration gaps remain; the 4–5% monthly account-profit target is unvalidated. A +30% option-trade target is not a 30% account return or a promise of monthly profit.
