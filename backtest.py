"""V2 backtest: replays the live engine on history, measures what happened after each signal (48h horizon)."""
import os, sys, json, time, requests, numpy as np, pandas as pd
import engine as E

def hist(days):
    out, after = [], ""
    while len(out) < days * 96:
        q = dict(instId=E.INST, bar="15m", limit=100)
        if after: q["after"] = after
        try: d = E._get("market/history-candles", **q)
        except Exception as e: print("fetch stopped:", e); break
        if not d: break
        out += d; after = d[-1][0]; time.sleep(0.12)
    df = pd.DataFrame([x[:6] for x in out], columns=["ts", "o", "h", "l", "c", "v"]).astype(float)
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)

def rs(df, rule):
    x = df.copy(); x.index = pd.to_datetime(x.ts, unit="ms")
    r = x.resample(rule).agg({"ts": "first", "o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}).dropna()
    return r.reset_index(drop=True)

def run(m15):
    h1, h4, rows, i = rs(m15, "1h"), rs(m15, "4h"), [], 700
    while i < len(m15) - 200:
        tc = m15.ts.iloc[i] + 900000
        a1, a4 = h1[h1.ts + 3600000 <= tc].tail(60), h4[h4.ts + 14400000 <= tc].tail(60)
        r = E.scan(m15.iloc[i - 300:i + 1], a4, a1)
        if r["signal"] == "NO TRADE": i += 1; continue
        k, e = (1 if r["side"] == "LONG" else -1), r["entry"]; f = m15.iloc[i + 1:i + 193]
        fa = ((f.h - e) if k == 1 else (e - f.l)).values; ad = ((e - f.l) if k == 1 else (f.h - e)).values
        risk = abs(e - r["sl"]); sl_i = int(np.argmax(ad >= risk)) if (ad >= risk).any() else 10**9
        hit = lambda x: bool((fa >= x).any() and int(np.argmax(fa >= x)) < sl_i)
        end = min(sl_i + 1, len(fa))
        rows.append(dict(side=r["side"], score=r["score"], regime=r["regime"], sl=sl_i < 10**9, mfe=fa[:end].max(), mae=ad[:end].max(),
                         t1=hit(abs(r["t1"] - e)), t2=hit(abs(r["t2"] - e)), t3=hit(abs(r["t3"] - e)),
                         **{f"p{x}": hit(x) for x in (500, 1000, 2000, 5000)}))
        i += 16  # skip 4h after a signal: no overlapping duplicates
    return pd.DataFrame(rows)

def summ(g):
    if len(g) == 0: return {"n": 0}
    o = {"n": len(g), "stop_hit_%": round(g.sl.mean() * 100, 1), "median_MFE_pts": round(g.mfe.median()), "median_MAE_pts": round(g.mae.median())}
    for c in ("t1", "t2", "t3", "p500", "p1000", "p2000", "p5000"): o[c + "_before_stop_%"] = round(g[c].mean() * 100, 1)
    return o

def report(df):
    o = {"note": "48h horizon, stop = engine SL, point targets counted only if reached BEFORE stop. Small n = low confidence. Past results are not a guarantee.",
         "all": summ(df), "long": summ(df[df.side == "LONG"]), "short": summ(df[df.side == "SHORT"]),
         "score_60_64": summ(df[df.score < 65]), "score_65_79": summ(df[(df.score >= 65) & (df.score < 80)]), "score_80_plus": summ(df[df.score >= 80])}
    o["by_regime"] = {k: summ(g) for k, g in df.groupby("regime")}
    return o

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    df = run(hist(days)); res = report(df)
    json.dump(res, open("backtest_results.json", "w"), indent=1); print(json.dumps(res, indent=1))
    if os.environ.get("TG_TOKEN"):
        a = res["all"]; msg = f"Backtest done ({days}d)\nSignals: {a['n']}\nStop hit: {a.get('stop_hit_%')}%\nT1 before stop: {a.get('t1_before_stop_%')}%\nT2: {a.get('t2_before_stop_%')}%\nT3: {a.get('t3_before_stop_%')}%\n+1000pts: {a.get('p1000_before_stop_%')}%  +2000pts: {a.get('p2000_before_stop_%')}%\nFull details on dashboard."
        requests.post(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage", json=dict(chat_id=os.environ["TG_CHAT_ID"], text=msg), timeout=20)
