"""Ask-the-market: data side. Builds HISTORY STATS (free OKX public data, no API key) that answer
'if the market looks like THIS right now, what happened in the next 5 min / 15 min / 1 h / 4 h / 24 h in the past?'.
State = the 7-method consensus score (methods.py) on the last COMPLETED candle -> 5 buckets. Per bucket and horizon we store:
  P(up), sample size, typical move size, and P(up) in each half of history (so the answer can say if the lean is STABLE or just noise).
Also per volatility tercile: how often price reached +/-x% within the horizon (for 'kya 90000 tak jayega?' type questions).
Honest by design: direction odds near 50% are reported as 'no edge'. Nothing here is a prediction or an order."""
import os, json, time, datetime as dt
import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
import methods as MT

FILE = "ask_stats.json"; REBUILD_DAYS = 7
BNAME = ["STRONG SHORT jhukaav", "halka SHORT jhukaav", "NEUTRAL / mila-jula", "halka LONG jhukaav", "STRONG LONG jhukaav"]
VNAME = ["shaant (calm)", "normal", "tez (wild)"]
GRID = [0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 7, 10]            # percent
HZ = {5: ("5m", 1), 15: ("5m", 3), 30: ("5m", 6), 60: ("1H", 1), 120: ("1H", 2), 240: ("1H", 4), 1440: ("1H", 24)}   # minutes -> (candle frame, bars ahead)
HZ_NAME = {5: "5 min", 15: "15 min", 30: "30 min", 60: "1 ghanta", 120: "2 ghante", 240: "4 ghante", 1440: "24 ghante (1 din)"}
FRAMES = {"5m": dict(bar="5m", days=30, per_day=288), "1H": dict(bar="1H", days=365, per_day=24)}


def bucket(net): return 0 if net <= -35 else 1 if net <= -10 else 2 if net < 10 else 3 if net < 35 else 4


def net_of(vs):
    if not vs: return None
    W = sum(MT.WEIGHTS[k] for k, *_ in vs); return float(sum(d * s * MT.WEIGHTS[k] for k, d, s, _ in vs) / W * 100)


def fetch(bar, days, budget_s=40):
    import engine as E
    per = FRAMES[bar]["per_day"]; out, after, t0 = [], "", time.time()
    while len(out) < days * per and time.time() - t0 < budget_s:
        q = dict(instId=E.INST, bar=bar, limit=100)
        if after: q["after"] = after
        try: d = E._get("market/history-candles", **q)
        except Exception as e: print("ask fetch stopped:", bar, e); break
        if not d: break
        out += d; after = d[-1][0]; time.sleep(0.08)
    df = pd.DataFrame([x[:6] for x in out], columns=["ts", "o", "h", "l", "c", "v"]).astype(float)
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def _nets(df):
    I = MT.prepare(df); n = I["n"]; net = np.full(n, np.nan)
    for i in range(210, n):
        v = net_of(MT.votes(I, i))
        if v is not None: net[i] = v
    return I, net


