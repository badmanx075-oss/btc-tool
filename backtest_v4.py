"""V4: other strategy families on 1H/4H, up to 2y data. Verdict needs train>0, test>0 (95% one-sided) AND >=3 of 4 time chunks positive."""
import os, sys, json, requests, numpy as np, pandas as pd
import engine as E, backtest as B, backtest_v3 as V

def prep(m15):
    h1, h4 = B.rs(m15, "1h"), B.rs(m15, "4h"); h1["atr"] = E.atr_series(h1)
    net = h4.c - h4.c.shift(30); h4["er"] = net.abs() / h4.c.diff().abs().rolling(30).sum(); h4["dir"] = np.sign(net)
    idx = np.searchsorted(h4.ts.values + 14400000, h1.ts.values + 3600000, side="right") - 1; j = np.clip(idx, 0, None)
    h1["er4"] = np.where(idx >= 0, h4.er.values[j], np.nan); h1["dir4"] = np.where(idx >= 0, h4.dir.values[j], 0)
    h1["ret30d"] = h1.c / h1.c.shift(720) - 1
    return h1

def side_sigs(h1, k, S):  # short = same logic on mirrored prices
    c, o = k * h1.c.values, k * h1.o.values
    hi, lo = (h1.h.values, h1.l.values) if k == 1 else (-h1.l.values, -h1.h.values)
    a, d4, e4, r30 = h1.atr.values, h1.dir4.values * k, h1.er4.values, h1.ret30d.values * k
    P = pd.Series
    hh24, ll24 = P(hi).rolling(24).max().values, P(lo).rolling(24).min().values
    hh48, ph24 = P(hi).shift(1).rolling(48).max().values, P(hi).shift(1).rolling(24).max().values
    comp = (h1.atr / h1.atr.rolling(100).mean()).values
    for i in range(800, len(c) - 130):
        if a[i] != a[i] or e4[i] != e4[i]: continue
        up = d4[i] > 0 and e4[i] > 0.3
        if up and hh24[i] - c[i] >= 1.5 * a[i] and c[i] > ll24[i] + 0.5 * a[i] and c[i] > o[i]: S["trend_pullback"].append((i, k))
        if up:
            for j in range(1, 9):
                if c[i - j] > hh48[i - j]:
                    lvl = hh48[i - j]
                    if lo[i] <= lvl + 0.2 * a[i] and c[i] > lvl and c[i] > o[i]: S["breakout_retest"].append((i, k))
                    break
        if comp[i] < 0.7 and c[i] > ph24[i]: S["squeeze_breakout"].append((i, k))
        if i % 24 == 0 and r30[i] > 0.08 and d4[i] > 0: S["slow_trend"].append((i, k))

def run_strat(M, h1, name, sigs, cfgs):
    S, last = [], -99
    for i, k in sigs:
        if i >= last + 24 and h1.atr.iloc[i] == h1.atr.iloc[i]: S.append(dict(i=i, side=k, e=M["c"][i], a=float(h1.atr.iloc[i]))); last = i
    out = []
    for c in cfgs:
        r = np.array([V.sim(M, s, c[0] * s["a"], c[1], c[2]) for s in S])
        if len(r) < 20: continue
        cut = int(len(r) * 0.6)
        out.append(dict(strategy=name, cfg=str(c), n=len(r), train=V.st(r[:cut]), test=V.st(r[cut:]), chunks=[round(float(x.mean()), 3) for x in np.array_split(r, 4)]))
    return out

def ok(r):
    t = r["test"]
    return r["n"] >= 80 and r["train"].get("mean_R", -9) > 0.05 and t.get("mean_R", -9) > 0.05 and t["mean_R"] - 1.64 * t["se"] > 0 and sum(x > 0 for x in r["chunks"]) >= 3

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 730
    h1 = prep(B.hist(days)); M = {x: h1[x].values for x in ("h", "l", "c")}
    S = {n: [] for n in ("trend_pullback", "breakout_retest", "squeeze_breakout", "slow_trend")}
    side_sigs(h1, 1, S); side_sigs(h1, -1, S)
    cfgs = [(k, m, H) for k in (1.5, 3) for m in (2, 4) for H in (48, 120)]
    rows = []
    for n, v in S.items(): rows += run_strat(M, h1, n, sorted(v), cfgs)
    passed = [r for r in rows if ok(r)]
    best = {n: max([r for r in rows if r["strategy"] == n], key=lambda r: r["test"].get("mean_R", -9), default=None) for n in S}
    res = dict(note=f"{days}d of 1H data, 0.10% cost, 24-bar cooldown. 24 configs tried, so a pass is only a CANDIDATE for paper-trading.",
               verdict=f"{len(passed)} CANDIDATE(S) PASSED" if passed else "NO STRATEGY PASSED", passed=passed, best_per_strategy=best)
    json.dump(res, open("backtest_v4_results.json", "w"), indent=1); print(json.dumps(res, indent=1))
    if os.environ.get("TG_TOKEN"):
        lines = [f"{n}: best {b['cfg']} test {b['test'].get('mean_R')}R n={b['n']} chunks {b['chunks']}" for n, b in best.items() if b]
        requests.post(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage", json=dict(chat_id=os.environ["TG_CHAT_ID"], text=f"V4 backtest ({days}d)\n" + "\n".join(lines) + f"\nVerdict: {res['verdict']}"), timeout=20)
