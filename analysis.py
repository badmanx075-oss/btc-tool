"""Full market analysis snapshot (spec 2-8, 12-16, 25-31): component scores, stage, entry/stop/target zones, expected-move odds from history,
false-signal checklist, range + breakout logic. Scores are transparent heuristics (weights NOT calibrated); backtests show no proven edge."""
import numpy as np
import engine as E, backtest_v4 as W

def _py(x):
    if isinstance(x, dict): return {k: _py(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [_py(v) for v in x]
    if isinstance(x, (np.floating,)): return float(x)
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.bool_,)): return bool(x)
    return x

def pivots(hi, lo, w=3):
    return ([i for i in range(w, len(hi) - w) if hi[i] == hi[i - w:i + w + 1].max()], [i for i in range(w, len(lo) - w) if lo[i] == lo[i - w:i + w + 1].min()])

def odds(stats, atr_pct):
    if not stats: return None
    b = int(atr_pct > stats["edges"][0]) + int(atr_pct > stats["edges"][1]); return b, stats["H"]["24"][str(b)], stats["Q"]["24"][str(b)], stats["n_bucket"][str(b)]

def snapshot(h1r, fr, oi, log, stats, regime, scores, has_trade=False):
    h1 = W.prep(h1r); d = h1.iloc[:-1].reset_index(drop=True); c, o, hi, lo, v = (d[x].values for x in ("c", "o", "h", "l", "v"))
    a = float(d.atr.iloc[-1]); px = float(h1r.c.iloc[-1]); ph, pl = pivots(hi, lo)
    struct = 50 + (25 if len(ph) >= 2 and hi[ph[-1]] > hi[ph[-2]] else -25) + (25 if len(pl) >= 2 and lo[pl[-1]] > lo[pl[-2]] else -25)
    up_v, dn_v = np.where(c > o, v, 0.0)[-12:].sum(), np.where(c < o, v, 0.0)[-12:].sum(); press = (up_v - dn_v) / max(up_v + dn_v, 1e-9); vr = float(v[-6:].mean() / max(v[-48:].mean(), 1e-9))
    mom6 = (c[-1] - c[-7]) / a; accel = mom6 - (c[-4] - c[-10]) / a; atrp = float((d.atr.iloc[-200:] < d.atr.iloc[-1]).mean() * 100)
    e4, d4 = float(d.er4.iloc[-1]), float(d.dir4.iloc[-1]); imb, oisig, of_note = 0.0, 0.0, "no order-flow data yet"
    if log is not None and "book_imbalance" in log and log.book_imbalance.notna().any():
        imb = float(log.book_imbalance.dropna().iloc[-1]); of_note = f"book imbalance {imb:+.2f}"
        if len(log) > 49:
            oc = float(log.oi_usd.iloc[-1] / log.oi_usd.iloc[-49] - 1); pc = c[-1] / c[-5] - 1; oisig = (1 if pc > 0 else -1) if oc > 0.002 else 0.0; of_note += f", OI {oc * 100:+.2f}% (4h)"
    above, below = [hi[i] for i in ph if hi[i] > px], [lo[i] for i in pl if lo[i] < px]; du = (min(above) - px) / a if above else 10.0; dd = (px - max(below)) / a if below else 10.0
    comp = dict(structure=struct, volume=50 + 40 * press, momentum=float(np.clip(50 + 20 * mom6 + 10 * accel, 0, 100)), order_flow=float(np.clip(50 + 25 * imb + 25 * oisig, 0, 100)),
                liquidity=float(np.clip(50 + 10 * (du - dd), 0, 100)), htf=float(np.clip(50 + 50 * e4 * (1 if d4 > 0 else -1), 0, 100)))
    lean = float(np.mean(list(comp.values())) - 50); side = 1 if lean > 8 else -1 if lean < -8 else 0; name = {1: "LONG", -1: "SHORT", 0: "NONE"}[side]
    ds = {x: (y if side >= 0 else 100 - y) for x, y in comp.items()}; wts = dict(structure=.2, htf=.2, momentum=.15, order_flow=.15, volume=.1, liquidity=.1)
    setup = float(sum(ds[x] * wts[x] for x in wts) / sum(wts.values())) if side else 0.0; cont = float(np.mean([ds["momentum"], ds["volume"], ds["htf"]]))
    ext = abs(c[-1] - c[-24:].mean()) / a; exh = float(min(100, 20 * ext + (20 if vr < 0.7 else 0)))
    rh, rl = float(hi[-96:].max()), float(lo[-96:].min()); pos = (px - rl) / max(rh - rl, 1e-9); rp, rq = float(hi[-108:-12].max()), float(lo[-108:-12].min())
    bu, bd = bool((c[-12:] > rp + .2 * a).any()), bool((c[-12:] < rq - .2 * a).any())
    if bu and c[-1] <= rp: brk = "FAILED BREAKOUT (up)"
    elif bd and c[-1] >= rq: brk = "FAILED BREAKOUT (down)"
    elif bu and lo[-1] <= rp + .3 * a: brk = "BREAKOUT RETEST (up)"
    elif bd and hi[-1] >= rq - .3 * a: brk = "BREAKOUT RETEST (down)"
    elif c[-1] > rp + .2 * a and vr > 1.3: brk = "BREAKOUT CONFIRMED (up)"
    elif c[-1] < rq - .2 * a and vr > 1.3: brk = "BREAKOUT CONFIRMED (down)"
    elif atrp < 30 and (rh - px < .5 * a or px - rl < .5 * a): brk = "BREAKOUT WATCH"
    else: brk = "none"
    od = odds(stats, a / px * 100); lmp = None; zones = None
    if od:
        b, Hb, Qb, nb = od; p2k = float(np.interp(2000 / px * 100, stats["grid"], Hb["up"])) + float(np.interp(2000 / px * 100, stats["grid"], Hb["dn"]))
        pmax = max(float(np.interp(2000 / px * 100, stats["grid"], stats["H"]["24"][str(i)]["up"])) + float(np.interp(2000 / px * 100, stats["grid"], stats["H"]["24"][str(i)]["dn"])) for i in range(3))
        lmp = round(100 * p2k / max(pmax, 1e-9))
    lv = None
    if side:
        kd = lambda x: x * side; pxd = kd(px); hd, ld = (hi, lo) if side == 1 else (-lo, -hi); conf = float(hd[-8:].max()); pref = min(float(ld[-12:].min()) - .4 * a, pxd - .8 * a)
        hard = float(ld[pl[-1]]) if (side == 1 and pl) else float(ld[-12:].min()); emerg = pxd - 3 * a; R_ = pxd - pref
        if od: key = "up" if side == 1 else "dn"; q = [x / 100 * px for x in Qb[key]]; tg = [pxd + q[0], pxd + q[1], pxd + q[2], pxd + q[3]]
        else: tg = [pxd + m * R_ for m in (1.5, 3, 5, 8)]
        zone = lambda x, y: sorted([kd(x), kd(y)])
        lv = dict(early_zone=zone(pxd - .3 * a, pxd + .1 * a), confirmation=kd(conf) , retest_zone=zone(conf - .3 * a, conf + .1 * a), late_above=kd(conf + a), hard_invalidation=kd(min(hard, pref)), preferred_sl=kd(pref),
                  emergency_sl=kd(emerg), t1=kd(tg[0]), t2=kd(tg[1]), t3=kd(tg[2]), extended=kd(tg[3]), rr_t1=round(float((tg[0] - pxd) / R_), 2), targets_from="history quantiles" if od else "ATR multiples (run research workflow)")
        late = (px > lv["late_above"]) if side == 1 else (px < lv["late_above"]); inz = lv["early_zone"][0] <= px <= lv["early_zone"][1]
        lv["entry_state"] = "LATE: avoid chasing" if late else ("inside EARLY entry zone" if inz else "between zones: wait for early zone or confirmation")
    fl = []
    if side:
        opp = dd if side == 1 else du; wk = (hi[-1] - max(c[-1], o[-1])) / max(hi[-1] - lo[-1], 1e-9) if side == 1 else (min(c[-1], o[-1]) - lo[-1]) / max(hi[-1] - lo[-1], 1e-9)
        sweep = bool((side == 1 and lo[-6:].min() < lo[-30:-6].min() and c[-1] > lo[-30:-6].min()) or (side == -1 and hi[-6:].max() > hi[-30:-6].max() and c[-1] < hi[-30:-6].max()))
        fl = [("Volume not supporting the move", vr < .8 or ds["volume"] < 50), ("Market structure not supporting", ds["structure"] < 50), ("Liquidity against the trade (level within 1 ATR)", (du if side == 1 else dd) < 1),
              ("Higher timeframe against", ds["htf"] < 45), ("Momentum not improving", (accel if side == 1 else -accel) <= 0), ("Price rejecting the direction (wick)", wk > .5),
              ("Possible liquidity trap (sweep and reverse)", sweep), ("Failed-breakout signs", "FAILED" in brk), ("Volatility too high (top 10%)", atrp > 90), ("Middle of range", .35 < pos < .65)]
    nfl = sum(f[1] for f in fl); frisk = "Low" if nfl <= 2 else "Medium" if nfl <= 4 else "High"
    if has_trade: status = "TRADE ACTIVE (see Home)"
    elif not side or nfl >= 5 or setup < 60: status = "NO TRADE"
    else: status = f"EARLY {name} SETUP (experimental)" if setup >= 65 else f"WATCH ONLY ({name} lean, weak)"
    mx = max(scores.values()) if scores else 0
    stage = ("Stage 4-5: trade active" if has_trade else "Stage 6: exhaustion risk" if exh >= 70 else "Stage 3: momentum confirming" if (side and "CONFIRMED" in brk) else
             "Stage 2: early setup" if status.startswith("EARLY") else "Stage 1: accumulation/distribution developing" if mx >= 40 else "Stage 0: no clear opportunity")
    ex = None
    if od: key = "up" if side >= 0 else "dn"; q = [x / 100 * px for x in Qb[key]]; ex = dict(expected=[q[0], q[1]], strong=[q[1], q[2]], extended=[q[2], q[3]], side=key, sample=nb,
                                                                              odds={str(x): [round(float(np.interp(x / px * 100, stats["grid"], Hb["up"])), 3), round(float(np.interp(x / px * 100, stats["grid"], Hb["dn"])), 3)] for x in (500, 1000, 2000, 5000, 10000)})
    return _py(dict(price=px, regime=regime, stage=stage, status=status, direction=name, scores=dict(comp, accumulation=scores.get("LONG") if scores else None, distribution=scores.get("SHORT") if scores else None,
                    volatility_pct=atrp, large_move_potential=lmp, continuation=cont, exhaustion_risk=exh, setup=setup), levels=lv, expected_move=ex, checklist=[[x, y] for x, y in fl], false_signal_risk=frisk if side else "n/a",
                    range=dict(high=rh, low=rl, mid=(rh + rl) / 2, position_pct=pos * 100), breakout=brk, notes=dict(order_flow=of_note, atr=a, funding=fr, oi=oi)))

def text(A):
    if not A: return "Analysis abhi tayar nahi hai (agle scan ka intezaar karo)."
    s, L = A["scores"], A.get("levels"); t = [f"📋 ANALYSIS | BTC ${A['price']:,.0f}", f"Regime: {A['regime']} | {A['stage']}", f"Status: {A['status']} (direction lean: {A['direction']})",
        f"Setup {s['setup']:.0f} | Accumulation {s.get('accumulation')} | Distribution {s.get('distribution')} | Large-move potential {s.get('large_move_potential')}", f"False-signal risk: {A['false_signal_risk']} | Breakout: {A['breakout']}"]
    if L: t += [f"Early zone ${L['early_zone'][0]:,.0f}-{L['early_zone'][1]:,.0f} | Confirm ${L['confirmation']:,.0f} | SL ${L['preferred_sl']:,.0f}", f"T1 ${L['t1']:,.0f} | T2 ${L['t2']:,.0f} | T3 ${L['t3']:,.0f} | Ext ${L['extended']:,.0f}"]
    return "\n".join(t) + "\nEstimates, not predictions. Backtests show no proven edge."
