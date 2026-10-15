"""Support / resistance PER TIMEFRAME (5m, 15m, 1H, 4H, 1D) from confirmed swing points, clustered, with touch counts,
plus CONFLUENCE zones where several timeframes agree. Uses only past candles."""
import numpy as np
import methods as MT

TFS = ["5m", "15m", "1H", "4H", "1D"]; WEIGHT = {"5m": 1.0, "15m": 1.5, "1H": 2.0, "4H": 3.0, "1D": 4.0}


def levels_for(df, px, keep=2, look=220):
    """Nearest `keep` supports below and resistances above px for one timeframe."""
    d = df.tail(look + 10).reset_index(drop=True)
    if len(d) < 40: return dict(atr=None, supports=[], resistances=[])
    I = MT.prepare(d); a = float(I["atr"][-1]); n = I["n"]; tol = 0.35 * a
    pts = [(float(v), j) for arr in (I["sh"], I["sl"]) for j, v in enumerate(arr) if v == v]          # confirmed pivots (highs and lows)
    pts.sort(); cl = []
    for v, j in pts:
        if cl and v - cl[-1]["p"] <= tol: c = cl[-1]; c["vals"].append(v); c["p"] = float(np.mean(c["vals"])); c["last"] = max(c["last"], j)
        else: cl.append(dict(p=v, vals=[v], last=j))
    h, l, c_ = I["h"], I["l"], I["c"]; out = []
    for c in cl:
        p = c["p"]; touches = int(((abs(h - p) <= 0.25 * a) & (c_ < p)).sum() + ((abs(l - p) <= 0.25 * a) & (c_ > p)).sum())
        out.append(dict(price=round(p, 1), touches=max(touches, len(c["vals"])), recent=bool(n - c["last"] <= 40), dist_pct=round((p - px) / px * 100, 2), dist_atr=round((p - px) / a, 1)))
    sup = sorted([x for x in out if x["price"] < px], key=lambda x: -x["price"])[:keep]; res = sorted([x for x in out if x["price"] > px], key=lambda x: x["price"])[:keep]
    return dict(atr=round(a, 1), supports=sup, resistances=res)


def build(frames, px):
    per = {tf: levels_for(frames[tf], px) for tf in TFS if tf in frames and frames[tf] is not None and len(frames[tf]) >= 60}
    allp = [(x["price"], tf, WEIGHT[tf] + min(x["touches"], 5) * 0.3) for tf, v in per.items() for x in v["supports"] + v["resistances"]]
    allp.sort(); zones, tol = [], px * 0.0025
    for p, tf, w in allp:
        if zones and p - zones[-1]["hi"] <= tol: z = zones[-1]; z["hi"] = p; z["tfs"].add(tf); z["score"] += w; z["ps"].append(p)
        else: zones.append(dict(lo=p, hi=p, tfs={tf}, score=w, ps=[p]))
    Z = [dict(lo=round(min(z["ps"]), 1), hi=round(max(z["ps"]), 1), mid=round(float(np.mean(z["ps"])), 1), tfs=sorted(z["tfs"], key=TFS.index), score=round(z["score"], 1), kind="support" if np.mean(z["ps"]) < px else "resistance") for z in zones if len(z["tfs"]) >= 2]
    Z.sort(key=lambda z: -z["score"])
    return dict(px=round(px, 1), tf=per, zones=Z[:6])


def text(R):
    if not R or not R.get("tf"): return "Support/Resistance abhi ready nahi."
    L = [f"📐 SUPPORT / RESISTANCE (BTC ${R['px']:,.0f})"]
    for tf in TFS:
        v = R["tf"].get(tf)
        if not v: continue
        s = ", ".join(f"${x['price']:,.0f} ({x['touches']}x, {x['dist_pct']:+.1f}%)" for x in v["supports"]) or "-"; r = ", ".join(f"${x['price']:,.0f} ({x['touches']}x, {x['dist_pct']:+.1f}%)" for x in v["resistances"]) or "-"
        L.append(f"{tf}: 🟢 support {s} | 🔴 resistance {r}")
    if R.get("zones"):
        L.append("🎯 Confluence zones (kai timeframe ek jagah):")
        for z in R["zones"][:4]: L.append(f"{'🟢' if z['kind'] == 'support' else '🔴'} {z['kind']} ${z['lo']:,.0f}-{z['hi']:,.0f} ({'+'.join(z['tfs'])}, score {z['score']})")
    L.append("(touches = kitni baar bhaav yahan se palta. Zyada touches + zyada timeframe = mazboot level.)")
    return "\n".join(L)
