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

## Trade confirmation (new)
- Trade khulne ke baad tool dekhta hai ki market sach mein follow-through de raha hai ya nahi (6 checks: confirm level, +0.5R, momentum, 15m/1H direction, order flow, reversal flags).
- 4/6 pass (aur bhaav aage chala ho) => Telegram "✅ TRADE CONFIRM HUA" + dashboard par green banner. Baad mein 2/6 ya kam => "⚠️ CONFIRMATION KAMZOR".
- Sirf jaankari hai: trade ka stop/target nahi badalta. Alerts `/settings` mein "Trade confirm" button se on/off.
- Commands: `/settings` (ya `/setting`), `/readiness` (ya `/ready`). Bot sirf scan-run ke dauraan jawab deta hai (GitHub cron kabhi 10-30 min late hota hai).

## Time Intelligence + Session Breakout + Daily loss guard (new)
- **🕒 Time tab / `/timing`**: pichle 1 saal ki 1H candles se: kis ghante (IST) kitni range, upar kitne points, neeche kitne points, 500+/1000+ points ki sambhavna, sessions, weekday. Worker khud ~3 din mein rebuild karta hai (time_stats.json). Pehli baar ~1 minute lagta hai.
- **Active window alert**: HIGH-activity ghanta shuru hone se ~30 min pehle Telegram alert (typical points ke saath). `/settings` mein "Active window" button se band kar sakte ho.
- **Time-aware decision**: har trade ke saath us ghante ki class (HIGH/MEDIUM/LOW) save hoti hai; Review/Time tab mein dikhta hai ki tool ke apne trades kis ghante mein jeete/haare. `timing.skip_low_activity` (default off) on karoge to LOW ghante mein naye trades nahi khulenge (`/set skip_low_activity on`). Ye sirf tab on karo jab data dikhaye ki LOW ghante mein loss zyada hai.
- **Session Breakout strategy** (experimental, risk 0.3%): 6 ghante ki tang box ka breakout + strong candle + volume 1.3x+ + 4H trend virodh mein nahi + LOW ghanta nahi. Stop box ke doosri taraf, target 2R, 24h expiry. Confirmation tracker isse bhi chalta hai. Backtest: research workflow chalao (V8): time classes pehle aadhe data se, test baaki aadhe par.
- **Daily loss guard**: aaj ka realised loss 3% (`risk.max_daily_loss_pct`) tak pahunche to naye trades band, kal tak. Khule trades chalte rahte hain.
- Direction ke baare mein: har ghante ka up/down bias zyadatar noise hota hai, isliye tool use "significant" tabhi kehta hai jab bahut saaf ho.

## Multi-method analysis + Confluence strategy (new)
- 7 alag tareeke har scan par market ko parakhte hain: Trend (EMAs), Market structure (HH/HL, break of structure), Candlestick patterns (engulfing, hammer, shooting star, morning/evening star, doji, inside bar), Support/Resistance, Momentum (RSI+MACD), Bollinger bands, Volume (spike + OBV). Har ek LONG / SHORT / neutral vote deta hai aur kaaran batata hai.
- Live extra raay (vote nahi, sirf dikhti hai): order flow, OI+price, crowding, multi-timeframe.
- Dashboard Home par "🧩 Multi-method analysis" table; Telegram `/methods`; jab 4+ tareeke ek taraf aayein to alert.
- **Har trade** (kisi bhi strategy ka) ke saath "🧩 Doosri raay" jaati hai (entry ke waqt kitne tareeke saath/khilaaf the) aur review pack mein `by_methods_agree` se pata chalega ki jab zyada tareeke saath the to trades behtar the ya nahi.
- **Confluence strategy** (experimental, risk 0.4%): 4+ tareeke ek taraf, doosri taraf 1 se zyada nahi, net score 35+. Stop aakhri swing ke paar, target 2R.
- Optional gate: `/set min_methods_agree 3` => koi bhi strategy tabhi trade legi jab kam se kam 3 tareeke saath hon (default 0 = off).
- Backtest V9 (research workflow): koi parameter fit nahi, 3 fixed strictness levels, har half, har saal, long/short alag.

## Price-action chart, timeframe-wise S/R, aggressive buy/sell (new)
- **📈 Chart tab**: candlestick chart (5m/15m/1H/4H), EMA20/50, swing points, candle patterns (▲ bullish / ▼ bearish, sirf support/resistance ke paas wale), support/resistance lines, kai-timeframe confluence zones (shaded), tool ki apni entry (neela) / stop (laal) / target (hara) lines, purane trades ke markers, volume, aur daayen taraf har price par buy (hara) vs sell (laal) volume.
- **Support/Resistance timeframe-wise** (5m, 15m, 1H, 4H, 1D): nazdeeki 2 support + 2 resistance, kitni baar bhaav palta (touches), doori. Jahan kai timeframe milte hain wo "confluence zone" sabse mazboot. Telegram: `/levels`.
- **Aggressive buy/sell**: taker (market order) side se pata chalta hai kaun dabaav daal raha hai. State: AGGRESSIVE BUYING/SELLING, MILD, ya NORMAL. Kaun se price zones par buying/selling zyada hui (4h) aur sabse zyada trading wala price. Telegram: `/flow`; aggressive hone par alert (2 ghante cooldown, `/settings` mein "Order flow" button).
- Order-flow data scanner khud jama karta hai (orderflow_profile.json, pichle 36 ghante); poori tasveer ~1 ghante baad aati hai. Coverage % dikhata hai ki kitne trades pakde gaye.
- Order-flow ki halat har trade ke saath entry ke waqt save hoti hai (review pack mein `by_aggression`), aur multi-method "live second opinion" mein bhi dikhti hai.
- Chart ke liye `requirements.txt` mein `plotly` hona zaroori hai: file upload karke Streamlit app ko Reboot karo.

## Move radar + Smart exit (new)
- **🚀 Move radar** (Home card, Telegram `/radar`, alert "GOOD MOVE COMING?"): score 0-100 jo bataata hai ki badi move aane ki sambhavna kitni hai. Parts: volatility dabna (compression), tang box, volume build-up, active time window, bhaav box ke kinare, 7 tareekon ka jhukaav, + live order flow / OI.
- Flow: **GOOD MOVE COMING?** (score 65+) -> trigger levels batata hai -> **MOVE SHURU** (box tootne par) -> **MOVE COMPLETE** (expected points ~80% ya thakaan ke sanket) ya **MOVE FAIL** (fake-out). 8 ghante mein kuch na ho to watch khatam. Natije dashboard mein "kitni baar sach nikla" table mein jama hote hain.
- Radar sambhavna batata hai, guarantee nahi. Backtest V10 (research workflow) aise napta hai: score 65+ ke baad agle 6 ghante mein badi move (2.5x ATR) ki dar, base rate se kitni zyada, aur unseen half par.
- **Smart exit** (paper trades, default ON): trade tab band hota hai jab (1) +1R se zyada profit ho aur thakaan 70+ / profit-booking zone ho, (2) expected move poora ho jaye, ya (3) trade 10 ghante tak chala par kuch nahi hua (stall, aur confirm nahi hua). Ye trade ko lamba chalne se rokta hai.
- Asli rule (stop/target) wali copy **shadow** mein chalti rehti hai. Review tab mein "Smart exit vs asli rule" dikhata hai ki smart exit sach mein behtar tha ya nahi. Band karna ho: `/set smart_exit off`. Settings: `exits` section (`/config`).
