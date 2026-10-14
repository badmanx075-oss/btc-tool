"""Paper trading engine: virtual wallet with ledger, strategy registry, staged exits, remarks + feedback. NO real orders are ever placed.
Rules live in config.json (settings), strategies.py (entries) and lifecycle.py (exits)."""
import datetime as dt, requests
import timing as TM, confirm as CF, engine as E, backtest_v4 as W4, learn, config, wallet, lifecycle, advisor, review, strategies as ST
from config import inr

FX_DEFAULT = 88.0

def fx(P):
    try: P["fx"] = float(requests.get("https://open.er-api.com/v6/latest/USD", timeout=10).json()["rates"]["INR"])
    except Exception: pass
    return P.get("fx", FX_DEFAULT)

iso = lambda now: now.isoformat(timespec="seconds")
def jlog(P, now, kind, text): P["journal"].append(dict(ts=iso(now), kind=kind, text=text)); del P["journal"][:-500]
def ev(t, now, typ, price, note=""): t["events"].append(dict(ts=iso(now), type=typ, price=round(float(price), 1), note=note))
def order(P, now, tid, act, qty, price, note): P["orders"].append(dict(ts=iso(now), order_id=tid, action=act, qty_btc=round(float(qty), 6), price=round(float(price), 1), note=note)); del P["orders"][:-300]

def radar(h1, i):  # live checklist for trend_pullback: how close are we to a trade?
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

def positions(P): return [t for t in (P.get("pos") or {}).values() if t]

def unreal_inr(P, px):
    return sum((px - t["entry"]) * t["side"] * t["qty"] * t["remaining"] * t["fx"] for t in positions(P))

def status_text(S):
    P, lp, M = S.get("paper") or {}, S.get("last_price"), S.get("market") or {}; Wl = P.get("wallet") or {}; eq = Wl.get("cash", 0) + Wl.get("margin", 0)
    L = [f"BTC: ${lp:,.0f}" if lp else "BTC: n/a", f"Regime: {M.get('regime', '-')}", f"Wallet equity {inr(eq)} ({(eq / Wl.get('start', eq or 1) - 1) * 100:+.1f}% since start) | free {inr(Wl.get('cash', 0))} | in trades {inr(Wl.get('margin', 0))}",
         f"Trades closed: {len(P.get('closed', []))}"]
    for t in positions(P):
        if lp: L.append(f"Open {t['id']} ({t['label']}): {(lp - t['entry']) * t['side'] / t['risk']:+.2f}R | stop ${t['sl']:,.0f} | target ${t['tp']:,.0f}")
    if not positions(P): L += ["Open trades: none", radar_line(P)]
    return "\n".join(L)

def weekly_text(P, now):
    cut = iso(now - dt.timedelta(days=7)); wk = [t for t in P.get("closed", []) if t.get("closed", "") >= cut]; w = sum(t["R"] > 0 for t in wk); pnl = sum(t.get("pnl_inr", 0) for t in wk)
    Wl = P.get("wallet") or {}; eq = Wl.get("cash", 0) + Wl.get("margin", 0)
    return (f"📅 WEEKLY REVIEW (paper wallet)\nTrades closed: {len(wk)} | wins {w} | losses {len(wk) - w}\nNet: {'+' if pnl >= 0 else '-'}{inr(abs(pnl))} ({sum(t['R'] for t in wk):+.2f}R)\n"
            f"Equity: {inr(eq)} ({(eq / Wl.get('start', eq or 1) - 1) * 100:+.1f}% since start) | Max drawdown {P.get('max_dd_pct', 0)}%\n{radar_line(P)}\nSignals are statistical, not guaranteed.")

def ledger_text(P, n=8):
    L = (P.get("wallet") or {}).get("ledger", [])[-n:]
    return "🧾 Last wallet entries\n" + "\n".join(f"{e['ts'][5:16].replace('T', ' ')} {e['type']} {e['trade_id']} {e['amount']:+,.0f} → equity {inr(e['equity'])}" for e in L)

