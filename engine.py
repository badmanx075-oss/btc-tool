"""Analysis engine: regime -> early setup -> levels. Public OKX data, no API key."""
import requests, pandas as pd

B = "https://www.okx.com/api/v5/"; INST = "BTC-USDT-SWAP"

def _get(p, **q):
    r = requests.get(B + p, params=q, timeout=15); r.raise_for_status(); return r.json()["data"]

def candles(bar, limit=300):
    d = _get("market/candles", instId=INST, bar=bar, limit=limit)
    df = pd.DataFrame([x[:6] for x in d], columns=["ts", "o", "h", "l", "c", "v"]).astype(float)
    return df.sort_values("ts").reset_index(drop=True)

def funding(): return float(_get("public/funding-rate", instId=INST)[0]["fundingRate"])
def open_interest(): return float(_get("public/open-interest", instType="SWAP", instId=INST)[0]["oiUsd"])

def atr_series(df, n=14):
    pc = df.c.shift()
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _er(s):  # efficiency ratio: 1 = straight trend, 0 = noise
    return abs(s.iloc[-1] - s.iloc[0]) / max(s.diff().abs().sum(), 1e-9)

def regime(h4, h1):
    s, s1 = h4.c.tail(30), h1.c.tail(24)
    e, e1, up, up1 = _er(s), _er(s1), s.iloc[-1] > s.iloc[0], s1.iloc[-1] > s1.iloc[0]
    if e > 0.3:
        if up: return "TRANSITION BULL->BEAR" if (e1 > 0.4 and not up1) else "BULLISH TREND"
        return "TRANSITION BEAR->BULL" if (e1 > 0.4 and up1) else "BEARISH TREND"
    return "RANGE" if e < 0.2 else "UNCLEAR / NO-TRADE"

def _long_score(d, reg_bad):
    """Long logic on frame d; short is run on a mirrored frame (price negated)."""
    a = atr_series(d); w = d.tail(64); px = d.c.iloc[-1]
    pos = (px - w.l.min()) / max(w.h.max() - w.l.min(), 1e-9)
    pro, con, sc = [], [], 0
    def add(ok, pts, yes, no):
        nonlocal sc
        if ok: sc += pts; pro.append(yes)
        else: con.append(no)
    add(pos < 0.3, 20, "price near range low", "price not at range edge (mid-range risk)")
    prior_low = d.l.iloc[-46:-6].min()
    add(d.l.tail(6).min() < prior_low and px > prior_low, 25, "failed breakdown / liquidity sweep", "no sweep of prior lows")
    add(d.l.tail(8).min() > d.l.iloc[-24:-8].min(), 15, "higher low forming", "no higher low yet")
    dn = lambda x: x[x.c < x.o].v.sum()
    add(dn(d.tail(8)) < dn(d.iloc[-16:-8]), 15, "selling volume fading", "selling volume not fading")
    add(a.iloc[-1] < a.tail(20).mean() * 0.9, 10, "volatility compression", "no compression")
    add(px > d.c.iloc[-4] and d.c.iloc[-1] > d.o.iloc[-1], 15, "momentum turning up", "momentum not turning")
    if reg_bad: sc -= 15; con.append("higher-timeframe regime against setup")
    return max(sc, 0), pro, con

def _mirror(d):
    m = d.copy(); m["o"], m["c"], m["h"], m["l"] = -d.o, -d.c, -d.l, -d.h; return m

def scan(m15, h4, h1):
    reg = regime(h4, h1); res = []
    for side, k in (("LONG", 1), ("SHORT", -1)):
        d = m15 if k == 1 else _mirror(m15)
        bad = (side == "LONG" and reg == "BEARISH TREND") or (side == "SHORT" and reg == "BULLISH TREND")
        sc, pro, con = _long_score(d, bad)
        a = atr_series(d).iloc[-1]; px = d.c.iloc[-1]
        sl = min(d.l.tail(12).min() - 0.4 * a, px - 0.8 * a); R = px - sl
        lv = dict(entry=px, zone=sorted([k * (px - 0.3 * a), k * (px + 0.1 * a)]), sl=k * sl,
                  t1=k * (px + 1.5 * R), t2=k * (px + 3 * R), t3=k * (px + 5 * R), ext=k * (px + 8 * R),
                  confirm=k * d.h.tail(8).max())
        lv["entry"] = k * px
        res.append(dict(side=side, score=sc, pro=pro, con=con, **lv))
    best = max(res, key=lambda r: r["score"]); other = min(res, key=lambda r: r["score"])
    a4 = atr_series(h4).iloc[-1]; pts = abs(best["t3"] - best["entry"])
    ratio = pts / a4
    best["move_class"] = "SMALL" if ratio < 1 else "MEDIUM" if ratio < 2 else "LARGE" if ratio < 4 else "VERY LARGE"
    best["risk"] = "Low" if best["score"] >= 80 else "Medium" if best["score"] >= 65 else "High"
    best["signal"] = ("EARLY " + best["side"] + " SETUP") if best["score"] >= 60 and best["score"] - other["score"] >= 15 else "NO TRADE"
    best["regime"] = reg
    return best
