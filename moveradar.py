"""MOVE RADAR: warns BEFORE a good move (squeeze / compression + volume build-up + price at the edge of its box + active time window
+ methods leaning one way + order flow), then tracks the move and says when it is COMPLETE (expected points reached or exhaustion).
It is a PROBABILITY tool, not a prediction: backtest_v10 measures how often a high radar score really was followed by a big move.
Price part (score_price) uses only past candles, so live and backtest are identical."""
import numpy as np
import methods as MT

FIRE, BUILD = 65, 45
WATCH_H = 8


def score_price(I, i, cls_now=None, cls_next=None):
    a = I["atr"][i]
    if i < 250 or not a == a: return None
    h, l, c, v = I["h"], I["l"], I["c"], I["v"]; bw = I["bw_pct"][i]; comp = 0
    if bw == bw: comp = 30 if bw <= 0.10 else 22 if bw <= 0.20 else 12 if bw <= 0.30 else 0
    if a / max(float(np.mean(I["atr"][i - 100:i])), 1e-9) < 0.7: comp = max(comp, 22)
    bh, bl = float(h[i - 7:i + 1].max()), float(l[i - 7:i + 1].min()); w = (bh - bl) / a; box = 15 if w <= 3 else 8 if w <= 4 else 0
    v3 = float(v[i - 2:i + 1].mean()) / max(float(I["vavg"][i]), 1e-9); vol = 10 if (v3 >= 1.1 and comp >= 12) else 0
    best = max([x for x in (cls_now, cls_next) if x], key=lambda k: {"HIGH": 2, "MEDIUM": 1, "LOW": 0}[k], default=None); tm = {"HIGH": 15, "MEDIUM": 7}.get(best, 0)
    d = min(bh - c[i], c[i] - bl) / a; loc = 15 if d <= 0.6 else 8 if d <= 1.2 else 0
    cons = MT.consensus(MT.votes(I, i)); nl, ns = cons["long"], cons["short"]; lean = 1 if nl > ns and nl >= 2 else -1 if ns > nl and ns >= 2 else 0; mp = 15 if max(nl, ns) >= 3 else 7 if max(nl, ns) == 2 else 0
    parts = dict(compression=comp, tight_box=box, volume_buildup=vol, time_window=tm, near_box_edge=loc, methods_lean=mp)
    return dict(score=int(sum(parts.values())), parts=parts, lean=lean, box_hi=bh, box_lo=bl, atr=float(a), nl=nl, ns=ns)


def exhaustion(I, i, dirn):
    """0-100: is a move in direction dirn (+1 up, -1 down) running out of steam?"""
    r = I["rsi"][i]; pts, why = 0, []
    if (r > 75 and dirn == 1) or (r < 25 and dirn == -1): pts += 30; why.append(f"RSI {r:.0f} extreme")
    vr = float(I["v"][i - 2:i + 1].mean()) / max(float(I["vavg"][i]), 1e-9)
    if vr < 0.7: pts += 25; why.append("volume sookh raha hai")
    rng = max(I["h"][i] - I["l"][i], 1e-9); wick = (I["h"][i] - max(I["c"][i], I["o"][i])) / rng if dirn == 1 else (min(I["c"][i], I["o"][i]) - I["l"][i]) / rng
    if wick >= 0.5: pts += 25; why.append("aakhri candle mein rejection wick")
    hs = I["hist"]
    if (dirn == 1 and hs[i] < hs[i - 1] < hs[i - 2]) or (dirn == -1 and hs[i] > hs[i - 1] > hs[i - 2]): pts += 20; why.append("momentum ghat raha hai")
    return pts, why


def live(S, I, i, now, cls_now, cls_next):
    base = score_price(I, i, cls_now, cls_next)
    if not base: return None
    sc, notes = base["score"], []
    of = ((S.get("orderflow") or {}).get("now")) or {}; st = of.get("state", ""); lean = base["lean"]
    if st.startswith("AGGRESSIVE") or abs(of.get("ratio", 0)) >= 0.25:
        sd = 1 if of.get("ratio", 0) > 0 else -1
        if lean == 0 or sd == lean: sc += 10; lean = lean or sd; notes.append(f"order flow {st.lower()} (delta {of.get('ratio', 0) * 100:+.0f}%)")
        else: sc -= 10; notes.append("order flow lean ke khilaaf")
    dv = ((S.get("desk") or {}).get("derivs")) or {}
    if (dv.get("oi_change_4h") or 0) > 1.0 and abs(dv.get("price_change_4h") or 0) < 0.8: sc += 5; notes.append("OI badh raha hai, bhaav sust: positions ban rahi hain")
    sc = max(0, min(100, sc)); ex = ((S.get("analysis") or {}).get("expected_move") or {}).get("expected"); a = base["atr"]
    exp_pts = float(ex[0]) if ex else 3 * a
    state = "GOOD MOVE LIKELY" if sc >= FIRE else "BUILDING" if sc >= BUILD else "QUIET"
    return dict(ts=now.isoformat(timespec="seconds"), score=sc, state=state, lean=lean, parts=base["parts"], notes=notes, box_hi=round(base["box_hi"], 1), box_lo=round(base["box_lo"], 1), atr=round(a, 1), exp_pts=round(exp_pts), tm=dict(now=cls_now, next=cls_next))