def migrate_open(P, C, o, now):   # a trade opened by the previous version keeps running under the new wallet (margin locked), nothing is lost
    sc = C["strategies"]["trend_pullback"]; lev, fee = C["wallet"]["leverage"], C["wallet"]["fee_rate_per_side"]; k, e, qty, fxr = o["side"], o["entry"], o.get("qty_btc") or o.get("qty"), o.get("fx", 88)
    notional = qty * e; margin = notional * fxr / lev; fee_usd = fee * notional
    t = dict(id=o["id"], strategy="trend_pullback", label=sc.get("label", "Trend Pullback"), side=k, entry=e, sl0=o["sl"], sl=o["sl"], risk=o["risk"], mode="fixed", tp=o["tp"], t1=None, t2=None, t3=None,
             partial=0.5, qty=qty, qty_btc=qty, notional_usd=round(notional, 2), margin_inr=round(margin, 2), margin_released=0.0, rem_wallet=1.0, leverage=lev, fx=fxr, risk_inr=o.get("risk_inr", 0.0),
             fees_usd=fee_usd, realized_usd=0.0, stage=0, remaining=1.0, mfe_R=0.0, mae_R=0.0, exits=[], events=[], created=o["created"], last_ts=float(o.get("entry_ts", 0)) + 3.6e6 - 1,
             expiry_h=sc["expiry_hours"], cfg=config.snapshot(C, "trend_pullback"), ctx=o.get("ctx"), why=o.get("why", ""), capped=False)
    ev(t, now, "MIGRATED", e, "carried over from the previous version"); wallet.lock(P, now, t["id"], margin, fee_usd * fxr); P["pos"]["trend_pullback"] = t
    jlog(P, now, "MIGRATED", f"{t['id']} carried over from the previous version (nothing lost)")

def user_event(S, act, tid, now):   # 👍 / 👎 buttons under a closed-trade message
    ok = learn.user_feedback(S.get("paper") or {}, tid, good=(act == "fbgood"))
    return (f"Rating save ho gayi ({'👍 achha' if act == 'fbgood' else '👎 galat'}): {tid}") if ok else f"{tid} band trades mein nahi mila."

def add_note(S, tid, text): return f"Note save ho gaya: {tid}" if learn.user_feedback(S.get("paper") or {}, tid, note=text) else f"{tid} band trades mein nahi mila."

def my_exit(S, tid, price, note, now):   # YOUR own manual exit, to compare with what the system did
    P = S.get("paper") or {}; t = next((x for x in P.get("closed", []) if x["id"] == tid), None) or next((x for x in (P.get("pos") or {}).values() if x and x["id"] == tid), None)
    if not t: return "Trade ID nahi mila (/trades dekho)."
    try: px = float(str(price).replace(",", "").replace("$", ""))
    except ValueError: return "Price number likho: /myexit ID 83500 optional-note"
    pct = round((px - t["entry"]) * t["side"] / t["entry"] * 100, 2); t["user_exit"] = dict(price=px, pct=pct, note=note, ts=iso(now))
    return f"Aapka exit ${px:,.0f} = {pct:+.2f}% (entry ${t['entry']:,.0f}). " + (f"System: {t['R']:+.2f}R ({t['outcome']})." if "R" in t else "System trade abhi khula hai.")

def reset_wallet(S, now):
    P = S.get("paper") or {}; S.setdefault("archive", []).append(dict(ts=iso(now), closed=P.get("closed", []), ledger=(P.get("wallet") or {}).get("ledger", [])[-50:])); S["paper"] = {}
    return "Wallet reset: purani history archive ho gayi. Naya wallet agle scan par ban jayega."

