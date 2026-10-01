"""Paper trading with a virtual INR wallet and real-trade-style orders (qty, rate, fees, P&L).
Strategy = trend_pullback (the one that weakly survived V4/V5): stop 3xATR(1H), target 4R, expiry 120 x 1H bars. NO real orders are placed."""
import datetime as dt, requests
import engine as E, backtest_v4 as W, learn

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

def radar(h1, i):  # live checklist: how close are we to a trade?
    out = {}
    for k, name in ((1, "LONG"), (-1, "SHORT")):
        c, o = k * h1.c.values, k * h1.o.values; hi, lo = (h1.h.values, h1.l.values) if k == 1 else (-h1.l.values, -h1.h.values)
        a = float(h1.atr.iloc[i]); hh, ll = float(hi[i - 23:i + 1].max()), float(lo[i - 23:i + 1].min())
        d4, e4 = float(h1.dir4.iloc[i]) * k, float(h1.er4.iloc[i]); dep = (hh - float(c[i])) / a; intact = bool(c[i] > ll + 0.5 * a); bounce = bool(c[i] > o[i])
        out[name] = [[f"4H trend {'up' if k == 1 else 'down'}", bool(d4 > 0 and e4 > 0.3), f"strength {e4:.2f}, needs above 0.30"],
                     ["Pullback from recent extreme", bool(dep >= 1.5), f"{dep:.1f} ATR, needs 1.5 or more"],
                     ["Pullback not broken", intact, "price holds above recent swing" if intact else "price broke the recent swing"],
                     ["Bounce candle", bounce, "last 1H candle closed with the trend" if bounce else "last 1H candle closed against the trend"]]
    return out

def radar_line(P):
    r = P.get("radar")
    return "Setup radar: " + " | ".join(f"{'BUY' if s == 'LONG' else 'SELL'} {sum(c[1] for c in r[s])}/4" for s in ("LONG", "SHORT")) if r else "Setup radar: not computed yet"

def status_text(S):
    P, lp, M = S.get("paper") or {}, S.get("last_price"), S.get("market") or {}; bal, st0 = P.get("balance", START), P.get("start", START)
    L = [f"BTC: ${lp:,.0f}" if lp else "BTC: n/a", f"Regime: {M.get('regime', '-')}", f"Paper wallet: ₹{bal:,.0f} ({(bal / st0 - 1) * 100:+.1f}%) | trades closed {len(P.get('closed', []))}"]
    o = P.get("open")
    if o and lp: L.append(f"Open: {o['id']} {(lp - o['entry']) * o['side'] / o['risk']:+.2f}R | stop ${o['sl']:,.0f} | target ${o['tp']:,.0f}")
    else: L += ["Open trade: none", radar_line(P)]
    return "\n".join(L)

def feat(h1, i, k):
    c = k * h1.c.values; hi = h1.h.values if k == 1 else -h1.l.values; a = float(h1.atr.iloc[i]); ts = dt.datetime.fromtimestamp(float(h1.ts.iloc[i]) / 1000, dt.timezone.utc)
    return dict(er4=round(float(h1.er4.iloc[i]), 3), atr_pct=round(a / float(h1.c.iloc[i]) * 100, 3), depth=round((float(hi[i - 23:i + 1].max()) - float(c[i])) / a, 2), hour=ts.hour, wd=ts.weekday())

def resolve(h, t, px):  # walks candles after entry: returns ((outcome, price), MFE_R, MAE_R, hours) or None
    k, mfe, mae, res, hold = t["side"], 0.0, 0.0, None, 0.0
    for c in h[h.ts > t["entry_ts"]].itertuples():
        mfe = max(mfe, ((c.h if k == 1 else c.l) - t["entry"]) * k / t["risk"]); mae = max(mae, (t["entry"] - (c.l if k == 1 else c.h)) * k / t["risk"]); hold = (c.ts - t["entry_ts"]) / BAR
        if (c.l <= t["sl"]) if k == 1 else (c.h >= t["sl"]): res = ("STOP-LOSS", t["sl"]); break   # same-bar = stop first
        if (c.h >= t["tp"]) if k == 1 else (c.l <= t["tp"]): res = ("TARGET", t["tp"]); break
    if not res and (h.ts.iloc[-1] - t["entry_ts"]) / BAR >= 120: res = ("EXPIRED (5 days)", px); hold = (h.ts.iloc[-1] - t["entry_ts"]) / BAR
    return (res, round(mfe, 2), round(mae, 2), round(hold, 1)) if res else None