def build_frame(df, hbars):
    """df: candles. hbars: list of bars-ahead. Returns the stats block for this candle frame."""
    I, net = _nets(df); n = I["n"]; c, hi, lo = I["c"], I["h"], I["l"]; atrp = I["atr"] / np.maximum(c, 1e-9) * 100
    ok = ~np.isnan(net) & ~np.isnan(atrp)
    if ok.sum() < 800: return None
    e1, e2 = np.percentile(atrp[ok], [33.3, 66.7]); vb = (atrp > e1).astype(int) + (atrp > e2).astype(int)
    out = dict(rows=int(ok.sum()), vol_edges=[round(float(e1), 4), round(float(e2), 4)], H={})
    for H in hbars:
        m_i = ok.copy(); m_i[n - H:] = False                                    # decision bars that have H bars after them
        idx = np.where(m_i)[0]
        if len(idx) < 500: continue
        r = np.full(n, np.nan); r[:n - H] = (c[H:] - c[:n - H]) / c[:n - H] * 100
        mx = sliding_window_view(hi, H).max(axis=1); mn = sliding_window_view(lo, H).min(axis=1)       # window j..j+H-1
        upx = np.full(n, np.nan); dnx = np.full(n, np.nan); upx[:n - H] = (mx[1:n - H + 1] - c[:n - H]) / c[:n - H] * 100; dnx[:n - H] = (c[:n - H] - mn[1:n - H + 1]) / c[:n - H] * 100
        half = idx[len(idx) // 2]; up = (r > 0)
        blk = dict(h_bars=H, n=int(len(idx)), base=dict(p_up=round(float(up[idx].mean()), 4), p1=round(float(up[idx[idx < half]].mean()), 4), p2=round(float(up[idx[idx >= half]].mean()), 4)), by_net={}, by_vol={})
        b = np.array([bucket(x) if x == x else -1 for x in net])
        for k in range(5):
            s = idx[b[idx] == k]
            if len(s) < 30: continue
            s1, s2 = s[s < half], s[s >= half]
            blk["by_net"][str(k)] = dict(n=int(len(s)), p_up=round(float(up[s].mean()), 4), p1=round(float(up[s1].mean()), 4) if len(s1) >= 15 else None, p2=round(float(up[s2].mean()), 4) if len(s2) >= 15 else None,
                                         n1=int(len(s1)), n2=int(len(s2)), avg=round(float(r[s].mean()), 4), absq=[round(float(q), 4) for q in np.percentile(np.abs(r[s]), [25, 50, 75, 90])])
        for k in range(3):
            s = idx[vb[idx] == k]
            if len(s) < 50: continue
            blk["by_vol"][str(k)] = dict(n=int(len(s)), up=[round(float((upx[s] >= g).mean()), 4) for g in GRID], dn=[round(float((dnx[s] >= g).mean()), 4) for g in GRID],
                                         absq=[round(float(q), 4) for q in np.percentile(np.abs(r[s]), [25, 50, 75, 90])], upq=[round(float(q), 4) for q in np.percentile(upx[s], [50, 90])], dnq=[round(float(q), 4) for q in np.percentile(dnx[s], [50, 90])])
        out["H"][str(H)] = blk
    return out


def build(budget_s=40):
    res = dict(built=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), frames={}, grid=GRID)
    for fr, cfg in FRAMES.items():
        try:
            df = fetch(cfg["bar"], cfg["days"], budget_s); hb = sorted({b for m, (f, b) in HZ.items() if f == fr})
            blk = build_frame(df, hb) if len(df) > 1000 else None
            if blk: blk["from"] = int(df.ts.iloc[0]); blk["to"] = int(df.ts.iloc[-1]); res["frames"][fr] = blk
        except Exception as e: print("ask build error", fr, e)
    return res


def load():
    try: return json.load(open(FILE))
    except Exception: return None


def ensure(now, budget_s=40, force=False):
    """Rebuild every REBUILD_DAYS days. Never raises."""
    try:
        st = load()
        if st and not force and (now - dt.datetime.fromisoformat(st["built"])).total_seconds() < REBUILD_DAYS * 86400: return st
        new = build(budget_s)
        if new["frames"]: json.dump(new, open(FILE, "w"), separators=(",", ":")); return new
        return st
    except Exception as e: print("ask ensure error", e); return load()


def live_state(m5, h1):
    """Called every scan: the same 7-method score, on the last completed candle of each frame. Stored in state.json so the dashboard needs no network."""
    out = {}
    for name, df in (("5m", m5), ("1H", h1)):
        try:
            if df is None or len(df) < 215: continue
            I = MT.prepare(df.reset_index(drop=True)); i = I["n"] - 2; vs = MT.votes(I, i); net = net_of(vs)
            if net is None: continue
            out[name] = dict(net=round(net, 1), bucket=bucket(net), rsi=round(float(I["rsi"][i]), 1), atr_pct=round(float(I["atr"][i] / I["c"][i] * 100), 4), price=round(float(I["c"][i]), 1), ts=float(df.ts.iloc[-2]),
                             votes=[[MT.NAMES[k], int(d), t] for k, d, s, t in vs])
        except Exception as e: print("ask live_state error", name, e)
    return out


def resolve(S, m5, h1, now):
    """Fill in outcomes of forecasts we logged earlier (so we can show the REAL hit-rate of this feature over time)."""
    L = S.get("ask_log") or []
    for e in L:
        if e.get("done") or not e.get("p_up"): continue
        due = dt.datetime.fromisoformat(e["due"])
        if now < due: continue
        df = h1 if e["h"] >= 240 else m5; due_ms = due.timestamp() * 1000
        try:
            row = df[df.ts >= due_ms].head(1)
            if len(row) and row.ts.iloc[0] - due_ms < 2 * (3600e3 if df is h1 else 300e3): e["px1"] = float(row.o.iloc[0]); e["up"] = bool(e["px1"] > e["px0"]); e["done"] = True
            elif (now - due).total_seconds() > 2 * 86400: e["done"] = True; e["up"] = None
        except Exception: pass
    S["ask_log"] = L[-300:]


