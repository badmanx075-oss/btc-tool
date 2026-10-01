"""Paper-trading of the one strategy that weakly survived V4/V5: trend_pullback.
Rules mirror the backtest: stop 3xATR(1H), single target 4R, expiry 120 x 1H bars, 24-bar cooldown. No real money."""
import engine as E, backtest_v4 as W

START = 20000      # virtual wallet in INR (change to 10000 if you like)
RISK_PCT = 1.0     # % of wallet risked per trade (distance to stop)
COST, BAR = 0.0010, 3600000.0
NAMES = ("trend_pullback", "breakout_retest", "squeeze_breakout", "slow_trend")

def run(S, send, now):
    P = S.setdefault("paper", {"open": None, "closed": [], "n": 0, "last_entry_ts": 0})
    P.setdefault("balance", START); P.setdefault("start", START); P.setdefault("peak", P["balance"]); P.setdefault("max_dd_pct", 0.0)
    h = E.candles("1H", 300); px = float(h.c.iloc[-1]); t = P["open"]
    if t:
        k, res = t["side"], None
        for c in h[h.ts > t["entry_ts"]].itertuples():
            if (c.l <= t["sl"]) if k == 1 else (c.h >= t["sl"]): res = ("STOP", t["sl"]); break   # same-bar = stop first
            if (c.h >= t["tp"]) if k == 1 else (c.l <= t["tp"]): res = ("TARGET", t["tp"]); break
        if not res and (h.ts.iloc[-1] - t["entry_ts"]) / BAR >= 120: res = ("EXPIRED", px)
        if res:
            R = (res[1] - t["entry"]) * k / t["risk"] - COST * t["entry"] / t["risk"]
            t.update(outcome=res[0], exit=float(res[1]), R=round(float(R), 3), closed=now.isoformat(timespec="seconds"))
            pnl = float(R) * t.get("risk_inr", 0.0); t["pnl_inr"] = round(pnl, 2); P["balance"] = round(P["balance"] + pnl, 2)
            P["peak"] = max(P["peak"], P["balance"]); P["max_dd_pct"] = max(P["max_dd_pct"], round((P["peak"] - P["balance"]) / P["peak"] * 100, 2))
            P["closed"].append(t); P["open"] = None; tot = sum(x["R"] for x in P["closed"]); ret = (P["balance"] / P["start"] - 1) * 100
            send(f"📝 PAPER TRADE CLOSED\n{t['id']}\n{res[0]} at ${res[1]:,.0f}\nResult: {R:+.2f}R = {'+' if pnl >= 0 else '-'}₹{abs(pnl):,.0f}\n"
                 f"💰 Wallet: ₹{P['balance']:,.0f} ({ret:+.1f}% since start) | Max drawdown {P['max_dd_pct']}%\nTrades: {len(P['closed'])} | Total {tot:+.2f}R")
        return
    h1 = W.prep(h); i = len(h1) - 2          # last fully closed 1H bar
    if h1.ts.iloc[i] - P["last_entry_ts"] < 24 * BAR: return
    Sg = {n: [] for n in NAMES}; W.side_sigs(h1, 1, Sg, i, i + 1); W.side_sigs(h1, -1, Sg, i, i + 1)
    if not Sg["trend_pullback"]: return
    k = Sg["trend_pullback"][0][1]; e = float(h1.c.iloc[i]); risk = 3 * float(h1.atr.iloc[i]); P["n"] += 1
    risk_inr = round(P["balance"] * RISK_PCT / 100, 2); notional = risk_inr * e / risk
    P["last_entry_ts"] = float(h1.ts.iloc[i]); side = "LONG" if k == 1 else "SHORT"
    tid = f"PAPER-{side}-{now.strftime('%Y%m%d')}-{P['n']:03d}"
    P["open"] = dict(id=tid, side=k, entry=e, sl=e - k * risk, tp=e + k * 4 * risk, risk=risk, risk_inr=risk_inr, notional_inr=round(notional, 2), entry_ts=float(h1.ts.iloc[i]), created=now.isoformat(timespec="seconds"))
    send(f"📝 PAPER TRADE OPENED (no real money)\n{tid}\nStrategy: trend_pullback (backtest edge weak/unproven)\nEntry: ${e:,.0f}\nStop (3xATR 1H): ${e - k * risk:,.0f}\n"
         f"Target (4R): ${e + k * 4 * risk:,.0f}\nExpires: 5 days.\n💰 Wallet ₹{P['balance']:,.0f} | Risk this trade ₹{risk_inr:,.0f} ({RISK_PCT}%) | Position ₹{notional:,.0f} (~{notional / P['balance']:.1f}x)\nBacktest win rate ~33%, so losing streaks are normal.\nVirtual money, not advice or prediction.")
