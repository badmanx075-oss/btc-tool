"""Time intelligence: WHEN does BTC move, and by how many points, up and down?
Built from long 1H history (hour-of-day, weekday, session). Used for: live 'activity window' card, pre-window alerts,
time-aware strategy filter (optional) and calibration of the tool's own trades by hour.
Honest note: WHEN volatility is high is a robust, repeatable pattern. WHICH DIRECTION it goes in an hour is mostly noise,
so direction stats are shown but flagged 'significant' only when clearly above chance."""
import os, json, time, math, datetime as dt
import numpy as np, pandas as pd

FILE = "time_stats.json"; IST_SHIFT = dt.timedelta(hours=5, minutes=30)
SESSIONS = [("Asia", 0, 8), ("Europe", 8, 13), ("US", 13, 21), ("Late", 21, 24)]


def ist_label(h):          # UTC hour h -> IST window of that candle, e.g. 0 -> '05:30-06:30'
    a = (dt.datetime(2000, 1, 1, h) + IST_SHIFT); b = a + dt.timedelta(hours=1); return f"{a:%H:%M}-{b:%H:%M}"


def session_of(h): return next(n for n, a, b in SESSIONS if a <= h < b)


def fetch_hist(days=365, budget_s=90):
    import engine as E
    out, after, t0 = [], "", time.time()
    while len(out) < days * 24 and time.time() - t0 < budget_s:
        q = dict(instId=E.INST, bar="1H", limit=100)
        if after: q["after"] = after
        try: d = E._get("market/history-candles", **q)
        except Exception as e: print("timing fetch stopped:", e); break
        if not d: break
        out += d; after = d[-1][0]; time.sleep(0.1)
    df = pd.DataFrame([x[:6] for x in out], columns=["ts", "o", "h", "l", "c", "v"]).astype(float)
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def _table(df):
    d = df.copy(); d["dt"] = pd.to_datetime(d.ts, unit="ms", utc=True); d["hr"] = d.dt.dt.hour; d["wd"] = d.dt.dt.weekday
    d["rng"] = d.h - d.l; d["up"] = d.h - d.o; d["dn"] = d.o - d.l; d["ret"] = d.c - d.o; d["volu"] = d.v
    rows, mean_rng = [], float(d.rng.mean())
    for h, g in d.groupby("hr"):
        n = len(g); sd = float(g.ret.std()) if n > 1 else 0.0; z = float(g.ret.mean() / (sd / math.sqrt(n))) if sd > 0 else 0.0
        rows.append(dict(hr=int(h), ist=ist_label(int(h)), session=session_of(int(h)), n=n, avg_range=round(float(g.rng.mean()), 1), med_range=round(float(g.rng.median()), 1),
                         avg_up=round(float(g.up.mean()), 1), avg_down=round(float(g.dn.mean()), 1), p_range_500=round(float((g.rng >= 500).mean()), 3), p_range_1000=round(float((g.rng >= 1000).mean()), 3),
                         p_up_500=round(float((g.up >= 500).mean()), 3), p_down_500=round(float((g.dn >= 500).mean()), 3), pct_green=round(float((g.ret > 0).mean() * 100), 1),
                         mean_ret=round(float(g.ret.mean()), 1), z=round(z, 2), significant_bias=bool(abs(z) >= 3), activity=round(float(g.rng.mean()) / mean_rng * 100)))
    return rows


