# BTC Perpetual Tool: guide

Informational and statistical only. Virtual money, no real orders. Backtests show **no proven edge** yet.

## What runs by itself
- A GitHub Action (`scan`) runs about every 5 minutes: reads BTC data, builds the analysis, runs the paper wallet, answers Telegram commands for ~3.5 minutes, then saves `state.json`.
- The Streamlit dashboard (`app.py`) only displays what the scanner saved, plus a live price.
- Strategies in the paper wallet: **Trend Pullback** (backtested, weak edge) and **Early Signal** (experimental).

## Daily use
1. Open Telegram. You get order opened / closed messages with "Kyun liya" and "Kya hua", and a 👍/👎 button after every closed trade.
2. Open the dashboard: Home (live position + advisor status), Analysis (full snapshot), Wallet (journal, ledger), Health (is everything alive).
3. Send `/status` or `/wallet` any time.

## Telegram commands
`/ping` alive? | `/status` | `/wallet` | `/ledger` | `/trades` | `/analysis` | `/lessons` | `/approve N` / `/revert N` (learned filters)
`/config` show settings | `/set name value` e.g. `/set trend_pullback.risk_pct 2` | `/notify name on|off` e.g. `/notify morning off`
`/note ID text` | `/myexit ID price` (your own exit vs the system) | `/weekly` | `/demo` (test trade, wallet untouched) | `/resetwallet confirm`
Replies come within seconds while the scanner is listening, otherwise on the next run.

## Settings (config.json)
Wallet start amount, leverage, fees, risk % per trade, stop/target, expiry, alert on/off, morning/evening hour. Change with `/set` or by editing `config.json` on GitHub.
The start amount only applies before the first trade (or after `/resetwallet confirm`).

## One-time research runs
Actions -> **research** -> Run workflow (days 2000). Builds `move_stats.json` (expected-move odds by volatility) and `backtest_v6_results.json` (exit styles). The Analysis and Backtests tabs fill in after that.

## Honest limits
- No proven profitable signal yet; judge it by the paper results over months, not days.
- Order-flow and open-interest signals need months of recorded data (`market_log.csv`).
- There is no real exchange connection and none should be added before the edge is proven.

## Upgrading from the previous version (your data is kept)
- `state.json` and `market_log.csv` are NOT in the upload set, so GitHub keeps your existing copies.
- On the first scan the new code carries over: all old early-signal trades, the open paper trade (it gets margin locked in the new wallet), the order log, wallet balance, Telegram status and the recorder history.
- GitHub also keeps every earlier version of `state.json` under the repo's commit history, so nothing is ever truly lost.
