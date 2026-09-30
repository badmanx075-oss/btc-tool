"""Analysis engine: regime -> early setup -> levels. Public OKX data, no API key."""
import requests, pandas as pd

B = "https://www.okx.com/api/v5/"; INST = "BTC-USDT-SWAP"

def _get(p, **q):
    r = requests.get(B + p, params=q, timeout=15); r.raise_for_status(); return r.json()["data"]

BY = "https://api.bybit.com/v5/market/"; IV = {"5m": "5", "15m": "15", "1H": "60", "4H": "240"}

def candles(bar, limit=300):
    try:  # primary: OKX
        rows = [x[:6] for x in _get("market/candles", instId=INST, bar=bar, limit=limit)]
    except Exception:  # fallback: Bybit
        r = requests.get(BY + "kline", params=dict(category="linear", symbol="BTCUSDT", interval=IV[bar], limit=limit), timeout=15)
        r.raise_for_status(); rows = [x[:6] for x in r.json()["result"]["list"]]
    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"]).astype(float)
    return df.sort_values("ts").reset_index(drop=True)

def _tick():
    r = requests.get(BY + "tickers", params=dict(category="linear", symbol="BTCUSDT"), timeout=15); r.raise_for_status()
    return r.json()["result"]["list"][0]

def funding():
    try: return float(_get("public/funding-rate", instId=INST)[0]["fundingRate"])
    except Exception:
        try: return float(_tick()["fundingRate"])
        except Exception: return 0.0

def open_interest():
    try: return float(_get("public/open-interest", instType="SWAP", instId=INST)[0]["oiUsd"])
    except Exception:
        try: return float(_tick()["openInterestValue"])
        except Exception: return 0.0

TR = {"price near range low": "price near range high", "failed breakdown / liquidity sweep": "failed breakout / sweep of highs",
      "no sweep of prior lows": "no sweep of prior highs", "higher low forming": "lower high forming", "no higher low yet": "no lower high yet",
      "selling volume fading": "buying volume fading", "selling volume not fading": "buying volume not fading",
      "momentum turning up": "momentum turning down"}

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
        if k == -1: pro = [TR.get(x, x) for x in pro]; con = [TR.get(x, x) for x in con]
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
    gap = best["score"] - other["score"]
    best["signal"] = "NO TRADE" if best["score"] < 60 or gap < 15 else ("EARLY " + best["side"] + " SETUP" if best["score"] >= 65 else "WATCH: WEAK " + best["side"] + " SETUP")
    best["regime"] = reg
    return best
