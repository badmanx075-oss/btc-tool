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

## Trade History tab (permanent record)
- Tab **📒 Trade History** lists every trade ever taken (paper wallet) or alerted (early signal): Indian time (IST) for open and close, **why it was taken**, entry/stop/targets, result, R, P/L in ₹, the tool's own review, **your feedback** (👍/👎/note from Telegram) and a full timeline. Filter, search, open one trade, or download everything as CSV.
- It is stored in its own file `trade_history.json` (written by the scanner each run). Page refresh, code upgrades, a wallet reset or a damaged `state.json` never delete it. Records are only added or updated, never removed; an update never blanks an existing field.
- Old trades are imported automatically on the first scan after you upload the new files.
- A damaged history file is moved aside (`trade_history.json.damaged-...`), never overwritten.

## Changing the tool later (safe way)
- Strategy rules: `strategies.py` (signals) and `config.json` / `/set` (risk, stop, target, expiry). The history is unaffected.
- New columns in the history tab: add the field in `history.py` (`from_paper` / `from_signal`) and one entry in the table in `app.py`. Old records keep working; the full original trade is always kept under `raw`.
- Changing the file format: bump `SCHEMA` in `history.py` and add a step in `_upgrade()`.
- Always upload the files together: `worker.py`, `paper.py`, `history.py`, `app.py`, `.github/workflows/scan.yml`.

## More Telegram commands
`/help` all commands | `/history [n]` last n trades | `/timeline ID` one trade's full story (IST) | `/stats` win rate, avg R, drawdown, streaks and an honest verdict | `/today` today's summary | `/pause` stop NEW trades and alerts (open trades still managed) | `/resume`.
The bot's command menu (the "/" button in Telegram) is filled in automatically on each run.

## Performance section (Trade History tab)
Win rate, average R with its error margin, profit factor, max drawdown, streaks, equity curve, and splits by side, strategy, outcome, weekday and time of day (IST). Below 30 closed trades it says "too few, noise": do not change any rule from small samples.
Upload together: `stats.py` (new), `worker.py`, `paper.py`, `app.py`.

## Decision Desk tab (new)
Answers the specification's 27 real-time questions in plain words, before entry (1-16) and after entry (17-27), plus: key levels ladder (previous day / 7-day high-low, VWAP, swing levels, round numbers, merged into confluence zones with distance in points and ATR), point-move classes (500 to 10,000 points as points, % and 4H-ATR multiples with historical odds), multi-timeframe table (5m, 15m, 30m, 1H, 4H), reversal evidence, derivatives and order-flow reading (funding, open interest vs price, taker buy/sell, liquidations), stage history (the model can move backwards), and a profit-booking planner where you choose the percentages.
New data recorded every scan: `flow_log.csv` (taker buy/sell balance, liquidations). It needs hours to days of scans before it shows anything.

## V7 scorecard and design document
Run **Actions -> research -> Run workflow** (days 2000) once more: it now also builds `backtest_v7_results.json` (target hit rates before the stop, hours to target, stop/false-signal rate, MFE/MAE, how often 500...10,000 points were travelled, early vs late, four ways to trade, splits). The Backtests tab shows it. `DESIGN.md` (also inside the Guide tab) is the architecture and methodology document (sections A to V of the specification).

Files for this upgrade: `levels.py`, `moves.py`, `reversal.py`, `derivs.py`, `flow.py`, `desk.py`, `decision.py`, `backtest_v7.py`, `DESIGN.md` (new) and `worker.py`, `app.py`, `.github/workflows/scan.yml`, `.github/workflows/research.yml`, `GUIDE.md` (changed).

## Continuous testing + review pack (new)
- Tool khud 24x7 paper-trade karta rehta hai. Aapko kuch chalana nahi hai.
- Har trade ke saath entry ke waqt ka poora snapshot (grade, scores, session, MTF, crowding, regime) save hota hai.
- Weak (score 50-64) early signals "near-miss" shadow trades ban jaate hain: bina risk ke extra data, taaki pata chale min_score sahi hai ya nahi.
- Dashboard ka **📦 Review** tab: progress bar (N/30 trades), calibration tables, aur download buttons (JSON + short .md).
- Telegram: `/export` (dono files), `/readiness`, `/settings` (ON/OFF buttons), `/deliveries` (last sends). 10/20/30/50/75/100... trades par milestone alert; 30+ par pack khud aa jata hai.
- Naye alerts: "Setup ban raha hai (3/4)", "Stage badla", "B/C-grade near-miss". Cooldown se repeat nahi hote.
- Jab 30+ trades ho jayein: pack ki file mujhe bhejo, main rules tune karunga.
