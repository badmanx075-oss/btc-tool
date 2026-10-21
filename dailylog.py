"""PERMANENT daily archive: one row per IST day (00:00-24:00 IST), saved forever in daily_history.json (+ a CSV copy for Excel / for sending to Claude).
A day that is finished (24 candles) is FROZEN: never changed or deleted. Today's row is refreshed every scan until the day ends.
First run back-fills up to a year from OKX 1H history (free public data), so analysis is possible from day one.
Extra fields kept for later analysis: UP/DOWN day, IST hour of the day's high and low, range of each session (Asia/Europe/US/Late),
biggest 1H candle, volume, and what the paper tool itself did that day (trades closed, net INR). Nothing here is a prediction."""
import os, json, csv, datetime as dt
import numpy as np, pandas as pd

FILE = "daily_history.json"; CSVF = "daily_history.csv"; IST = pd.Timedelta(hours=5, minutes=30)
SESS = [("asia", 0, 8), ("europe", 8, 13), ("us", 13, 21), ("late", 21, 24)]            # UTC hours (same as timing.py)
WD = ["Somvar (Mon)", "Mangalvar (Tue)", "Budhvar (Wed)", "Guruvar (Thu)", "Shukravar (Fri)", "Shanivar (Sat)", "Ravivar (Sun)"]
COLS = ["day", "weekday", "open", "high", "low", "close", "up", "dn", "rng", "up_pct", "dn_pct", "rng_pct", "chg", "chg_pct", "direction", "high_hr_ist", "low_hr_ist",
        "rng_asia", "rng_europe", "rng_us", "rng_late", "max_1h_rng", "volume", "bars", "final", "paper_trades", "paper_pnl_inr", "src", "saved_at"]


def load():
    try:
        a = json.load(open(FILE)); a.setdefault("days", {}); a.setdefault("meta", {}); return a
    except Exception: return dict(days={}, meta={})