def advise(P, C, t, hr, px, now, send):   # advisory status (hold / protect / book / reversal). Never changes the trade itself.
    try:
        m = advisor.assess(t, hr, px); t["mgmt"] = m; last = t.get("mts")
        if m["status"] != t.get("mstatus") and (not last or (now - dt.datetime.fromisoformat(last)).total_seconds() > 1200):
            first = "mstatus" not in t; t["mstatus"], t["mts"] = m["status"], iso(now)
            if not first: send(advisor.message(t, m, px), cat="advice")
    except Exception as ex: print("advice error", ex)

# ---------------------------------------------------------------- exits
def apply_exit(P, C, t, kind, price, frac, now, send):
    fee = C["wallet"]["fee_rate_per_side"]; units = frac * t["qty"]; pnl = units * (price - t["entry"]) * t["side"]; fee_usd = fee * units * price
    t["rem_wallet"] = round(t["rem_wallet"] - frac, 9); margin = t["margin_inr"] - t["margin_released"] if t["rem_wallet"] <= 1e-9 else frac * t["margin_inr"]
    t["margin_released"] += margin; wallet.release(P, now, t["id"], margin, pnl * t["fx"], fee_usd * t["fx"], f"{kind} ({frac * 100:.0f}% of position)")
    t["realized_usd"] += pnl; t["fees_usd"] += fee_usd; t["exits"].append(dict(ts=iso(now), kind=kind, price=float(price), frac=round(frac, 4), pnl_inr=round(pnl * t["fx"], 2)))
    ev(t, now, kind, price, f"{frac * 100:.0f}% of position, P/L {inr(pnl * t['fx'])}"); order(P, now, t["id"], "SELL" if t["side"] == 1 else "BUY", units, price, "exit: " + kind)
    jlog(P, now, "EXIT", f"{t['id']} {kind} at ${price:,.0f} ({frac * 100:.0f}%)")
    if kind == "T1 PARTIAL" and C["alerts"].get("stage_alerts"):
        send(f"🎯 T1 HIT ({t['id']})  🕒 {config.ist(now, C)} IST\n{frac * 100:.0f}% booked at ${price:,.0f} ({'+' if pnl >= 0 else '-'}{inr(abs(pnl * t['fx']))}).\nStop moved to entry ${t['entry']:,.0f}. Remaining {t['remaining'] * 100:.0f}% runs to T2 ${t['t2']:,.0f}.")