def net_R(t, xp): return (xp - t["entry"]) * t["side"] / t["risk"] - COST * t["entry"] / t["risk"]

def run(S, send, now):
    P = S.setdefault("paper", {})
    for key, v in dict(balance=START, start=START, peak=START, max_dd_pct=0.0, orders=[], open=None, closed=[], n=0, last_entry_ts=0, filters=[], proposals=[], shadow=[], lessons={}).items(): P.setdefault(key, v)
    h = E.candles("1H", 300); px = float(h.c.iloc[-1]); t = P["open"]
    if t and t.get("demo"):               # demo trade: tests the pipeline, never touches the wallet
        k = t["side"]; age = (now - dt.datetime.fromisoformat(t["created"])).total_seconds() / 3600; hit = None
        if (px <= t["sl"]) if k == 1 else (px >= t["sl"]): hit = ("STOP-LOSS", t["sl"])
        elif (px >= t["tp"]) if k == 1 else (px <= t["tp"]): hit = ("TARGET", t["tp"])
        elif age >= 1: hit = ("TIME UP (1h)", px)
        if hit:
            usd = (hit[1] - t["entry"]) * k * t["qty_btc"]; P["open"] = None
            send(f"🧪 DEMO ORDER CLOSED (test only, wallet NOT changed)\n{t['id']}\n{hit[0]} at ${hit[1]:,.0f}\nWould-be P/L: {'+' if usd >= 0 else '-'}₹{abs(usd * t['fx']):,.0f}\nPipeline works: scan -> order -> monitor -> close -> Telegram.")
        return
    for sh in P["shadow"]:                # trades the learned filters skipped: tracked to verify the filters really help
        if "R" not in sh:
            r = resolve(h, sh, px)
            if r: sh.update(outcome=r[0][0], exit=float(r[0][1]), R=round(float(net_R(sh, r[0][1])), 3), mfe_R=r[1], mae_R=r[2])
    del P["shadow"][:-100]
    for m in learn.check_filters(P): send(m)
    if t and P.pop("force_demo", False): send("Demo skipped: a real paper trade is already open.")
    if t:
        r = resolve(h, t, px)
        if r:
            (name, xp), mfe, mae, hold = r; k = t["side"]
            q, fxr, gpts = t.get("qty_btc"), t.get("fx", P.get("fx", FX_DEFAULT)), (xp - t["entry"]) * k
            if q: gross = q * gpts; fees = COST * t["entry"] * q; net = gross - fees; pnl = net * fxr; R = net / (q * t["risk"])
            else: R = net_R(t, xp); pnl = R * t.get("risk_inr", 0.0); gross = fees = net = 0.0
            t.update(outcome=name, exit=float(xp), R=round(float(R), 3), pnl_inr=round(float(pnl), 2), gross_usd=round(float(gross), 2), fees_usd=round(float(fees), 2),
                     net_usd=round(float(net), 2), mfe_R=mfe, mae_R=mae, hold_h=hold, closed=now.isoformat(timespec="seconds")); t["lesson"] = learn.postmortem(t)
            P["balance"] = round(P["balance"] + pnl, 2); P["peak"] = max(P["peak"], P["balance"])
            P["max_dd_pct"] = max(P["max_dd_pct"], round((P["peak"] - P["balance"]) / P["peak"] * 100, 2))
            P["closed"].append(t); P["open"] = None; ret = (P["balance"] / P["start"] - 1) * 100; act = "SELL" if k == 1 else "BUY"; npro = len(P["proposals"]); learn.update(P)
            log(P, now, t["id"], act, q, xp, "exit: " + name)
            send(f"📝 PAPER ORDER CLOSED (virtual)\nOrder ID: {t['id']}\nAction: {act} ({'close long' if k == 1 else 'cover short'})\nQty: {q} BTC\n"
                 f"Entry: ${t['entry']:,.0f} -> Exit: ${xp:,.0f}  [{name}]\nGross ${gross:+,.2f} | Fees ${fees:,.2f} | Net {'+' if pnl >= 0 else '-'}₹{abs(pnl):,.0f} ({R:+.2f}R)\n"
                 f"💰 Wallet: ₹{P['balance']:,.0f} ({ret:+.1f}% since start) | Max drawdown {P['max_dd_pct']}%\nTrades closed: {len(P['closed'])}\n"
                 f"🧠 Lesson: {t['lesson']}" + ("\n💡 New filter idea proposed. Send /lessons." if len(P["proposals"]) > npro else ""))
        return
    h1 = W.prep(h); i = len(h1) - 2          # last fully closed 1H bar
    P["radar"] = dict(ts=now.isoformat(timespec="seconds"), price=px, **radar(h1, i)); demo = bool(P.pop("force_demo", False))
    if demo: k, e, risk = 1, px, 0.003 * px
    else:
        if h1.ts.iloc[i] - P["last_entry_ts"] < 24 * BAR: return
        Sg = {n: [] for n in NAMES}; W.side_sigs(h1, 1, Sg, i, i + 1); W.side_sigs(h1, -1, Sg, i, i + 1)
        if not Sg["trend_pullback"]: return
        k = Sg["trend_pullback"][0][1]; e = float(h1.c.iloc[i]); risk = 3 * float(h1.atr.iloc[i]); M_ = S.get("market") or {}
        ctx = dict(feat(h1, i, k), side_n=k, side="LONG" if k == 1 else "SHORT", funding=float(M_.get("funding", 0)), regime=M_.get("regime")); blk = learn.blocked_by(P, ctx)
        if blk:
            P["last_entry_ts"] = float(h1.ts.iloc[i])
            P["shadow"].append(dict(id=f"SHADOW-{now.strftime('%Y%m%d%H%M')}", side=k, entry=e, sl=e - k * risk, tp=e + k * 4 * risk, risk=risk, entry_ts=float(h1.ts.iloc[i]), filter=blk["text"], ctx=ctx))
            send(f"🧠 Signal skipped by learned filter #{blk['id']}: {blk['text']}\nIt is tracked as a shadow trade to check whether the filter really helps."); return
    fxr = fx(P); qty = round(P["balance"] * RISK_PCT / 100 / (risk * fxr), 4)
    if qty < 0.0001: return                   # wallet too small for a trade
    risk_inr = round(qty * risk * fxr, 2); notional = qty * e; side, act = ("LONG", "BUY") if k == 1 else ("SHORT", "SELL"); mult = 1 if demo else 4
    if demo: tid = f"DEMO-{side}-{now.strftime('%H%M')}"
    else: P["n"] += 1; P["last_entry_ts"] = float(h1.ts.iloc[i]); tid = f"PAPER-{side}-{now.strftime('%Y%m%d')}-{P['n']:03d}"
    P["open"] = dict(id=tid, side=k, entry=e, sl=e - k * risk, tp=e + k * mult * risk, risk=risk, qty_btc=qty, notional_usd=round(notional, 2), risk_inr=risk_inr,
                     fx=fxr, entry_ts=float(h1.ts.iloc[i]), created=now.isoformat(timespec="seconds"), **({"demo": True} if demo else {"ctx": ctx}))
    if not demo: log(P, now, tid, act, qty, e, "entry (market, paper fill)")
    body = (f"Order ID: {tid}\nSymbol: BTCUSDT Perpetual\nAction: {act} ({side})\nQty: {qty} BTC\nRate: ${e:,.0f}\n"
            f"Position value: ${notional:,.0f} (₹{notional * fxr:,.0f}, ~{notional * fxr / P['balance']:.1f}x wallet)\nStop-loss: ${e - k * risk:,.0f}\nTarget ({mult}R): ${e + k * mult * risk:,.0f}\n")
    send(("🧪 DEMO ORDER PLACED (test only, wallet NOT affected)\n" + body + "Closes at stop/target or within 1 hour.") if demo else
         ("📝 PAPER ORDER PLACED (virtual money)\n" + body + f"Risk: ₹{risk_inr:,.0f} ({RISK_PCT}% of ₹{P['balance']:,.0f}) | Expires in 5 days\nStrategy: trend_pullback (backtest edge weak/unproven; ~33% win rate). Not advice."))
