"""V3: tests stop/target/horizon variants + factor lift with a train/test split.
Writes params.json (used live by engine) ONLY if an edge survives on unseen test data."""
import os, sys, json, requests, numpy as np
import engine as E, backtest as B

REV = {v: k for k, v in E.TR.items()}
FACT = ["price near range low", "failed breakdown / liquidity sweep", "higher low forming", "selling volume fading", "volatility compression", "momentum turning up"]
COST = 0.0010  # assumed 0.10% round-trip fees + slippage

def collect(m15, step=2):
    h1, h4, out = B.rs(m15, "1h"), B.rs(m15, "4h"), []
    for i in range(700, len(m15) - 100, step):
        tc = m15.ts.iloc[i] + 900000
        a1, a4 = h1[h1.ts + 3600000 <= tc].tail(60), h4[h4.ts + 14400000 <= tc].tail(60)
        r = E.scan(m15.iloc[i - 300:i + 1], a4, a1)
        if r["signal"] == "NO TRADE": continue
        pro = {REV.get(x, x) for x in r["pro"]}
        out.append(dict(i=i, side=1 if r["side"] == "LONG" else -1, e=r["entry"], score=r["score"], regime=r["regime"],
                        a1=float(E.atr_series(a1).iloc[-1]), r0=abs(r["entry"] - r["sl"]), **{f: f in pro for f in FACT}))
    return out

def sim(M, s, risk, mult, H):
    i, k, e = s["i"], s["side"], s["e"]
    hi, lo = M["h"][i + 1:i + 1 + H], M["l"][i + 1:i + 1 + H]
    fa, ad = ((hi - e) if k == 1 else (e - lo)), ((e - lo) if k == 1 else (hi - e))
    sl = int(np.argmax(ad >= risk)) if (ad >= risk).any() else 10**9
    tp = int(np.argmax(fa >= mult * risk)) if (fa >= mult * risk).any() else 10**9
    r = mult if tp < sl else (-1.0 if sl < 10**9 else (M["c"][i + H] - e) * k / risk)  # same-bar = stop first (conservative)
    return r - COST * e / risk

def ev(M, S, cfg):
    out = []
    for s in S:
        risk = s["r0"] if cfg == "orig" else cfg[0] * s["a1"]
        mult, H = (1.5, 48) if cfg == "orig" else (cfg[1], cfg[2])
        if risk > 0 and risk == risk: out.append(sim(M, s, risk, mult, H))
    return np.array(out)

def st(r):
    if len(r) < 2: return {"n": len(r)}
    return {"n": len(r), "mean_R": round(float(r.mean()), 3), "win_%": round(float((r > 0).mean() * 100), 1), "se": round(float(r.std() / np.sqrt(len(r))), 3)}

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    m = B.hist(days); M = {c: m[c].values for c in ("h", "l", "c")}
    S, last = [], -99
    for s in collect(m):                      # one trade per 4h window, same trades for every config
        if s["i"] >= last + 16: S.append(s); last = s["i"]
    cut = int(len(S) * 0.7); tr, te = S[:cut], S[cut:]
    cfgs = [(k, mu, H) for k in (1, 1.5, 2, 3) for mu in (1, 1.5, 2, 3) for H in (24, 48, 96)]
    rows = [dict(cfg=str(c), train=st(ev(M, tr, c)), test=st(ev(M, te, c))) for c in ["orig"] + cfgs]
    cand = [r for r in rows[1:] if r["train"].get("n", 0) >= 100]
    best = max(cand, key=lambda r: r["train"]["mean_R"])
    t = best["test"]; edge = t.get("n", 0) >= 100 and best["train"]["mean_R"] > 0.05 and t["mean_R"] > 0.05 and t["mean_R"] - t["se"] > 0
    base = (1.5, 1.5, 48); allr = ev(M, S, base); lift = {}
    for f in FACT:
        p = np.array([s[f] for s in S])[:len(allr)]
        lift[f] = dict(present=st(allr[p]), absent=st(allr[~p]))
    sc = np.array([s["score"] for s in S])[:len(allr)]
    res = dict(
        note="mean_R = avg result per trade in R after 0.10% cost. Best config chosen on TRAIN, judged on unseen TEST. cfg=(stop x ATR1h, target R, horizon 15m-bars)",
        trades=len(S), original_rules=rows[0], best=best, verdict="EDGE FOUND (params.json written)" if edge else "NO RELIABLE EDGE - live levels unchanged",
        top5_train=sorted(rows[1:], key=lambda r: -(r["train"].get("mean_R") or -9))[:5], factor_lift=lift,
        score_buckets={"60-64": st(allr[sc < 65]), "65-79": st(allr[(sc >= 65) & (sc < 80)]), "80+": st(allr[sc >= 80])})
    json.dump(res, open("backtest_v3_results.json", "w"), indent=1); print(json.dumps(res, indent=1))
    if edge:
        k, mu, H = eval(best["cfg"]); json.dump(dict(sl_atr=k, tp_mult=mu, horizon=H), open("params.json", "w"))
    if os.environ.get("TG_TOKEN"):
        msg = (f"V3 backtest ({days}d), {len(S)} trades\nOriginal rules: mean {rows[0]['train'].get('mean_R')}R train / {rows[0]['test'].get('mean_R')}R test\n"
               f"Best cfg {best['cfg']}: train {best['train'].get('mean_R')}R, TEST {t.get('mean_R')}R (n={t.get('n')})\nVerdict: {res['verdict']}")
        requests.post(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage", json=dict(chat_id=os.environ["TG_CHAT_ID"], text=msg), timeout=20)
