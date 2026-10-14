"""V8: does the Session Breakout strategy work, and does the time-of-day filter help?
Uses the SAME function the live bot uses (strategies.session_breakout) and the SAME exit code (lifecycle.advance), fees included.
Time classes (HIGH/MEDIUM/LOW hour) are learned on the FIRST half of history and the strategy is judged on the SECOND half only (no peeking).
Verdict is strict: needs mean R > 0 at 95% one-sided on the unseen half, and both long and short not clearly negative."""
import sys, json, math, collections, datetime as dt
import numpy as np
import lifecycle, strategies as ST, timing, config, backtest_v4 as W, backtest_v5 as X

FEE = 0.0005; Bar = collections.namedtuple("Bar", "h l")


def run(df, variant, cls_map, start_i, sc):
    h1 = W.prep(df); H, L, Cc, TS = h1.h.values, h1.l.values, h1.c.values, h1.ts.values; out, busy = [], -1
    for i in range(max(start_i, 800), len(h1) - 30):
        if i <= busy: continue
        hr = dt.datetime.fromtimestamp(TS[i] / 1000, dt.timezone.utc).hour; nxt = (hr + 1) % 24; cls = cls_map.get(nxt)
        if variant == "high_only" and cls != "HIGH": continue
        if variant == "no_low" and cls == "LOW": continue
        now = dt.datetime.fromtimestamp(TS[i] / 1000 + 3600 + 300, dt.timezone.utc)
        sg = ST.session_breakout(dict(h1=h1.iloc[:i + 2], i=i, S={"market": {}}, now=now, tcls=cls if variant != "all" else None), sc)
        if not sg: continue
        k, e = sg["side"], sg["entry"]; t = lifecycle.new_state(k, e, sg["sl"], "fixed", tp=sg["tp"]); ex = []
        for j in range(i + 1, i + int(sc["expiry_hours"]) + 1):
            ex += lifecycle.advance(t, Bar(H[j], L[j]))
            if t["remaining"] <= 1e-9: break
        if t["remaining"] > 1e-9: ex.append(("EXPIRED", Cc[j], t["remaining"])); j = j
        out.append(dict(i=i, side=k, R=lifecycle.trade_R(ex, e, k, sg["risk"], FEE), ts=float(TS[i]))); busy = j + int(sc.get("cooldown_hours", 6)) - 1
    return out


def stat(rows):
    R = np.array([r["R"] for r in rows]); n = len(R)
    if n < 2: return dict(n=n)
    m, se = float(R.mean()), float(R.std(ddof=1) / math.sqrt(n))
    return dict(n=n, win_pct=round(float((R > 0).mean() * 100), 1), mean_R=round(m, 3), se=round(se, 3), lo95=round(m - 1.645 * se, 3), sum_R=round(float(R.sum()), 1))


def main(days=2000):
    df = X.hist1h(days); half = len(df) // 2; T = timing.build(df.iloc[:half]); cls_map = {r["hr"]: r["cls"] for r in T["hours"]}
    sc = config.load()["strategies"]["session_breakout"]; res = dict(rows=len(df), split_ts=float(df.ts.iloc[half]), classes_from="first half", variants={})
    for v in ("all", "no_low", "high_only"):
        tr = run(df, v, cls_map, half, sc)                      # unseen half only
        res["variants"][v] = dict(test=stat(tr), long=stat([r for r in tr if r["side"] == 1]), short=stat([r for r in tr if r["side"] == -1]))
    b = res["variants"]["no_low"]["test"]
    res["verdict"] = ("PROMISING (still paper-trade first)" if b.get("n", 0) >= 30 and b.get("lo95", -9) > 0 else "NOT PROVEN" if b.get("n", 0) >= 30 else "TOO FEW TRADES")
    json.dump(res, open("backtest_v8_results.json", "w"), indent=1); print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__": main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