def compute(h1, now):
    """All IST days found in the 1H candle frame -> list of rows."""
    d = h1.copy(); d["ist"] = pd.to_datetime(d.ts, unit="ms", utc=True) + IST; d["day"] = d.ist.dt.strftime("%Y-%m-%d"); d["uh"] = ((d.ts // 3600000) % 24).astype(int)
    today = (now + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d"); rows = []
    for day, g in d.groupby("day", sort=True):
        g = g.sort_values("ts"); o, hi, lo, c = float(g.o.iloc[0]), float(g.h.max()), float(g.l.min()), float(g.c.iloc[-1]); n = len(g)
        hh = int(g.loc[g.h.idxmax(), "ist"].hour); lh = int(g.loc[g.l.idxmin(), "ist"].hour); sess = {}
        for nm, a, b in SESS:
            s = g[(g.uh >= a) & (g.uh < b)]; sess["rng_" + nm] = round(float(s.h.max() - s.l.min()), 1) if len(s) else None
        chg = c - o; rows.append(dict(day=day, weekday=pd.Timestamp(day).weekday(), open=round(o, 1), high=round(hi, 1), low=round(lo, 1), close=round(c, 1), up=round(hi - o, 1), dn=round(o - lo, 1), rng=round(hi - lo, 1),
                                      up_pct=round((hi - o) / o * 100, 2), dn_pct=round((o - lo) / o * 100, 2), rng_pct=round((hi - lo) / o * 100, 2), chg=round(chg, 1), chg_pct=round(chg / o * 100, 2),
                                      direction="UP" if chg > 0.0005 * o else "DOWN" if chg < -0.0005 * o else "FLAT", high_hr_ist=hh, low_hr_ist=lh, **sess, max_1h_rng=round(float((g.h - g.l).max()), 1), volume=round(float(g.v.sum()), 1),
                                      bars=int(n), final=bool(n >= 24 and day != today)))
    return rows


def paper_by_day(S):
    """Closed paper trades grouped by IST close day -> {day: (count, net_inr)}."""
    out = {}
    for t in ((S or {}).get("paper") or {}).get("closed", []):
        try:
            day = (dt.datetime.fromisoformat(t["closed"]) + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d"); n, p = out.get(day, (0, 0.0)); out[day] = (n + 1, p + float(t.get("pnl_inr") or 0))
        except Exception: pass
    return out


def save(arc):
    tmp = FILE + ".tmp"; json.dump(arc, open(tmp, "w"), separators=(",", ":")); os.replace(tmp, FILE)
    rows = [arc["days"][k] for k in sorted(arc["days"])]
    with open(CSVF, "w", newline="") as f:
        w = csv.writer(f); w.writerow(COLS + ["weekday_name"])
        for r in rows: w.writerow([r.get(c, "") for c in COLS] + [WD[int(r["weekday"])]])


def update(h1, now, S=None, src="live"):
    """Add/refresh rows. A FINAL (finished) day is never overwritten. Never raises."""
    try:
        arc = load(); days = arc["days"]; stamp = now.isoformat(timespec="seconds"); changed = 0
        for r in compute(h1, now):
            old = days.get(r["day"])
            if old and old.get("final"): continue
            if old and old.get("bars", 0) > r["bars"] and not r["final"]: continue          # never replace a fuller row with a thinner one (e.g. frame only has part of that day)
            r.update(src=src if not old else old.get("src", src), saved_at=stamp, paper_trades=(old or {}).get("paper_trades", 0), paper_pnl_inr=(old or {}).get("paper_pnl_inr", 0)); days[r["day"]] = r; changed += 1
        pb = paper_by_day(S)                                                                  # the paper-tool result of a day may change after the day's candles are final: refresh last 4 days only
        for day in sorted(days)[-4:]:
            if day in pb: days[day]["paper_trades"], days[day]["paper_pnl_inr"] = pb[day][0], round(pb[day][1], 2)
        arc["meta"]["updated"] = stamp; arc["meta"]["n"] = len(days)
        if changed or not os.path.exists(CSVF): save(arc)
        return arc
    except Exception as e: print("dailylog update error", e); return load()


def backfill(now, S=None, days=365, budget_s=60):
    """Once (and again every 3 days if it came back short): pull up to a year of 1H candles from OKX and fill missing days."""
    try:
        arc = load(); fin = sum(1 for r in arc["days"].values() if r.get("final")); last = arc["meta"].get("backfill_ts")
        if fin >= days * 0.9: return arc
        if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < 3 * 86400 and fin >= 20: return arc
        import timing
        df = timing.fetch_hist(days, budget_s); arc["meta"]["backfill_ts"] = now.isoformat(timespec="seconds"); json.dump(arc, open(FILE, "w"), separators=(",", ":"))
        if len(df) >= 48: return update(df, now, S, src="backfill")
        return arc
    except Exception as e: print("dailylog backfill error", e); return load()


# ------------------------------------------------------------------ analysis
def _fin(arc): return [arc["days"][k] for k in sorted(arc["days"]) if arc["days"][k].get("final")]


def stats(arc):
    R = _fin(arc)
    if len(R) < 3: return None
    rng, up, dn, pc = (np.array([r[k] for r in R], float) for k in ("rng", "up", "dn", "rng_pct")); out = dict(n=len(R), first=R[0]["day"], last=R[-1]["day"])
    win = lambda k: dict(rng=round(float(rng[-k:].mean())), rng_pct=round(float(pc[-k:].mean()), 2), up=round(float(up[-k:].mean())), dn=round(float(dn[-k:].mean())), n=int(min(k, len(R))))
    out["w7"], out["w30"], out["w90"], out["all"] = win(7), win(30), win(90), win(len(R))
    out["median_rng"] = round(float(np.median(rng))); out["p90_rng"] = round(float(np.percentile(rng, 90))); out["p10_rng"] = round(float(np.percentile(rng, 10)))
    out["up_days_pct"] = round(float(np.mean([r["direction"] == "UP" for r in R]) * 100), 1)
    wd = {}
    for r in R: wd.setdefault(int(r["weekday"]), []).append(r)
    out["weekday"] = [dict(wd=k, name=WD[k], n=len(v), rng=round(float(np.mean([x["rng"] for x in v]))), rng_pct=round(float(np.mean([x["rng_pct"] for x in v])), 2), up_days=round(float(np.mean([x["direction"] == "UP" for x in v]) * 100))) for k, v in sorted(wd.items())]
    hh = pd.Series([r["high_hr_ist"] for r in R]).value_counts(normalize=True).head(3); lh = pd.Series([r["low_hr_ist"] for r in R]).value_counts(normalize=True).head(3)
    out["high_hours"] = [(int(h), round(float(p) * 100)) for h, p in hh.items()]; out["low_hours"] = [(int(h), round(float(p) * 100)) for h, p in lh.items()]
    ses = {}
    for nm, _, _ in SESS:
        v = [r.get("rng_" + nm) for r in R if r.get("rng_" + nm) is not None]
        if v: ses[nm] = round(float(np.mean(v)))
    out["sessions"] = ses
    if len(R) >= 30:                                                                              # volatility clustering: does a big day tend to be followed by a big day?
        thr = np.percentile(rng, 75); after_big = [R[i + 1]["rng"] for i in range(len(R) - 1) if R[i]["rng"] >= thr]; after_small = [R[i + 1]["rng"] for i in range(len(R) - 1) if R[i]["rng"] < thr]
        if len(after_big) >= 8 and len(after_small) >= 8: out["cluster"] = dict(after_big=round(float(np.mean(after_big))), after_other=round(float(np.mean(after_small))), n_big=len(after_big))
    s, best_u, best_d = 0, 0, 0
    for r in R:
        s = (s + 1 if s >= 0 else 1) if r["direction"] == "UP" else (s - 1 if s <= 0 else -1) if r["direction"] == "DOWN" else 0; best_u, best_d = max(best_u, s), max(best_d, -s)
    out["streak_up"], out["streak_down"] = best_u, best_d; big = sorted(R, key=lambda r: -r["rng"])[:3]; out["biggest"] = [(r["day"], r["rng"], r["rng_pct"], r["direction"]) for r in big]
    t = arc["days"].get(max(arc["days"])) if arc["days"] else None
    if t and not t.get("final"): out["today_rank"] = round(float((rng <= t["rng"]).mean() * 100)); out["today_rng"] = t["rng"]
    return out


def text_stats(arc):
    s = stats(arc)
    if not s: return "Daily archive mein abhi 3 se kam poore din hain. Kuch din baad analysis aayega (backfill pehle scan mein 1 saal ka data laata hai)."
    L = [f"🗂 DAILY ARCHIVE: {s['n']} poore din saved ({s['first']} se {s['last']})"]
    for k, nm in (("w7", "Pichhle 7 din"), ("w30", "Pichhle 30 din"), ("w90", "Pichhle 90 din")):
        w = s[k]
        if w["n"] >= 3: L.append(f"{nm}: average range {w['rng']:,} pts ({w['rng_pct']}%) | upar +{w['up']:,} / neeche -{w['dn']:,} pts")
    L.append(f"Saare din: median range {s['median_rng']:,} pts | chhote din (10%) {s['p10_rng']:,} ya kam | bade din (10%) {s['p90_rng']:,}+ pts | UP band hue {s['up_days_pct']}% din")
    L.append("Weekday ka average range: " + ", ".join(f"{w['name'].split(' ')[1].strip('()')} {w['rng']:,}" for w in s["weekday"]))
    L.append("Din ka high aksar IST ghante: " + ", ".join(f"{h:02d}:00 ({p}%)" for h, p in s["high_hours"]) + " | low: " + ", ".join(f"{h:02d}:00 ({p}%)" for h, p in s["low_hours"]))
    if s["sessions"]: L.append("Session ka average range (pts): " + ", ".join(f"{k} {v:,}" for k, v in s["sessions"].items()))
    if s.get("cluster"): c = s["cluster"]; L.append(f"Bade din ke baad agla din: average {c['after_big']:,} pts, baaki dinon ke baad {c['after_other']:,} pts (volatility clustering: bada din aksar bade din ke baad aata hai)" if c["after_big"] > c["after_other"] * 1.1 else f"Bade din ke baad agla din: {c['after_big']:,} pts vs baaki {c['after_other']:,} pts (koi saaf fark nahi)")
    L.append(f"Sabse bade din: " + "; ".join(f"{d[5:]} {r:,.0f} pts ({p:.1f}%, {dr})" for d, r, p, dr in s["biggest"]) + f" | sabse lambi streak: {s['streak_up']} UP din, {s['streak_down']} DOWN din")
    if s["n"] < 90: L.append(f"Dhyan: abhi sirf {s['n']} din hain. Weekday aur ghante ke pattern ke liye kam se kam 90 din chahiye, tab tak inhe pakka mat maano.")
    if s.get("today_rank") is not None: L.append(f"Aaj abhi tak range {s['today_rng']:,.0f} pts: itihaas ke {s['today_rank']}% dinon se bada ya barabar (din abhi chal raha hai).")
    return "\n".join(L)


def text_days(arc, n=14):
    rows = [arc["days"][k] for k in sorted(arc["days"])][-n:][::-1]
    if not rows: return "Daily archive abhi khaali hai (pehle scan ke baad bharega)."
    L = [f"📒 PICHHLE {len(rows)} DIN (saved, IST) | din: upar / neeche / range pts | close-open"]
    for r in rows: L.append(f"{r['day'][5:]} {WD[int(r['weekday'])].split(' ')[1].strip('()')}{' (aaj)' if not r.get('final') else ''}: +{r['up']:,.0f} / -{r['dn']:,.0f} / {r['rng']:,.0f} ({r['rng_pct']:.1f}%) | {r['chg']:+,.0f} {r['direction']}" + (f" | tool: {r['paper_trades']} trade, ₹{r['paper_pnl_inr']:+,.0f}" if r.get("paper_trades") else ""))
    return "\n".join(L)
