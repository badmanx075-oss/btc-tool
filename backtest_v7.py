"""V7: full scorecard of the live strategy (trend_pullback entries) for spec section 33.
Same entries and risk (stop = 3 x ATR1h) as V6. Measures, over a 120-hour window after each entry:
 - hit rate of each target (in R) BEFORE the stop, and how many hours it took (median)
 - stop-hit / false-signal rate, expiry rate
 - max favourable / adverse excursion (R and points), and how often price travelled 500/1000/2000/5000/10000 points
 - the four ways to trade it: EARLY+HOLD, EARLY+PARTIAL, LATE+FIXED, LATE+TRAILING
 - early-vs-late entry delay, and splits by side, year, volatility and trend strength.
Fees 0.05% per side. R = units of risk. Honest verdict: only 'fresh' trades (older than 730 days, never used to pick the rules) count."""
import os, sys, json, numpy as np, pandas as pd
import backtest_v4 as W, backtest_v5 as X, backtest_v6 as V6

HZ = 120
TARGETS = (1, 1.5, 2, 3, 4, 5, 8)
POINTS = (500, 1000, 2000, 5000, 10000)
TNAME = {1.5: "T1 (1.5R)", 3: "T2 (3R)", 5: "T3 (5R)", 8: "Extended (8R)"}


def walk(M, i, k, a):
    """Excursions after entry at close[i]. Direction-space: favourable = in the trade direction. Stop (1R = 3 ATR) is checked first inside a bar."""
    risk = 3 * a; e = M["c"][i]; hi, lo = (M["h"], M["l"]) if k == 1 else (-M["l"], -M["h"]); ed = k * e
    j = np.arange(i + 1, i + HZ + 1); fav = (hi[j] - ed) / risk; adv = (ed - lo[j]) / risk
    sm = adv >= 1; sb = int(np.argmax(sm)) if sm.any() else None
    out = dict(risk_pts=risk, stop_bar=sb, hits={}, hours={})
    for T in TARGETS:
        tm = fav >= T; tb = int(np.argmax(tm)) if tm.any() else None
        out["hits"][T] = tb is not None and (sb is None or tb < sb)
        if out["hits"][T]: out["hours"][T] = tb + 1
    end = sb if sb is not None else HZ
    out["mfe_R"] = float(fav[:end].max()) if end > 0 else 0.0; out["mae_R"] = 1.0 if sb is not None else float(adv.max()); out["mfe_R_all"] = float(fav.max())
    return out


def blk(r):
    r = np.asarray(r, float)
    if len(r) < 2: return dict(n=int(len(r)))
    cum = np.cumsum(r); dd = float((np.maximum.accumulate(cum) - cum).max()); w, l = r[r > 0], r[r <= 0]
    return dict(n=int(len(r)), avg_R=round(float(r.mean()), 3), win_pct=round(float((r > 0).mean() * 100), 1), se=round(float(r.std() / np.sqrt(len(r))), 3),
                profit_factor=round(float(w.sum() / -l.sum()), 2) if l.sum() < 0 else None, avg_win_R=round(float(w.mean()), 2) if len(w) else 0.0, avg_loss_R=round(float(l.mean()), 2) if len(l) else 0.0, max_drawdown_R=round(dd, 1))