def build(df):
    rows = _table(df); order = sorted(rows, key=lambda r: -r["activity"])
    for i, r in enumerate(order): r["cls"] = "HIGH" if i < 8 else "LOW" if i >= 16 else "MEDIUM"
    recent = _table(df[df.ts >= df.ts.max() - 60 * 86400000]) if len(df) > 24 * 90 else None
    d = df.copy(); d["dt"] = pd.to_datetime(d.ts, unit="ms", utc=True); d["day"] = d.dt.dt.date; d["wd"] = d.dt.dt.weekday
    dd = d.groupby("day").agg(h=("h", "max"), l=("l", "min"), wd=("wd", "first")); dd["rng"] = dd.h - dd.l; wk = []
    for w, nm in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")): g = dd[dd.wd == w]; wk.append(dict(day=nm, n=len(g), avg_day_range=round(float(g.rng.mean()), 0) if len(g) else None))
    ses = []
    for n, a, b in SESSIONS:
        g = [r for r in rows if r["session"] == n]; ses.append(dict(session=n, ist=f"{ist_label(a)[:5]}-{ist_label(b - 1)[-5:]}", avg_range_per_hour=round(float(np.mean([r['avg_range'] for r in g])), 1), avg_up=round(float(np.mean([r['avg_up'] for r in g])), 1), avg_down=round(float(np.mean([r['avg_down'] for r in g])), 1)))
    return dict(built=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), rows=len(df), days=round(len(df) / 24), first=str(pd.to_datetime(df.ts.min(), unit="ms").date()), hours=rows, recent=recent,
                weekdays=wk, sessions=ses, top_hours=[r["hr"] for r in order[:5]], quiet_hours=[r["hr"] for r in order[-5:]],
                note="Volatility timing is reliable; direction per hour is mostly noise (see significant_bias).")


def load(path=FILE):
    try: return json.load(open(path))
    except Exception: return None


def ensure(now, path=FILE, max_age_days=3, days=365):
    """Builds time_stats.json when missing or older than max_age_days. Runs rarely; never raises."""
    T = load(path)
    try:
        if T and (now - dt.datetime.fromisoformat(T["built"])).days < max_age_days: return T
        df = fetch_hist(days)
        if len(df) < 24 * 20: return T
        T = build(df); json.dump(T, open(path, "w")); return T
    except Exception as e: print("timing error", e); return T


def cls_of(T, hr):
    if not T: return None
    r = next((x for x in T["hours"] if x["hr"] == hr), None); return r["cls"] if r else None


def now_context(T, now):
    """What the current hour usually looks like, and the next active windows."""
    if not T: return None
    H = {r["hr"]: r for r in T["hours"]}; h = now.hour; r = H[h]; mins = 60 - now.minute
    nxt = next(((hh, H[hh]) for k in range(1, 7) for hh in [(h + k) % 24] if H[hh]["cls"] == "HIGH"), None)
    nxt_in = None if not nxt else ((nxt[0] - h) % 24) * 60 - now.minute
    return dict(hr=h, ist=r["ist"], cls=r["cls"], activity=r["activity"], avg_range=r["avg_range"], avg_up=r["avg_up"], avg_down=r["avg_down"], p_range_500=r["p_range_500"], p_range_1000=r["p_range_1000"],
                session=r["session"], next_high=None if not nxt else dict(hr=nxt[0], ist=nxt[1]["ist"], in_min=nxt_in, avg_range=nxt[1]["avg_range"], avg_up=nxt[1]["avg_up"], avg_down=nxt[1]["avg_down"]),
                top=[(x, H[x]["ist"], H[x]["avg_range"]) for x in T["top_hours"]], hist_days=T["days"])


def text(C):
    if not C: return "Time stats abhi bani nahi hain (pehle scan ke baad aa jayengi)."
    L = [f"🕒 TIME INTELLIGENCE (IST)\nAbhi: {C['ist']} ({C['session']} session) → activity {C['cls']} ({C['activity']}% of average)",
         f"Is ghante mein typical move: range {C['avg_range']:,.0f} pts | upar {C['avg_up']:,.0f} | neeche {C['avg_down']:,.0f} pts",
         f"500+ pts range ki sambhavna {C['p_range_500'] * 100:.0f}%, 1000+ ki {C['p_range_1000'] * 100:.0f}% (history {C['hist_days']} din)"]
    if C.get("next_high"): n = C["next_high"]; L.append(f"Agla HIGH window: {n['ist']} ({n['in_min']} min baad), typical range {n['avg_range']:,.0f} pts (up {n['avg_up']:,.0f} / down {n['avg_down']:,.0f})")
    L.append("Sabse active ghante (IST): " + ", ".join(f"{i} ({r:,.0f} pts)" for _, i, r in C["top"]))
    L.append("Dhyan: volatility ka samay bharosemand pattern hai, direction nahi.")
    return "\n".join(L)
