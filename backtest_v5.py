"""V5: robustness test of trend_pullback on ~5.5y of 1H data.
Trades older than 730d were NOT used to pick the config in V4, so they are genuine out-of-sample."""
import os, sys, json, time, requests, numpy as np, pandas as pd
import engine as E, backtest_v3 as V, backtest_v4 as W

def hist1h(days):
    out, after = [], ""
    while len(out) < days * 24:
        q = dict(instId=E.INST, bar="1H", limit=100)
        if after: q["after"] = after
        try: d = E._get("market/history-candles", **q)
        except Exception as e: print("fetch stopped:", e); break
        if not d: break
        out += d; after = d[-1][0]; time.sleep(0.12)
    df = pd.DataFrame([x[:6] for x in out], columns=["ts", "o", "h", "l", "c", "v"]).astype(float)
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)

def analyze(raw):
    h1 = W.prep(raw); M = {x: h1[x].values for x in ("h", "l", "c")}
    S = {n: [] for n in ("trend_pullback", "breakout_retest", "squeeze_breakout", "slow_trend")}
    W.side_sigs(h1, 1, S); W.side_sigs(h1, -1, S)
    T, last = [], -99
    for i, k in sorted(S["trend_pullback"]):
        if i >= last + 24 and i < len(h1) - 170 and h1.atr.iloc[i] == h1.atr.iloc[i]:
            T.append(dict(i=i, side=k, e=M["c"][i], a=float(h1.atr.iloc[i]))); last = i
    idx = [t["i"] for t in T]; ts = h1.ts.values[idx]; yr = pd.to_datetime(ts, unit="ms").year.values
    side = np.array([t["side"] for t in T]); fresh = ts < h1.ts.values[-1] - 730 * 86400000
    R = lambda c: np.array([V.sim(M, t, c[0] * t["a"], c[1], c[2]) for t in T])
    rows = []
    for c in [(k, m, H) for k in (2, 3, 4) for m in (3, 4, 5) for H in (72, 120, 168)]:
        r = R(c); rows.append(dict(cfg=str(c), all=V.st(r), fresh_oos=V.st(r[fresh]), last2y=V.st(r[~fresh])))
    cen = (3, 4, 120); rc = R(cen); V.COST = 0.002; rc2 = R(cen); V.COST = 0.0010
    by_year = {int(y): V.st(rc[yr == y]) for y in sorted(set(yr))}
    f = V.st(rc[fresh]); g = lambda d: d.get("mean_R", -9)
    pos_grid = float(np.mean([g(r["fresh_oos"]) > 0 for r in rows])); yrs = [v for v in by_year.values() if v["n"] >= 10]
    pos_years = float(np.mean([g(v) > 0 for v in yrs])) if yrs else 0.0
    if f.get("n", 0) >= 100 and g(f) - 1.64 * f.get("se", 9) > 0 and pos_grid >= 0.7 and pos_years >= 0.6: v = "ROBUST CANDIDATE - move to paper-trading"
    elif f.get("n", 0) >= 60 and g(f) - f.get("se", 9) > 0 and pos_grid >= 0.6: v = "PROMISING BUT NOT PROVEN - paper-trade and keep collecting data"
    else: v = "NOT SUPPORTED - treat the V4 result as luck"
    return dict(note="Central cfg (stop 3xATR1h, target 4R, 120 bars). fresh_oos = trades older than 730d (never used for selection). 0.10% cost.",
                verdict=v, trades=len(T), central_fresh_oos=f, central_last2y=V.st(rc[~fresh]), central_all=V.st(rc),
                fresh_long=V.st(rc[fresh & (side == 1)]), fresh_short=V.st(rc[fresh & (side == -1)]), cost_doubled_all=V.st(rc2),
                share_of_grid_positive_fresh=round(pos_grid, 2), share_of_years_positive=round(pos_years, 2), by_year=by_year, grid=rows)

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    res = analyze(hist1h(days)); json.dump(res, open("backtest_v5_results.json", "w"), indent=1); print(json.dumps(res, indent=1))
    if os.environ.get("TG_TOKEN"):
        f = res["central_fresh_oos"]; msg = (f"V5 robustness ({days}d), {res['trades']} trades\nFresh OOS: {f.get('mean_R')}R (n={f.get('n')}, se {f.get('se')})\n"
               f"Last 2y: {res['central_last2y'].get('mean_R')}R | cost x2: {res['cost_doubled_all'].get('mean_R')}R\n"
               f"Grid positive: {res['share_of_grid_positive_fresh']*100:.0f}% | Years positive: {res['share_of_years_positive']*100:.0f}%\nVerdict: {res['verdict']}")
        requests.post(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage", json=dict(chat_id=os.environ["TG_CHAT_ID"], text=msg), timeout=20)
