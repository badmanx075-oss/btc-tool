"""V11: does the ANALOG (nearest-neighbour) engine have a real edge? Walk-forward over the whole history: at every hour the engine only sees the PAST
(library = bars that finished at least 24h earlier), finds the 150 most similar past hours, and the 'analog_edge' strategy trades only when the 4h lean is clear
(P(up) >= 58% with 95% lower bound >= 50%, or the mirror for shorts). Same trade simulator, fees and exit rules as the live bot (lifecycle.advance), one trade at a time.
Also reports the engine's own accuracy on unseen data (direction hit-rate, Brier score vs coin-flip, range predictability vs plain ATR).
Verdict: needs >=30 trades, mean R > 0 at 95% one-sided, AND both halves positive. Nothing is fitted on the test part."""
import sys, json, math, collections, datetime as dt
import numpy as np
import lifecycle, strategies as ST, methods as MT, analog as AN, config, backtest_v5 as X

FEE = 0.0005; Bar = collections.namedtuple("Bar", "h l")


def run(df, I, F, T, sc, start_frac=0.3):
    n = len(df); t0 = int(n * start_frac); mu = np.nanmean(F[AN.WARM:t0], axis=0); sd = np.nanstd(F[AN.WARM:t0], axis=0) + 1e-9; Z = AN.zscore(F, mu, sd); okf = ~np.isnan(Z).any(axis=1); ok4 = ~np.isnan(T[:, 1, 0])
    H, L, Cc, TS = df.h.values, df.l.values, df.c.values, df.ts.values; out, busy, sig_n, exp = [], -1, 0, int(sc["expiry_hours"])
    for i in range(t0, n - exp - 2):
        if i <= busy or not okf[i]: continue
        idx = np.where(okf[:i - 23] & ok4[:i - 23])[0]
        if len(idx) < 400: continue
        nb = AN.nearest(Z, idx, Z[i]); st = AN.horizon_stats(T, nb, 1, float((T[idx, 1, 0] > 0).mean())); s = AN.signal(st)
        if not s: continue
        sig_n += 1; now = dt.datetime.fromtimestamp(TS[i] / 1000 + 3600 + 300, dt.timezone.utc)
        sg = ST.analog_edge(dict(h1=df, i=i, S={"market": {}}, now=now, tcls=None, mI=I, analog=dict(signal=s, p4=st["p_up"])), dict(sc, require_validated=False))
        if not sg: continue
        k, e = sg["side"], sg["entry"]; t = lifecycle.new_state(k, e, sg["sl"], "fixed", tp=sg["tp"]); ex = []; j = i
        for j in range(i + 1, i + exp + 1):
            ex += lifecycle.advance(t, Bar(H[j], L[j]))
            if t["remaining"] <= 1e-9: break
        if t["remaining"] > 1e-9: ex.append(("EXPIRED", Cc[j], t["remaining"]))
        out.append(dict(i=i, side=k, ts=float(TS[i]), R=lifecycle.trade_R(ex, e, k, sg["risk"], FEE))); busy = j + int(sc.get("cooldown_hours", 4)) - 1
    return out, sig_n


def stat(rows):
    R = np.array([r["R"] for r in rows]); n = len(R)
    if n < 2: return dict(n=n)
    m, se = float(R.mean()), float(R.std(ddof=1) / math.sqrt(n))
    return dict(n=n, win_pct=round(float((R > 0).mean() * 100), 1), mean_R=round(m, 3), se=round(se, 3), lo95=round(m - 1.645 * se, 3), sum_R=round(float(R.sum()), 1))


def main(days=2000):
    df = X.hist1h(days).reset_index(drop=True); I = MT.prepare(df); F, T = AN.features(I), AN.targets(I); sc = config.load()["strategies"]["analog_edge"]; half = df.ts.iloc[len(df) // 2]
    tr, sig_n = run(df, I, F, T, sc); years = {}
    for r in tr: years.setdefault(dt.datetime.fromtimestamp(r["ts"] / 1000).year, []).append(r)
    res = dict(rows=len(df), signals=sig_n, all=stat(tr), first_half=stat([r for r in tr if r["ts"] < half]), second_half=stat([r for r in tr if r["ts"] >= half]), long=stat([r for r in tr if r["side"] == 1]),
               short=stat([r for r in tr if r["side"] == -1]), by_year={str(y): stat(v) for y, v in sorted(years.items())}, engine_check=AN._validate(F, T, I))
    a, h1_, h2 = res["all"], res["first_half"], res["second_half"]
    res["verdict"] = ("PROMISING (still paper-trade first)" if a.get("n", 0) >= 30 and a.get("lo95", -9) > 0 and h1_.get("mean_R", -9) > 0 and h2.get("mean_R", -9) > 0 else "NOT PROVEN" if a.get("n", 0) >= 30 else "TOO FEW TRADES")
    json.dump(res, open("backtest_v11_results.json", "w"), indent=1); print(json.dumps({k: res[k] for k in ("rows", "signals", "verdict", "all", "engine_check")})); return res


if __name__ == "__main__": main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