def finalize(P, C, t, now, send):
    net = t["realized_usd"] - t["fees_usd"]; R = net / (t["qty"] * t["risk"]); kinds = [e["kind"] for e in t["exits"]]; fr = sum(e["frac"] for e in t["exits"]) or 1
    outcome = ("T2 REACHED" if "T2 TARGET" in kinds else "TARGET" if "TARGET" in kinds else "EXPIRED" if "EXPIRED" in kinds else "T1 BOOKED, STOPPED AT ENTRY" if "BREAKEVEN STOP" in kinds else "STOP-LOSS")
    t.update(closed=iso(now), outcome=outcome, exit=sum(e["price"] * e["frac"] for e in t["exits"]) / fr, R=round(float(R), 3), pnl_inr=round(float(net * t["fx"]), 2), net_usd=round(float(net), 2),
             gross_usd=round(float(t["realized_usd"]), 2), fees_usd=round(float(t["fees_usd"]), 2), mfe_R=round(t["mfe_R"], 2), mae_R=round(t["mae_R"], 2),
             hold_h=round((now - dt.datetime.fromisoformat(t["created"])).total_seconds() / 3600, 1))
    t["lesson"] = learn.postmortem(t); t["feedback"] = dict(auto=learn.feedback(t), user=None); ev(t, now, "CLOSED", t["exit"], outcome)
    P["closed"].append(t); P["pos"][t["strategy"]] = None; wallet.sync(P); P["peak"] = max(P["peak"], P["balance"])
    P["max_dd_pct"] = max(P["max_dd_pct"], round((P["peak"] - P["balance"]) / P["peak"] * 100, 2)); Wl = P["wallet"]; npro = len(P["proposals"]); learn.update(P)
    jlog(P, now, "CLOSED", f"{t['id']} {outcome} {R:+.2f}R {inr(t['pnl_inr'])}")
    if C["alerts"].get("paper_close"):
        ex = " + ".join(f"{e['kind']} {e['frac'] * 100:.0f}% @ ${e['price']:,.0f}" for e in t["exits"]); act = "SELL (close long)" if t["side"] == 1 else "BUY (cover short)"
        btn = [[{"text": "👍 Achha trade", "callback_data": f"fbgood|{t['id']}"}, {"text": "👎 Galat trade", "callback_data": f"fbbad|{t['id']}"}]] if C["alerts"].get("feedback_buttons") else None
        send(f"📝 PAPER ORDER CLOSED (virtual)  🕒 {config.ist(now, C)} IST\n{t['label']}\nOrder ID: {t['id']}\nAction: {act}\nQty: {t['qty']} BTC | opened {config.ist(dt.datetime.fromisoformat(t['created']), C)}\n"
             f"Entry ${t['entry']:,.0f} → avg exit ${t['exit']:,.0f}  [{outcome}]\nExits: {ex}\nGross ${t['gross_usd']:+,.2f} | Fees ${t['fees_usd']:,.2f} | Net {'+' if t['pnl_inr'] >= 0 else '-'}{inr(abs(t['pnl_inr']))} ({R:+.2f}R)\n"
             f"💰 Equity {inr(Wl['cash'] + Wl['margin'])} ({(P['balance'] / Wl['start'] - 1) * 100:+.1f}% since start) | free {inr(Wl['cash'])} | max drawdown {P['max_dd_pct']}%\n"
             f"💬 Kya hua: {t['lesson']}\n📝 Feedback: {t['feedback']['auto']['verdict']}\nRate it with the buttons, or send: /note {t['id']} your remark" + ("\n💡 New filter idea. Send /lessons." if len(P["proposals"]) > npro else ""), buttons=btn)

def manage(P, C, t, h15, px, now, send):
    for c in h15[h15.ts > t["last_ts"]].itertuples():
        for kind, price, frac in lifecycle.advance(t, c): apply_exit(P, C, t, kind, price, frac, now, send)
        if t["remaining"] <= 1e-9: break
    if t["remaining"] > 1e-9 and (now - dt.datetime.fromisoformat(t["created"])).total_seconds() / 3600 >= t["expiry_h"]:
        frac = t["remaining"]; t["remaining"] = 0; apply_exit(P, C, t, "EXPIRED", px, frac, now, send)
    if len(h15) > 1: t["last_ts"] = max(t["last_ts"], float(h15.ts.iloc[-2]))
    if t["remaining"] <= 1e-9: finalize(P, C, t, now, send)