def daily(h1, now, n_days=10):
    """Per IST calendar day (00:00-24:00 IST) from 1H candles: open/high/low/close, how far it went UP and DOWN from the open, in points and %.
    Used for 'kal kitna move hua' and for sizing stop-loss. Last row is TODAY (so far)."""
    d = h1.copy(); d["ist"] = pd.to_datetime(d.ts, unit="ms", utc=True) + pd.Timedelta(hours=5, minutes=30); d["day"] = d.ist.dt.strftime("%Y-%m-%d")
    today = (now + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d"); rows = []
    for day, g in d.groupby("day", sort=True):
        o, hi, lo, c = float(g.o.iloc[0]), float(g.h.max()), float(g.l.min()), float(g.c.iloc[-1])
        rows.append(dict(day=day, today=day == today, bars=int(len(g)), open=round(o, 1), high=round(hi, 1), low=round(lo, 1), close=round(c, 1), up=round(hi - o, 1), dn=round(o - lo, 1), rng=round(hi - lo, 1),
                         up_pct=round((hi - o) / o * 100, 2), dn_pct=round((o - lo) / o * 100, 2), rng_pct=round((hi - lo) / o * 100, 2), chg=round(c - o, 1), chg_pct=round((c - o) / o * 100, 2), full=len(g) >= 23))
    rows = rows[-n_days:]; full = [r for r in rows if r["full"] and not r["today"]]; k = full[-7:]
    avg = dict(n=len(k), rng=round(float(np.mean([r["rng"] for r in k])), 0), rng_pct=round(float(np.mean([r["rng_pct"] for r in k])), 2), up=round(float(np.mean([r["up"] for r in k])), 0), dn=round(float(np.mean([r["dn"] for r in k])), 0),
               max_rng=round(float(max(r["rng"] for r in k)), 0), min_rng=round(float(min(r["rng"] for r in k)), 0)) if k else None
    return dict(rows=rows, avg7=avg, ts=now.isoformat(timespec="seconds"))


def daily_text(D, px=None):
    if not D or not D.get("rows"): return "Daily move data abhi ready nahi (agle scan ke baad aa jayega)."
    R = D["rows"]; full = [r for r in R if not r["today"]]; L = ["📆 DIN-WAR MOVE (IST din: raat 12 se raat 12)"]
    if full:
        y = full[-1]; L.append(f"KAL ({y['day']}): open ${y['open']:,.0f} → close ${y['close']:,.0f} ({y['chg']:+,.0f} pts, {y['chg_pct']:+.2f}%)\n   Upar tak gaya: +{y['up']:,.0f} pts (+{y['up_pct']:.2f}%) | Neeche tak gaya: -{y['dn']:,.0f} pts (-{y['dn_pct']:.2f}%) | Poora range {y['rng']:,.0f} pts ({y['rng_pct']:.2f}%)")
    t = [r for r in R if r["today"]]
    if t: r = t[-1]; L.append(f"AAJ ABHI TAK: upar +{r['up']:,.0f} pts ({r['up_pct']:.2f}%), neeche -{r['dn']:,.0f} pts ({r['dn_pct']:.2f}%), range {r['rng']:,.0f} pts")
    L.append("Pichhle dinon ka (upar / neeche / range, points):")
    for r in full[-6:][::-1]: L.append(f"  {r['day'][5:]}: +{r['up']:,.0f} / -{r['dn']:,.0f} / {r['rng']:,.0f}  ({r['rng_pct']:.1f}%)")
    a = D.get("avg7")
    if a: L.append(f"Pichhle {a['n']} din ka average: upar +{a['up']:,.0f}, neeche -{a['dn']:,.0f} pts, range {a['rng']:,.0f} pts ({a['rng_pct']:.1f}%). Sabse chhota din {a['min_rng']:,.0f}, sabse bada {a['max_rng']:,.0f} pts.")
    if a: L.append(f"Stop-loss ke liye: ek din mein aam tor par {a['rng']:,.0f} pts ghoom jata hai, isliye bahut chhota stop (jaise {a['rng'] * 0.1:,.0f} pts) normal halchal mein hi kat sakta hai. Stop apne setup ke swing/ATR ke hisaab se rakho; ye range sirf ek andaaza hai.")
    return "\n".join(L)


if __name__ == "__main__":
    st = ensure(dt.datetime.now(dt.timezone.utc), budget_s=120, force=True)
    print({f: {h: (b["n"], b["base"]["p_up"]) for h, b in v["H"].items()} for f, v in (st or {}).get("frames", {}).items()})
