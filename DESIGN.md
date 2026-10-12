# BTC Perpetual Opportunity Tool: design document

Answers section 38 (A to V) of the specification. Everything is informational and probabilistic. Backtests so far show **no proven edge**; the tool is for paper-trading and learning.

## A. Architecture
```
GitHub Actions (every 5 min)                      Streamlit Cloud (free)
  worker.py                                         app.py  (reads the repo's files)
   ├─ engine.py      regime, early setup, levels     ├─ Home / Decision Desk / Analysis
   ├─ analysis.py    scores, stage, zones, odds      ├─ Wallet / Trade History / Learning
   ├─ desk.py        levels, moves, derivs, reversal ├─ Health / Settings / Backtests / Guide
   ├─ paper.py       virtual wallet, orders, exits
   ├─ advisor.py     hold / protect / book advice    Storage = files in the repo (the database)
   ├─ learn.py       post-mortems, learned filters    state.json         live state
   ├─ history.py     permanent trade record           trade_history.json permanent, never deleted
   └─ Telegram       alerts, buttons, commands        market_log.csv, flow_log.csv  recorded market data
```
One state, several interfaces: the dashboard and Telegram read and write the same trade records.

## B. Data and APIs
| Class | Data | Source | Used for |
|---|---|---|---|
| FREE, required | BTC perpetual price, OHLCV 5m to 4H | OKX public API (Bybit fallback) | everything |
| FREE, required | funding rate, open interest | OKX / Bybit public | positioning, crowding |
| FREE, recorded by us | order-book imbalance, taker buy/sell balance, liquidations | OKX public (`market/books`, `market/trades`, `public/liquidation-orders`) | order-flow component (history builds up from day 1) |
| OPTIONAL PAID | deep historical order flow / liquidation history, tick data | e.g. Coinglass, Kaiko, Tardis | longer order-flow backtests |
| NICE TO HAVE | options/IV, on-chain, ETF flows, news | various | context only, not built |
No paid API is needed. Free data limit: order-flow and OI history exist only from the day the recorder started, so those signals cannot be backtested over years yet.

## C. Features and why
Market structure (swing highs/lows), range position, volume pressure (up-volume vs down-volume), momentum (move per ATR, its acceleration), volatility (ATR percentile, compression), liquidity (distance to swing levels, key levels), higher-timeframe efficiency ratio (trend strength), funding, OI change, book imbalance, taker delta. No RSI/MACD/EMA-cross rules: each feature answers a market question (who is pressing, is the structure intact, where is the liquidity).

## D. Leading, confirming, lagging
- **Leading**: compression, repeated support defence, liquidity sweep + reclaim, selling-volume fading, higher low, OI/funding build-up.
- **Confirming**: break and hold of a key level, momentum acceleration, volume expansion, retest holding.
- **Lagging**: trend-strength ratio, regime label, moving-average style context (used only for context).

## E. Stage 1 to 6 logic
Stage 0 nothing; 1 accumulation/distribution developing (score 40+); 2 early setup (score 65+, few false-signal flags); 3 momentum confirming (breakout confirmed in the direction); 4-5 trade active and managed; 6 exhaustion risk (exhaustion score 70+). Stage is recomputed every scan and **can move backwards**; each change is logged in the Stage history table.

## F. Long and short logic
Short is the exact mirror of long (the same code runs on mirrored prices), so no side is favoured by design. Long score: price near range low, liquidity sweep, higher low, selling volume fading, compression, momentum turning up, minus a penalty if the higher timeframe is against.

## G. Range logic
Range = high/low of the last ~96 hours; mid-range is a no-trade zone. Lower edge = long candidates, upper edge = short candidates, but only with extra evidence (sweep, volume, momentum turn). Support touch alone is never a signal.

## H. Breakout and false-breakout logic
BREAKOUT WATCH (compressed volatility at an edge) then BREAKOUT CONFIRMED (close beyond the range with volume 1.3x normal). Also detected: breakout retest, failed breakout (back inside the range), failed retest (reversal evidence).

## I. Expected-move calculation
Direction-agnostic history on 5+ years of 1H data: for every past hour, how far did price travel up and down in the next 24h/72h, grouped by volatility (calm/normal/wild). Expected/strong/extended zones are the 50th, 75th, 90th, 95th percentile of that travel. Built by `move_stats.py` (research workflow).