# ---------------------------------------------------------------- entries
def open_position(P, C, name, sg, now, h15, fxr, send):
    sc = C["strategies"][name]; Wl = P["wallet"]; k, e = sg["side"], sg["entry"]; fee, lev = C["wallet"]["fee_rate_per_side"], C["wallet"]["leverage"]
    qty = (Wl["cash"] + Wl["margin"]) * sc["risk_pct"] / 100 / (sg["risk"] * fxr); cap = Wl["cash"] * 0.99 / (e * fxr * (1 / lev + fee)); capped = qty > cap; qty = min(qty, cap)
    step = C["wallet"].get("qty_step", 0.0001); qty = round(int(qty / step) * step, 6)
    if qty < step: jlog(P, now, "SKIPPED", f"{name} {'LONG' if k == 1 else 'SHORT'} signal skipped: not enough free balance"); return False
    P["n"][name] = P["n"].get(name, 0) + 1; side = "LONG" if k == 1 else "SHORT"; tid = f"{ {'trend_pullback': 'TP', 'session_breakout': 'SB'}.get(name, 'ES') }-{side}-{now.strftime('%Y%m%d')}-{P['n'][name]:03d}"
    notional = qty * e; margin = notional * fxr / lev; fee_usd = fee * notional
    t = dict(id=tid, strategy=name, label=sc.get("label", name), side=k, entry=e, sl0=sg["sl"], sl=sg["sl"], risk=sg["risk"], mode=sg["mode"], tp=sg.get("tp"), t1=sg.get("t1"), t2=sg.get("t2"), t3=sg.get("t3"),
             partial=sc.get("partial_pct", 50) / 100, qty=qty, qty_btc=qty, notional_usd=round(notional, 2), margin_inr=round(margin, 2), margin_released=0.0, rem_wallet=1.0, leverage=lev, fx=fxr,
             risk_inr=round(qty * sg["risk"] * fxr, 2), fees_usd=fee_usd, realized_usd=0.0, stage=0, remaining=1.0, mfe_R=0.0, mae_R=0.0, exits=[], events=[], created=iso(now),
             last_ts=float(h15.ts.iloc[-1]), expiry_h=sc["expiry_hours"], cfg=config.snapshot(C, name), ctx=sg["ctx"], entry_ctx=sg.get("entry_ctx"), confirm_lvl=sg.get("confirm"), grade=review.grade(name, sg["ctx"]), why=sg["why"], capped=bool(capped))
    ev(t, now, "OPENED", e, f"qty {qty} BTC, margin {inr(margin)}"); wallet.lock(P, now, tid, margin, fee_usd * fxr); P["pos"][name] = t; P["last_entry"][name] = now.timestamp() * 1000
    order(P, now, tid, "BUY" if k == 1 else "SELL", qty, e, "entry (market, paper fill)"); jlog(P, now, "OPENED", f"{tid} {side} {qty} BTC at ${e:,.0f} (margin {inr(margin)})"); Wl = P["wallet"]
    plan = (f"Stop-loss ${t['sl']:,.0f} | Target ${t['tp']:,.0f} ({sc.get('target_r')}R)" if sg["mode"] == "fixed" else
            f"Stop-loss ${t['sl']:,.0f} | T1 ${t['t1']:,.0f} ({sc['partial_pct']}% booked, stop to entry) | T2 ${t['t2']:,.0f} (rest)")
    if C["alerts"].get("paper_open"):
        send(f"📝 PAPER ORDER PLACED (virtual)  🕒 {config.ist(now, C)} IST\n{t['label']} | Grade {t['grade']}\nOrder ID: {tid}\nAction: {'BUY' if k == 1 else 'SELL'} ({side}) BTCUSDT Perpetual\nQty: {qty} BTC @ ${e:,.0f}\n"
             f"Position value ${notional:,.0f} ({inr(notional * fxr)}) | margin locked {inr(margin)} ({lev}x) | entry fee {inr(fee_usd * fxr)}\n{plan}\n"
             f"Risk {inr(t['risk_inr'])} ({sc['risk_pct']}% of equity)" + (" | size capped by free balance" if capped else "") + f"\n💬 Kyun liya: {t['why']}\n"
             f"💰 Wallet: free {inr(Wl['cash'])} | in trades {inr(Wl['margin'])} | equity {inr(Wl['cash'] + Wl['margin'])}")
    return True

def shadow_step(sh, h15, now, fee):  # a signal skipped by a learned filter is still simulated, to verify the filter helps
    for c in h15[h15.ts > sh["last_ts"]].itertuples():
        for kind, price, frac in lifecycle.advance(sh, c): sh["exits"].append((kind, price, frac))
        if sh["remaining"] <= 1e-9: break
    if sh["remaining"] > 1e-9 and (now - dt.datetime.fromisoformat(sh["created"])).total_seconds() / 3600 >= sh["expiry_h"]:
        sh["exits"].append(("EXPIRED", float(h15.c.iloc[-1]), sh["remaining"])); sh["remaining"] = 0
    if len(h15) > 1: sh["last_ts"] = max(sh["last_ts"], float(h15.ts.iloc[-2]))
    if sh["remaining"] <= 1e-9: sh["R"] = round(float(lifecycle.trade_R(sh["exits"], sh["entry"], sh["side"], sh["risk"], fee)), 3)