def _due(S, key, hours, now):
    import datetime as dt
    d = S.setdefault("alert_sent", {}); last = d.get(key)
    if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < hours * 3600: return False
    d[key] = now.isoformat(timespec="seconds"); return True


def watch(S, rm, px, I, i, now, send):
    """State machine: radar fires -> 'good move coming' -> move starts (trigger broken) -> move complete / failed / expired."""
    import datetime as dt
    if not rm: return
    w = S.get("move_watch"); log = S.setdefault("move_log", []); a = rm["atr"]; side = lambda k: "UPAR" if k == 1 else "NEECHE"
    if w and (now - dt.datetime.fromisoformat(w["ts"])).total_seconds() > WATCH_H * 3600:
        if w.get("triggered") is None: log.append(dict(w, result="NO MOVE (expired)", end=now.isoformat(timespec="seconds")))
        S["move_watch"] = w = None
    if not w:
        if rm["state"] == "GOOD MOVE LIKELY" and not S.get("paused") and _due(S, "move-fire", 3, now):
            w = S["move_watch"] = dict(ts=now.isoformat(timespec="seconds"), px=px, score=rm["score"], lean=rm["lean"], hi=rm["box_hi"], lo=rm["box_lo"], exp=rm["exp_pts"], triggered=None)
            ld = {1: "UPAR (LONG)", -1: "NEECHE (SHORT)", 0: "abhi saaf nahi (kisi bhi taraf)"}[rm["lean"]]
            send(f"🚀 GOOD MOVE COMING? (radar {rm['score']}/100)\nBTC ${px:,.0f} | jhukaav: {ld}\nKyun: " + ", ".join(k.replace('_', ' ') for k, v in rm["parts"].items() if v >= 10) + (" | " + "; ".join(rm["notes"]) if rm["notes"] else "")
                 + f"\nTrigger: ${rm['box_hi']:,.0f} ke upar band = move UPAR shuru | ${rm['box_lo']:,.0f} ke neeche band = move NEECHE shuru\nTypical size: ~{rm['exp_pts']:,.0f} pts. Move poora hone par bataunga.\n"
                 "⚠️ Ye sambhavna hai, guarantee nahi: kabhi move nahi bhi aata (fake-out). Trigger ka intezaar karo.", cat="move")
        return
    if w["triggered"] is None:
        k = 1 if px > w["hi"] + 0.1 * a else -1 if px < w["lo"] - 0.1 * a else 0
        if k:
            w.update(triggered=k, start=w["hi"] if k == 1 else w["lo"], trig_ts=now.isoformat(timespec="seconds"), peak=0.0)
            send(f"🚀 MOVE SHURU: {side(k)}\nBTC ${px:,.0f} ne ${w['start']:,.0f} tod diya. Expected ~{w['exp']:,.0f} pts. " + ("Radar ka jhukaav bhi yahi tha ✅" if k == w["lean"] else "Radar ka jhukaav alag tha ⚠️ (fake-out ka risk)") + "\nMove poora hone par alert aayega, taaki trade lamba na chale.", cat="move")
        return
    k = w["triggered"]; tr = (px - w["start"]) * k; w["peak"] = max(w.get("peak", 0.0), tr); ex, why = exhaustion(I, i, k)
    if tr >= 0.8 * w["exp"] or (ex >= 70 and tr >= 0.3 * w["exp"]):
        send(f"✅ MOVE COMPLETE ({side(k)}): ~{tr:,.0f} pts (expected ~{w['exp']:,.0f})\nBTC ${px:,.0f}. " + (("Thakaan ke sanket: " + ", ".join(why) + ". ") if why else "") + "Ab naya entry mat chhedo; khule trade mein profit book karne ka samay.", cat="move")
        log.append(dict(w, result="COMPLETE", traveled=round(tr), end=now.isoformat(timespec="seconds"))); S["move_watch"] = None
    elif tr < -1.0 * a and w["peak"] < 0.3 * w["exp"]:
        send(f"❌ MOVE FAIL (fake-out): bhaav trigger ${w['start']:,.0f} ke wapas {abs(tr):,.0f} pts ulta gaya. Is setup ko chhod do.", cat="move")
        log.append(dict(w, result="FAILED", traveled=round(tr), end=now.isoformat(timespec="seconds"))); S["move_watch"] = None
    del log[:-60]


def text(rm, w=None):
    if not rm: return "Move radar abhi ready nahi."
    ic = {"GOOD MOVE LIKELY": "🚀", "BUILDING": "🟡", "QUIET": "⚪"}[rm["state"]]; ld = {1: "UPAR", -1: "NEECHE", 0: "saaf nahi"}[rm["lean"]]
    L = [f"{ic} MOVE RADAR: {rm['score']}/100 ({rm['state']}) | jhukaav {ld}", "Parts: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in rm["parts"].items()) + (" | " + "; ".join(rm["notes"]) if rm["notes"] else ""),
         f"Box: ${rm['box_lo']:,.0f} - ${rm['box_hi']:,.0f} | typical move ~{rm['exp_pts']:,.0f} pts"]
    if w: L.append(f"Watch: {'move shuru ' + ('UPAR' if w['triggered'] == 1 else 'NEECHE') if w.get('triggered') else 'trigger ka intezaar'} (radar {w['score']} par fire hua)")
    L.append("Radar sambhavna batata hai, guarantee nahi. Backtest result dashboard ke Backtests tab mein (V10).")
    return "\n".join(L)
