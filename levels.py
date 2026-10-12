"""Key price levels around the current price (spec 4, 14, 15, 22): previous-day / 7-day highs and lows, daily and 7-day VWAP,
swing support/resistance from 1H pivots, and round numbers. Nearby levels are merged into CONFLUENCE zones (several reasons at one price = stronger).
Descriptive only: levels are where price has reacted before, not guarantees."""
import numpy as np
import datetime as dt


def _pivots(hi, lo, w=3):
    return ([i for i in range(w, len(hi) - w) if hi[i] == hi[i - w:i + w + 1].max()], [i for i in range(w, len(lo) - w) if lo[i] == lo[i - w:i + w + 1].min()])


def _day(ts_ms): return dt.datetime.fromtimestamp(float(ts_ms) / 1000, dt.timezone.utc).date()


def collect(h1, px, atr1h):
    """h1: DataFrame ts,o,h,l,c,v (last row = live candle). Returns raw list of (name, price)."""
    d = h1.reset_index(drop=True); n = len(d); out = []
    if n < 60: return out
    days = np.array([_day(t) for t in d.ts.values]); today = days[-1]; prev = sorted(set(days))[-2] if len(set(days)) > 1 else None
    if prev is not None:
        m = days == prev; out += [("Previous day high", float(d.h[m].max())), ("Previous day low", float(d.l[m].min())), ("Previous day close", float(d.c[m].iloc[-1]))]
    mt = days == today; out += [("Today's high", float(d.h[mt].max())), ("Today's low", float(d.l[mt].min())), ("Today's open", float(d.o[mt].iloc[0]))]
    w = d.tail(168); out += [("7-day high", float(w.h.max())), ("7-day low", float(w.l.min()))]
    tp = (d.h + d.l + d.c) / 3
    if mt.sum() >= 2 and d.v[mt].sum() > 0: out.append(("Today's VWAP", float((tp[mt] * d.v[mt]).sum() / d.v[mt].sum())))
    if w.v.sum() > 0: out.append(("7-day VWAP", float((tp.tail(168) * w.v).sum() / w.v.sum())))
    hi, lo = d.h.values[:-1], d.l.values[:-1]; ph, pl = _pivots(hi[-200:], lo[-200:]); off = max(len(hi) - 200, 0)
    for i in ph[-6:]: out.append(("Swing high", float(hi[off + i])))
    for i in pl[-6:]: out.append(("Swing low", float(lo[off + i])))
    for step, nm in ((1000, "Round number"), (500, "Half-round number")):
        base = round(px / step) * step
        for k in range(-3, 4):
            lvl = base + k * step
            if lvl > 0 and abs(lvl - px) / px < 0.04 and (step == 1000 or lvl % 1000): out.append((nm, float(lvl)))
    return out


def ladder(h1, px, atr1h, atr4h=None, merge_atr=0.25, keep=4):
    """Merge nearby levels into zones and split into resistance (above) and support (below)."""
    raw = sorted(collect(h1, px, atr1h), key=lambda x: x[1]); zones = []
    for name, p in raw:
        if zones and abs(p - zones[-1]["price"]) <= merge_atr * atr1h:
            z = zones[-1]; z["names"].append(name); z["prices"].append(p); z["price"] = float(np.mean(z["prices"]))
        else: zones.append(dict(price=p, prices=[p], names=[name]))
    rows = []
    for z in zones:
        dist = z["price"] - px; names = sorted(set(z["names"]), key=z["names"].index)
        weight = len(z["names"]) + (1 if any(x in ("Previous day high", "Previous day low", "7-day high", "7-day low") for x in names) else 0)
        rows.append(dict(price=round(z["price"], 1), names=names, count=len(z["names"]), strength="strong" if weight >= 3 else "medium" if weight == 2 else "light",
                         dist_pts=round(dist, 1), dist_pct=round(dist / px * 100, 2), dist_atr1h=round(dist / max(atr1h, 1e-9), 2), side="resistance" if dist > 0 else "support"))
    up = sorted([r for r in rows if r["side"] == "resistance"], key=lambda r: r["dist_pts"])[:keep]; dn = sorted([r for r in rows if r["side"] == "support"], key=lambda r: -r["dist_pts"])[:keep]
    vw = next((p for n, p in raw if n == "Today's VWAP"), None); ext = None
    if vw is not None:
        e = (px - vw) / max(atr1h, 1e-9); ext = dict(vwap=round(vw, 1), dev_atr=round(e, 2), note=("far above VWAP (stretched): chasing longs is risky" if e > 2.5 else "far below VWAP (stretched): chasing shorts is risky" if e < -2.5 else "near VWAP (not stretched)"))
    return dict(price=px, resistance=up, support=dn, vwap=ext, nearest_resistance=up[0] if up else None, nearest_support=dn[0] if dn else None)
