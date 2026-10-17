"""V10: does the MOVE RADAR really warn before big moves? For every past hour: radar score (price-only part, same code as live) vs what happened in the NEXT 6 hours.
'Big move' = price travels >= 2.5 x ATR(1H) away from the close in either direction within 6 hours.
Time classes (HIGH/MEDIUM/LOW hour) are learned on the first half; results are judged on the UNSEEN second half. Also: when the radar leans one way, how often was that the bigger side?
Verdict: USEFUL only if, at score>=65, the big-move rate beats the base rate by >=10 points with >=50 signals, on the unseen half AND on the first half."""
import sys, json, math, datetime as dt
import numpy as np
import methods as MT, moveradar as MR, timing, backtest_v5 as X

H_FWD, BIG_ATR = 6, 2.5


def run(df, cls_map):
    I = MT.prepare(df); n = I["n"]; rows = []; TS = df.ts.values
    for i in range(250, n - H_FWD - 1):
        hr = dt.datetime.fromtimestamp(TS[i] / 1000, dt.timezone.utc).hour
        s = MR.score_price(I, i, cls_map.get(hr), cls_map.get((hr + 1) % 24)) if True else None
        if not s: continue
        a = I["atr"][i]; up = float(I["h"][i + 1:i + 1 + H_FWD].max() - I["c"][i]); dn = float(I["c"][i] - I["l"][i + 1:i + 1 + H_FWD].min())
        rows.append(dict(i=i, ts=float(TS[i]), score=s["score"], lean=s["lean"], mx=max(up, dn) / a, pts=max(up, dn), bigger=1 if up > dn else -1))
    return rows


def block(rows, lo, hi):
    r = [x for x in rows if lo <= x["score"] < hi]
    if not r: return dict(n=0)
    big = np.array([x["mx"] >= BIG_ATR for x in r]); L = [x for x in r if x["lean"] != 0]
    return dict(n=len(r), big_rate=round(float(big.mean()) * 100, 1), avg_move_atr=round(float(np.mean([x["mx"] for x in r])), 2), avg_move_pts=round(float(np.mean([x["pts"] for x in r]))),
                lean_n=len(L), lean_right_pct=round(float(np.mean([x["lean"] == x["bigger"] for x in L])) * 100, 1) if L else None)


def main(days=2000):
    df = X.hist1h(days); half = len(df) // 2; T = timing.build(df.iloc[:half]); cls = {r["hr"]: r["cls"] for r in T["hours"]}; rows = run(df, cls); hts = float(df.ts.iloc[half])
    out = dict(rows=len(df), forward_hours=H_FWD, big_move_atr=BIG_ATR, buckets={})
    for nm, rs in (("unseen_second_half", [r for r in rows if r["ts"] >= hts]), ("first_half", [r for r in rows if r["ts"] < hts])):
        out["buckets"][nm] = {"all_hours": block(rs, 0, 101), "score_0_44": block(rs, 0, 45), "score_45_64": block(rs, 45, 65), "score_65_plus": block(rs, 65, 101), "score_75_plus": block(rs, 75, 101)}
    a, b = out["buckets"]["unseen_second_half"], out["buckets"]["first_half"]
    ok = lambda d: d["score_65_plus"].get("n", 0) >= 50 and d["score_65_plus"]["big_rate"] - d["all_hours"]["big_rate"] >= 10
    out["verdict"] = "USEFUL (still just probability)" if ok(a) and ok(b) else "NOT PROVEN" if a["score_65_plus"].get("n", 0) >= 50 else "TOO FEW SIGNALS"
    json.dump(out, open("backtest_v10_results.json", "w"), indent=1); print(json.dumps(out["verdict"]), json.dumps(a)); return out


if __name__ == "__main__": main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
