"""V6: which EXIT style works best on the trend_pullback entries? Same entries for every style, fees included (per side, like live).
Live-supported styles run through lifecycle.advance, the SAME code the paper wallet uses, so the test means what live does.
Trailing styles are research-only (not available live). Fresh out-of-sample = trades older than 730 days."""
import os, sys, json, collections, requests, numpy as np
import lifecycle, backtest_v4 as W, backtest_v5 as X

FEE = 0.0005                                     # per side (config wallet.fee_rate_per_side)
Bar = collections.namedtuple("Bar", "h l")
STYLES = {"fixed_4R (live default)": dict(mode="fixed", tgt=4), "fixed_2R": dict(mode="fixed", tgt=2),
          "staged: 50% at 1.5R, rest 4R (early-signal style)": dict(mode="staged", t1=1.5, t2=4), "staged: 50% at 2R, rest 6R": dict(mode="staged", t1=2, t2=6),
          "late_entry_6h_fixed_4R": dict(mode="fixed", tgt=4, delay=6),
          "atr_trail_3x (research only)": dict(trail="atr"), "structure_trail (research only)": dict(trail="struct")}

def sim_exit(M, i, k, a, S, H=120):
    """Walk the bars after entry with lifecycle.advance (stop checked first) and return net R after fees."""
    j0 = i + S.get("delay", 0); e = M["c"][j0]; risk = 3 * a; g = lambda m: e + k * S.get(m, 0) * risk
    t = lifecycle.new_state(k, e, e - k * risk, S["mode"], tp=g("tgt"), t1=g("t1"), t2=g("t2"), partial=0.5); exits = []
    for j in range(j0 + 1, j0 + H + 1):
        exits += lifecycle.advance(t, Bar(M["h"][j], M["l"][j]))
        if t["remaining"] <= 1e-9: break
    if t["remaining"] > 1e-9: exits.append(("EXPIRED", M["c"][j0 + H], t["remaining"]))
    return lifecycle.trade_R(exits, e, k, risk, FEE)

def sim_trail(M, i, k, a, S, H=120):
    hi, lo, cl = (M["h"], M["l"], M["c"]) if k == 1 else (-M["l"], -M["h"], -M["c"]); e = cl[i]; risk = 3 * a; sl = e - risk; hc = e
    cost = 2 * FEE * abs(M["c"][i]) / risk
    for j in range(i + 1, i + H + 1):
        if lo[j] <= sl: return (sl - e) / risk - cost
        hc = max(hc, cl[j])
        if S["trail"] == "atr": sl = max(sl, hc - 3 * a)
        elif hc - e >= risk: sl = max(sl, lo[j - 11:j + 1].min() - 0.2 * a)
    return (cl[i + H] - e) / risk - cost

def trades(h1):
    S = {n: [] for n in ("trend_pullback", "breakout_retest", "squeeze_breakout", "slow_trend")}; W.side_sigs(h1, 1, S); W.side_sigs(h1, -1, S); T, last = [], -99
    for i, k in sorted(S["trend_pullback"]):
        if i >= last + 24 and i < len(h1) - 135 and h1.atr.iloc[i] == h1.atr.iloc[i]: T.append((i, k, float(h1.atr.iloc[i]))); last = i
    return T

def st(r):
    if len(r) < 2: return {"n": len(r)}
    cum = np.cumsum(r); dd = float((np.maximum.accumulate(cum) - cum).max())
    return {"n": len(r), "mean_R": round(float(r.mean()), 3), "win_%": round(float((r > 0).mean() * 100), 1), "se": round(float(r.std() / np.sqrt(len(r))), 3), "max_drawdown_R": round(dd, 1)}

def analyze(raw):
    h1 = W.prep(raw); M = {x: h1[x].values for x in ("h", "l", "c")}; T = trades(h1); ts = h1.ts.values[[t[0] for t in T]]; fresh = ts < h1.ts.values[-1] - 730 * 86400000
    R = {n: np.array([(sim_trail if "trail" in P else sim_exit)(M, i, k, a, P) for i, k, a in T]) for n, P in STYLES.items()}; base = R["fixed_4R (live default)"]; rows = {}
    for n, r in R.items():
        d = (r - base)[fresh]; se = float(d.std() / np.sqrt(len(d))) if len(d) > 1 else 9.0; dm = float(d.mean()) if len(d) else 0.0
        rows[n] = dict(all=st(r), fresh_oos=st(r[fresh]), last2y=st(r[~fresh]), vs_current_fresh=dict(diff_R=round(dm, 3), se=round(se, 3), better=bool(n != "fixed_4R (live default)" and dm - 1.64 * se > 0)))
    win = [n for n, v in rows.items() if v["vs_current_fresh"]["better"]]
    verdict = ("IMPROVEMENT FOUND: " + ", ".join(win) + " (still needs paper-trade confirmation)") if win else "NO EXIT STYLE IS CLEARLY BETTER than the live fixed 4R rule"
    return dict(note="Same entries, per-side fee 0.05%. 7 styles tried, so only a clear paired improvement counts. R = units of risk.", trades=len(T), verdict=verdict, policies=rows)

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    res = analyze(X.hist1h(days)); json.dump(res, open("backtest_v6_results.json", "w"), indent=1); print(json.dumps(res, indent=1)[:2500])
    if os.environ.get("TG_TOKEN"):
        L = [f"{n}: fresh {v['fresh_oos'].get('mean_R')}R, win {v['fresh_oos'].get('win_%')}%, maxDD {v['fresh_oos'].get('max_drawdown_R')}R" for n, v in res["policies"].items()]
        requests.post(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage", json=dict(chat_id=os.environ["TG_CHAT_ID"], text=f"V6 exit-style test ({res['trades']} trades)\n" + "\n".join(L) + f"\nVerdict: {res['verdict']}"), timeout=20)