def analyze(raw):
    h1 = W.prep(raw); M = {x: h1[x].values for x in ("o", "h", "l", "c")}; T = V6.trades(h1)
    if len(T) < 20: return dict(error="too few trades", trades=len(T))
    idx = np.array([t[0] for t in T]); ts = h1.ts.values[idx]; fresh = ts < h1.ts.values[-1] - 730 * 86400000
    W_ = [walk(M, i, k, a) for i, k, a in T]; side = np.array([t[1] for t in T]); yr = pd.to_datetime(ts, unit="ms").year.values
    # --- target table
    tt = {}
    for T_ in TARGETS:
        hit = np.array([w["hits"][T_] for w in W_]); hrs = [w["hours"][T_] for w in W_ if T_ in w["hours"]]
        tt[str(T_)] = dict(label=TNAME.get(T_, f"{T_}R"), hit_before_stop_pct=round(float(hit.mean() * 100), 1), hit_fresh_pct=round(float(hit[fresh].mean() * 100), 1) if fresh.any() else None,
                           median_hours=round(float(np.median(hrs)), 1) if hrs else None, n_hits=int(hit.sum()))
    sbars = [w["stop_bar"] + 1 for w in W_ if w["stop_bar"] is not None]
    stop_first = np.array([w["stop_bar"] is not None and not w["hits"][1] for w in W_]); expired = np.array([w["stop_bar"] is None and not w["hits"][4] for w in W_])
    mfe, mae = np.array([w["mfe_R"] for w in W_]), np.array([w["mae_R"] for w in W_]); rp = np.array([w["risk_pts"] for w in W_])
    pct = lambda x: [round(float(np.percentile(x, q)), 2) for q in (50, 75, 90)]
    pts_tbl = {str(p): dict(reached_before_stop_pct=round(float(np.mean(mfe * rp >= p) * 100), 1), reached_any_time_pct=round(float(np.mean(np.array([w["mfe_R_all"] for w in W_]) * rp >= p) * 100), 1)) for p in POINTS}
    # --- the four ways to trade it (spec 33) and early-vs-late delay
    fixed, staged = V6.STYLES["fixed_4R (live default)"], V6.STYLES["staged: 50% at 1.5R, rest 4R (early-signal style)"]
    run = lambda S, d=0: np.array([V6.sim_exit(M, i + d, k, a, S) for i, k, a in T]); sim_t = lambda d: np.array([V6.sim_trail(M, i + d, k, a, dict(trail="atr")) for i, k, a in T])
    R_fixed = run(fixed); four = {"EARLY ENTRY + HOLD (fixed 4R)": R_fixed, "EARLY ENTRY + PARTIAL (50% at 1.5R, rest 4R)": run(staged), "LATE ENTRY (6h) + FIXED 4R": run(fixed, 6), "LATE ENTRY (6h) + ATR TRAILING": sim_t(6)}
    delay = {f"{d}h after signal": blk(run(fixed, d)) for d in (0, 3, 6, 12)}
    # --- splits (live rule = fixed 4R)
    a_ = np.array([t[2] for t in T]); volp = a_ / M["c"][idx]; q = np.percentile(volp, [33.3, 66.7]); vb = np.where(volp < q[0], "calm", np.where(volp < q[1], "normal", "wild"))
    er = h1.er4.values[idx]; qe = np.nanpercentile(er, [33.3, 66.7]); eb = np.where(er < qe[0], "weaker trend", np.where(er < qe[1], "medium trend", "strong trend"))
    split = lambda lab: {str(u): blk(R_fixed[lab == u]) for u in sorted(set(lab.tolist()))}
    f = blk(R_fixed[fresh]); pos_years = [blk(R_fixed[yr == y]) for y in sorted(set(yr.tolist()))]
    verdict = "NOT PROVEN: no statistically clear edge on unseen trades" if not (f.get("n", 0) >= 100 and f.get("avg_R", 0) - 1.64 * f.get("se", 9) > 0) else "POSSIBLE EDGE on unseen trades: keep paper-trading"
    return dict(note="Entries = live trend_pullback rule. Window 120h, stop 3xATR1h, fees 0.05%/side. fresh = older than 730 days (never used to choose the rules).", trades=len(T), verdict=verdict,
                overall=blk(R_fixed), fresh_oos=f, last2y=blk(R_fixed[~fresh]), targets=tt,
                stops=dict(stop_before_1R_pct=round(float(stop_first.mean() * 100), 1), false_signal_rate_pct=round(float(stop_first.mean() * 100), 1), stop_touched_pct=round(float(len(sbars) / len(T) * 100), 1),
                           median_hours_to_stop=round(float(np.median(sbars)), 1) if sbars else None, expired_no_result_pct=round(float(expired.mean() * 100), 1)),
                excursions=dict(mfe_R_p50_p75_p90=pct(mfe), mae_R_p50_p75_p90=pct(mae), median_risk_points=round(float(np.median(rp))), points=pts_tbl),
                four_ways={k: dict(all=blk(v), fresh=blk(v[fresh])) for k, v in four.items()}, entry_delay=delay,
                by_side={("LONG" if k == 1 else "SHORT"): blk(R_fixed[side == k]) for k in (1, -1)}, by_year={str(y): blk(R_fixed[yr == y]) for y in sorted(set(yr.tolist()))},
                by_volatility=split(vb), by_trend_strength=split(eb))


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    res = analyze(X.hist1h(days)); json.dump(res, open("backtest_v7_results.json", "w"), indent=1); print(json.dumps({k: res.get(k) for k in ("trades", "verdict", "overall", "targets", "stops")}, indent=1)[:3000])