## J. 500 / 1,000 / 2,000 / 5,000 / 10,000+ point detection
`moves.py`: each size is shown as points, % of price and multiples of the 4H ATR, so the **class adapts**: SMALL under 1 ATR, MEDIUM 1-2, LARGE 2-4, VERY LARGE over 4. Next to each: how often price historically travelled that far in 24h and 72h from the same volatility bucket. Large Move Potential score = the chance of a 2,000-point move now relative to the best volatility bucket.

## K. Entry zones
Early zone (price -0.3 to +0.1 ATR), confirmation entry (above the last 8-bar extreme), retest zone around the confirmation level, late/avoid zone (one ATR beyond confirmation). The dashboard states whether the setup is early, between zones or late.

## L. Stop and invalidation
Hard invalidation = beyond the last swing point supporting the idea; preferred stop = below the recent low minus 0.4 ATR, at least 0.8 ATR away; emergency = 3 ATR. Never a fixed percentage. The Decision Desk explains why the setup is invalid beyond each level.

## M. Targets and profit booking
Targets come from the historical move quantiles when available, otherwise ATR multiples of the risk. T1 to T3 and an extended zone. Partial booking percentages are **yours to choose** (Decision Desk planner); the live paper rule is the tested fixed 4R (or staged for the early signal), unchanged.

## N. Post-entry monitoring
`advisor.py` every scan: stage (entry, profit developing, momentum strong, target approaching, exhaustion watch, profit booking, reversal detected, setup failing), momentum, volume, structure break, give-back of profit, exhaustion score, reasons in plain language.

## O. Hold vs book
Compares remaining distance to target (R) against risk to the protected stop (R), and shows what booking now locks in. Statuses: HOLD (strong / more possible / thesis intact), HOLD BUT PROTECT, PARTIAL ADVISED, PROFIT-BOOKING ZONE, REVERSAL RISK, thesis invalidated. Wording stays probabilistic.

## P. Trailing stop
Advice: breakeven after +1R, structure trail after +1.5R, ATR trail (3 ATR from the best close) when exhaustion is above 50. Backtests (V6, V7) compare fixed, staged, ATR trailing and structure trailing on the same entries. Result so far: **no style is clearly better than the live rule**, so the live rule is not changed.

## Q. Probability and backtesting
No look-ahead (only closed candles), per-side fees, stop checked before target inside a bar, train/test split, and 'fresh' trades older than 730 days never used to choose rules. V7 scorecard: hit rate of each target before the stop, hours to target, stop and false-signal rate, MFE/MAE, how often 500...10,000 points were travelled, four ways to trade (early+hold, early+partial, late+fixed, late+trailing), entry delay, splits by side/year/volatility/trend strength.

## R. False-signal filtering
Ten checks (volume, structure, liquidity, higher timeframe, momentum, rejection wick, liquidity trap, failed breakout, volatility, mid-range). Five or more flags, or a weak score, produce **NO TRADE**, which is a valid output.

## S. Free stack
Python, pandas, numpy, requests, Streamlit, GitHub Actions, Telegram Bot API. Storage in JSON/CSV files in the repo. Cost: 0.

## T. Roadmap
- **V1 (done)**: scanner, regime, early signal, levels, Telegram alerts, dashboard.
- **V2 (done)**: paper wallet, lifecycle, advisor, history, learning, backtests V1-V6.
- **V3 (done)**: Decision Desk, key levels, point-move classes, reversal evidence, derivatives/order-flow recorder, V7 scorecard, stage history, 30m timeframe.
- **Next (needs data over time)**: calibrate the score weights on paper-trade results (100+ trades), order-flow and OI signals backtested once months of `flow_log.csv` exist, re-test strategies per regime.

## U. What $0 can realistically build
Everything above. What it cannot do: tick-level order flow history, guaranteed fills, real execution (deliberately not connected).

## V. Deliberately NOT included (complexity without proven value)
Machine-learning price prediction (overfits), automatic strategy changes after each loss (overfits: the tool only *proposes* filters and verifies them on shadow trades), real exchange connection before an edge is proven, options/on-chain/news feeds.

## Honest limits
The score weights are not calibrated; the early-signal engine tested negative; trend_pullback is weakly positive but unproven; order-flow history is short. Treat all output as research.
