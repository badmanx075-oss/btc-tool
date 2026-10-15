"""V9: does the multi-method CONFLUENCE strategy work? Uses the SAME functions as the live bot (methods.votes/consensus, strategies.confluence,
lifecycle.advance), fees included, one trade at a time + cooldown. Nothing is fitted: three fixed strictness levels (need 3/4/5 methods agreeing)
are shown for the whole history, each half, each year, and long/short separately.
Verdict (for need=4): needs >=30 trades, mean R > 0 at 95% one-sided, AND both halves positive."""
import sys, json, math, collections, datetime as dt
import numpy as np
import lifecycle, strategies as ST, methods as MT, config, backtest_v5 as X

FEE = 0.0005; Bar = collections.namedtuple("Bar", "h l")


def run(df, I, need, sc0):
    sc = dict(sc0, need=need); H, L, Cc, TS = df.h.values, df.l.values, df.c.values, df.ts.values; out, busy = [], -1; N = len(df)
    for i in range(250, N - int(sc["expiry_hours"]) - 2):
        if i <= busy: continue
        now = dt.datetime.fromtimestamp(TS[i] / 1000 + 3600 + 300, dt.timezone.utc)
        sg = ST.confluence(dict(h1=df, i=i, S={"market": {}}, now=now, tcls=None, mI=I), sc)
        if not sg: continue
        k, e = sg["side"], sg["entry"]; t = lifecycle.new_state(k, e, sg["sl"], "fixed", tp=sg["tp"]); ex = []; j = i
        for j in range(i + 1, i + int(sc["expiry_hours"]) + 1):
            ex += lifecycle.advance(t, Bar(H[j], L[j]))
            if t["remaining"] <= 1e-9: break
        if t["remaining"] > 1e-9: ex.append(("EXPIRED", Cc[j], t["remaining"]))
        out.append(dict(i=i, side=k, ts=float(TS[i]), R=lifecycle.trade_R(ex, e, k, sg["risk"], FEE))); busy = j + int(sc.get("cooldown_hours", 12)) - 1
    return out


def stat(rows):
    R = np.array([r["R"] for r in rows]); n = len(R)
    if n < 2: return dict(n=n)
    m, se = float(R.mean()), float(R.std(ddof=1) / math.sqrt(n))
    return dict(n=n, win_pct=round(float((R > 0).mean() * 100), 1), mean_R=round(m, 3), se=round(se, 3), lo95=round(m - 1.645 * se, 3), sum_R=round(float(R.sum()), 1))


def main(days=2000):
    df = X.hist1h(days); I = MT.prepare(df); sc0 = config.load()["strategies"]["confluence"]; half = df.ts.iloc[len(df) // 2]; res = dict(rows=len(df), variants={})
    for need in (3, 4, 5):
        tr = run(df, I, need, sc0); years = {}
        for r in tr: years.setdefault(dt.datetime.fromtimestamp(r["ts"] / 1000).year, []).append(r)
        res["variants"][f"need_{need}"] = dict(all=stat(tr), first_half=stat([r for r in tr if r["ts"] < half]), second_half=stat([r for r in tr if r["ts"] >= half]),
                                               long=stat([r for r in tr if r["side"] == 1]), short=stat([r for r in tr if r["side"] == -1]), by_year={str(y): stat(v) for y, v in sorted(years.items())})
    v = res["variants"]["need_4"]; a, h1_, h2 = v["all"], v["first_half"], v["second_half"]
    res["verdict"] = ("PROMISING (still paper-trade first)" if a.get("n", 0) >= 30 and a.get("lo95", -9) > 0 and h1_.get("mean_R", -9) > 0 and h2.get("mean_R", -9) > 0
                      else "NOT PROVEN" if a.get("n", 0) >= 30 else "TOO FEW TRADES")
    json.dump(res, open("backtest_v9_results.json", "w"), indent=1); print(json.dumps({k: res[k] for k in ("rows", "verdict")}), {k: v_["all"] for k, v_ in res["variants"].items()}); return res


if __name__ == "__main__": main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
