"""Paper trading with a virtual INR wallet and real-trade-style orders (qty, rate, fees, P&L).
Strategy = trend_pullback (the one that weakly survived V4/V5): stop 3xATR(1H), target 4R, expiry 120 x 1H bars. NO real orders are placed."""
import requests
import engine as E, backtest_v4 as W

START = 20000      # virtual wallet in INR (use 10000 if you prefer)
RISK_PCT = 1.0     # % of wallet risked per trade (distance to stop)
COST, BAR, FX_DEFAULT = 0.0010, 3600000.0, 88.0
NAMES = ("trend_pullback", "breakout_retest", "squeeze_breakout", "slow_trend")

def fx(P):
    try: P["fx"] = float(requests.get("https://open.er-api.com/v6/latest/USD", timeout=10).json()["rates"]["INR"])
    except Exception: pass
    return P.get("fx", FX_DEFAULT)

def log(P, now, oid, action, qty, price, note):
    P["orders"].append(dict(ts=now.isoformat(timespec="seconds"), order_id=oid, action=action, qty_btc=qty, price=round(float(price), 1), note=note))
    del P["orders"][:-200]

def run(S, send, now):
    P = S.setdefault("paper", {})
    for key, v in dict(balance=START, start=START, peak=START, max_dd_pct=0.0, orders=[], open=None, closed=[], n=0, last_entry_ts=0).items(): P.setdefault(key, v)
    h = E.candles("1H", 300); px = float(h.c.iloc[-1]); t = P["open"]
    if t:
        k, res = t["side"], None
        for c in h[h.ts > t["entry_ts"]].itertuples():
            if (c.l <= t["sl"]) if k == 1 else (c.h >= t["sl"]): res = ("STOP-LOSS", t["sl"]); break   # same-bar = stop first
            if (c.h >= t["tp"]) if k == 1 else (c.l <= t["tp"]): res = ("TARGET", t["tp"]); break
        if not res and (h.ts.iloc[-1] - t["entry_ts"]) / BAR >= 120: res = ("EXPIRED (5 days)", px)
        if res:
            q, fxr, gpts = t.get("qty_btc"), t.get("fx", P.get("fx", FX_DEFAULT)), (res[1] - t["entry"]) * k
            if q: gross = q * gpts; fees = COST * t["entry"] * q; net = gross - fees; pnl = net * fxr; R = net / (q * t["risk"])
            else: R = gpts / t["risk"] - COST * t["entry"] / t["risk"]; pnl = R * t.get("risk_inr", 0.0); gross = fees = net = 0.0
            t.update(outcome=res[0], exit=float(res[1]), R=round(float(R), 3), pnl_inr=round(float(pnl), 2), gross_usd=round(float(gross), 2),
                     fees_usd=round(float(fees), 2), net_usd=round(float(net), 2), closed=now.isoformat(timespec="seconds"))
            P["balance"] = round(P["balance"] + pnl, 2); P["peak"] = max(P["peak"], P["balance"])
            P["max_dd_pct"] = max(P["max_dd_pct"], round((P["peak"] - P["balance"]) / P["peak"] * 100, 2))
            P["closed"].append(t); P["open"] = None; ret = (P["balance"] / P["start"] - 1) * 100; act = "SELL" if k == 1 else "BUY"
            log(P, now, t["id"], act, q, res[1], "exit: " + res[0])
            send(f"📝 PAPER ORDER CLOSED (virtual)\nOrder ID: {t['id']}\nAction: {act} ({'close long' if k == 1 else 'cover short'})\nQty: {q} BTC\n"
                 f"Entry: ${t['entry']:,.0f} -> Exit: ${res[1]:,.0f}  [{res[0]}]\nGross ${gross:+,.2f} | Fees ${fees:,.2f} | Net {'+' if pnl >= 0 else '-'}₹{abs(pnl):,.0f} ({R:+.2f}R)\n"
                 f"💰 Wallet: ₹{P['balance']:,.0f} ({ret:+.1f}% since start) | Max drawdown {P['max_dd_pct']}%\nTrades closed: {len(P['closed'])}")
        return
    h1 = W.prep(h); i = len(h1) - 2          # last fully closed 1H bar
    if h1.ts.iloc[i] - P["last_entry_ts"] < 24 * BAR: return
    Sg = {n: [] for n in NAMES}; W.side_sigs(h1, 1, Sg, i, i + 1); W.side_sigs(h1, -1, Sg, i, i + 1)
    if not Sg["trend_pullback"]: return
    k = Sg["trend_pullback"][0][1]; e = float(h1.c.iloc[i]); risk = 3 * float(h1.atr.iloc[i]); fxr = fx(P)
    qty = round(P["balance"] * RISK_PCT / 100 / (risk * fxr), 4)
    if qty < 0.0001: return                   # wallet too small for a trade
    risk_inr = round(qty * risk * fxr, 2); notional = qty * e; P["n"] += 1; P["last_entry_ts"] = float(h1.ts.iloc[i])
    side, act = ("LONG", "BUY") if k == 1 else ("SHORT", "SELL"); tid = f"PAPER-{side}-{now.strftime('%Y%m%d')}-{P['n']:03d}"
    P["open"] = dict(id=tid, side=k, entry=e, sl=e - k * risk, tp=e + k * 4 * risk, risk=risk, qty_btc=qty, notional_usd=round(notional, 2), risk_inr=risk_inr,
                     fx=fxr, entry_ts=float(h1.ts.iloc[i]), created=now.isoformat(timespec="seconds"))
    log(P, now, tid, act, qty, e, "entry (market, paper fill)")
    send(f"📝 PAPER ORDER PLACED (virtual money)\nOrder ID: {tid}\nSymbol: BTCUSDT Perpetual\nAction: {act} ({side})\nQty: {qty} BTC\nRate: ${e:,.0f}\n"
         f"Position value: ${notional:,.0f} (₹{notional * fxr:,.0f}, ~{notional * fxr / P['balance']:.1f}x wallet)\nStop-loss: ${e - k * risk:,.0f}\nTarget (4R): ${e + k * 4 * risk:,.0f}\n"
         f"Risk: ₹{risk_inr:,.0f} ({RISK_PCT}% of ₹{P['balance']:,.0f}) | Expires in 5 days\nStrategy: trend_pullback (backtest edge weak/unproven; ~33% win rate). Not advice.")