def daily_loss_hit(P, C, now, send):
    """Stops NEW entries for the rest of the (IST) day once realised loss today reaches risk.max_daily_loss_pct of starting capital."""
    lim = C.get("risk", {}).get("max_daily_loss_pct", 0)
    if not lim: return False
    day = lambda d: (d + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d"); today = day(now); start = (P.get("wallet") or {}).get("start") or 20000
    pnl = sum(t.get("pnl_inr", 0) for t in P.get("closed", []) if t.get("closed") and day(dt.datetime.fromisoformat(t["closed"])) == today)
    if pnl <= -lim / 100 * start:
        if P.get("loss_guard_day") != today:
            P["loss_guard_day"] = today; send(f"🛑 DAILY LOSS LIMIT\nAaj ka realised loss {inr(pnl)} (limit {lim}% = {inr(lim / 100 * start)}). Aaj naye trades nahi khulenge. Khule trades chalte rahenge. Kal subah (IST) se normal.", cat="paper_close")
        return True
    return False

def run(S, send, now, scan=None):
    C = config.load(); P = S.setdefault("paper", {})
    for key, v in dict(closed=[], pos={}, n={}, last_entry={}, filters=[], proposals=[], shadow=[], lessons={}, journal=[], orders=[], peak=0.0, max_dd_pct=0.0).items(): P.setdefault(key, v)
    if not isinstance(P["n"], dict): P["n"] = {"trend_pullback": P["n"]}
    old_open, old_last = P.get("open"), P.pop("last_entry_ts", None)           # data from the previous version: kept, never discarded
    wallet.init(P, C, now); P["peak"] = max(P["peak"], P["balance"]); P.pop("open", None)
    if old_last and "trend_pullback" not in P["last_entry"]: P["last_entry"]["trend_pullback"] = float(old_last) + 3.6e6
    if old_open and not P["pos"].get("trend_pullback"): migrate_open(P, C, old_open, now)
    h15, hr = E.candles("15m", 300), E.candles("1H", 300); px = float(h15.c.iloc[-1]); fee = C["wallet"]["fee_rate_per_side"]
    h1 = W4.prep(hr); i = len(h1) - 2; P["radar"] = dict(ts=iso(now), price=px, **radar(h1, i))
    d = P.get("demo")
    if d:                                                       # demo trade: tests the pipeline, never touches the wallet
        k = d["side"]; age = (now - dt.datetime.fromisoformat(d["created"])).total_seconds() / 3600; hit = None
        if (px <= d["sl"]) if k == 1 else (px >= d["sl"]): hit = ("STOP-LOSS", d["sl"])
        elif (px >= d["tp"]) if k == 1 else (px <= d["tp"]): hit = ("TARGET", d["tp"])
        elif age >= 1: hit = ("TIME UP (1h)", px)
        if hit:
            usd = (hit[1] - d["entry"]) * k * d["qty"]; P["demo"] = None; jlog(P, now, "DEMO", f"{d['id']} closed {hit[0]}")
            send(f"🧪 DEMO ORDER CLOSED (test only, wallet NOT changed)  🕒 {config.ist(now, C)} IST\n{d['id']}\n{hit[0]} at ${hit[1]:,.0f}\nWould-be P/L: {'+' if usd >= 0 else '-'}{inr(abs(usd * d['fx']))}\nPipeline works: scan -> order -> monitor -> close -> Telegram.")
    elif P.pop("force_demo", False):
        fxr = fx(P); e = px; risk = 0.003 * px; qty = round(P["wallet"]["cash"] * 0.002 / (risk * fxr), 4) or 0.0001
        P["demo"] = dict(id=f"DEMO-{now.strftime('%H%M')}", side=1, entry=e, sl=e - risk, tp=e + risk, risk=risk, qty=qty, fx=fxr, created=iso(now), why="Ye sirf test (demo) trade hai: scan, order, monitor, close aur Telegram chal rahe hain ya nahi, ye jaanchne ke liye.")
        send(f"🧪 DEMO ORDER PLACED (test only, wallet NOT affected)  🕒 {config.ist(now, C)} IST\nOrder ID: {P['demo']['id']}\nBUY (LONG) {qty} BTC @ ${e:,.0f}\nStop ${e - risk:,.0f} | Target ${e + risk:,.0f}\nCloses at stop/target or within 1 hour.")
    for sh in P["shadow"]:
        if "R" not in sh and "mode" in sh: shadow_step(sh, h15, now, fee)
    del P["shadow"][:-100]
    for m in learn.check_filters(P): send(m)
    for name, t in list(P["pos"].items()):
        if t: manage(P, C, t, h15, px, now, send)
    for name, t in list(P["pos"].items()):
        if t and C["alerts"].get("advice"): advise(P, C, t, hr, px, now, send)
        if t:
            try: CF.step(S, P, C, t, px, now, send, ev, config.ist)
            except Exception as ex: print("confirm error", ex)
    try: review.near_miss_step(S, P, scan, C["strategies"].get("early_signal", {}), h15, now, fee)
    except Exception as e: print("near-miss error", e)
    tcls = TM.cls_of(TM.load(), now.hour); loss_hit = daily_loss_hit(P, C, now, send)
    for name, sc in C["strategies"].items():
        if loss_hit or (tcls == "LOW" and C["timing"].get("skip_low_activity")): break
        if S.get("paused") or not sc.get("enabled") or P["pos"].get(name) or name not in ST.SIGNALS: continue
        if now.timestamp() * 1000 - P["last_entry"].get(name, 0) < sc.get("cooldown_hours", 1) * 3.6e6: continue
        if len(positions(P)) >= C["wallet"]["max_open_positions"]: continue
        sg = ST.SIGNALS[name](dict(h1=h1, i=i, S=S, scan=scan, now=now, tcls=tcls), sc)
        if not sg: continue
        P["last_entry"][name] = now.timestamp() * 1000; blk = learn.blocked_by(P, sg["ctx"], name)
        if blk:
            sh = lifecycle.new_state(sg["side"], sg["entry"], sg["sl"], sg["mode"], sg.get("tp"), sg.get("t1"), sg.get("t2"), sc.get("partial_pct", 50) / 100)
            sh.update(id=f"SHADOW-{name[:2].upper()}-{now.strftime('%Y%m%d%H%M')}", strategy=name, filter=blk["text"], ctx=sg["ctx"], exits=[], last_ts=float(h15.ts.iloc[-1]), created=iso(now), expiry_h=sc["expiry_hours"])
            P["shadow"].append(sh); jlog(P, now, "FILTERED", f"{name} signal skipped by filter #{blk['id']}")
            send(f"🧠 Signal skipped by learned filter #{blk['id']}: {blk['text']}\nIt is tracked as a shadow trade to check whether the filter really helps."); continue
        try: sg["entry_ctx"] = review.entry_ctx(S, now)
        except Exception as e: print("ctx error", e)
        jlog(P, now, "SIGNAL", f"{name} {'LONG' if sg['side'] == 1 else 'SHORT'} signal at ${sg['entry']:,.0f}")
        if not open_position(P, C, name, sg, now, h15, fx(P), send): P["last_entry"][name] = now.timestamp() * 1000 - max(sc.get("cooldown_hours", 1) - 1, 0) * 3.6e6
