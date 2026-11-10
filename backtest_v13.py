"""V13: does 'Bollinger band + RSI extreme + volume spike' reversion (strategy bb_rsi_vol) have an edge, after 0.05%/side fees?
Pooled over several perpetuals (BTC, ETH, SOL and a few liquid alts) on ~5 years of 1H data. Same honest method as V12: a grid of settings is judged on the FIRST 60% of each coin's
history (train); the settings that look best on train are then judged on the unseen last 40% (test). Test is never used for choosing. ~100 combos are tried, so a few look good by luck:
the verdict needs test mean R > 0 at 95% one-sided AND positive in both halves of the test part; the share of all combos that are positive on test is printed (about half = noise).
Entry = next bar open. Stop = beyond the signal candle's extreme (+0.3 ATR, clamped 0.8-2.0 ATR, min 0.5%), target 1/1.5/2 R, expiry 24 bars, stop checked first inside a bar."""
import sys, json, math, time
import numpy as np, pandas as pd
import engine as E, backtest_v4 as W4

FEE, EXPIRY, MIN_STOP = 0.0005, 24, 0.005
COINS = ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK")
BB = (2.0, 2.5); RSIS = (30, 25, 20); VOLS = (1.0, 1.5, 2.0); GUARD = (True, False); TARGETS = (1.0, 1.5, 2.0)


def hist1h_sym(sym, days):
    out, after = [], ""
    while len(out) < days * 24:
        q = dict(instId=f"{sym}-USDT-SWAP", bar="1H", limit=100)
        if after: q["after"] = after
        try: d = E._get("market/history-candles", **q)
        except Exception as e: print(sym, "fetch stopped:", e); break
        if not d: break
        out += d; after = d[-1][0]; time.sleep(0.12)
    df = pd.DataFrame([x[:6] for x in out], columns=["ts", "o", "h", "l", "c", "v"]).astype(float)
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def prep(df):
    h1 = W4.prep(df); c = h1.c
    h1["rsi"] = (lambda d: 100 - 100 / (1 + d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean() / (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan)))(c.diff()).fillna(100)
    for m in BB:
        mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0); h1[f"up{m}"], h1[f"dn{m}"] = mid + m * sd, mid - m * sd
    h1["vr"] = h1.v / h1.v.shift(1).rolling(24).mean()
    return h1


def signals(h1, m, rsi_os, vm, guard):
    c, o, hi, lo = h1.c.values, h1.o.values, h1.h.values, h1.l.values; rsi, vr = h1.rsi.values, h1.vr.values; up, dn = h1[f"up{m}"].values, h1[f"dn{m}"].values; er4, d4 = h1.er4.values, h1.dir4.values
    ok = np.isfinite(vr) & np.isfinite(up) & (vr >= vm)
    L = ok & (lo <= dn) & (rsi <= rsi_os) & (c > o); Sg = ok & (hi >= up) & (rsi >= 100 - rsi_os) & (c < o)
    if guard: L &= ~((er4 >= 0.5) & (d4 < 0)); Sg &= ~((er4 >= 0.5) & (d4 > 0))
    sig = np.zeros(len(c), int); sig[L] = 1; sig[Sg] = -1; sig[:260] = 0; return sig


def simulate(h1, sig, tgt_r):
    o, h, l, c, a, ts = h1.o.values, h1.h.values, h1.l.values, h1.c.values, h1.atr.values, h1.ts.values; n = len(c); out = []; i = 260
    while i < n - EXPIRY - 2:
        k = sig[i]
        if k == 0 or not np.isfinite(a[i]): i += 1; continue
        e = o[i + 1]; ext = min(l[i], l[i - 1]) if k == 1 else max(h[i], h[i - 1]); d = abs(e - (ext - k * 0.3 * a[i])); d = min(max(d, 0.8 * a[i]), 2.0 * a[i]); d = max(d, MIN_STOP * e)
        sl, tp = e - k * d, e + k * tgt_r * d; ex = None; j = i + 1
        for j in range(i + 1, i + 1 + EXPIRY):
            if (l[j] <= sl) if k == 1 else (h[j] >= sl): ex = sl; break
            if (h[j] >= tp) if k == 1 else (l[j] <= tp): ex = tp; break
        if ex is None: ex = c[j]
        out.append((float(ts[i]), int(k), float(((ex - e) * k - FEE * (e + ex)) / d))); i = j + 1
    return out


def stat(rows):
    R = np.array([r[2] for r in rows]); n = len(R)
    if n < 3: return dict(n=n)
    m, se = float(R.mean()), float(R.std(ddof=1) / math.sqrt(n)); gp, gl = R[R > 0].sum(), -R[R < 0].sum()
    return dict(n=n, win_pct=round(float((R > 0).mean() * 100), 1), mean_R=round(m, 3), se=round(se, 3), lo95=round(m - 1.645 * se, 3), pf=round(float(gp / gl), 2) if gl > 0 else None, sum_R=round(float(R.sum()), 1))


def main(days=2000, coins=COINS, loader=hist1h_sym):
    data = {}
    for s in coins:
        try:
            df = loader(s, days).reset_index(drop=True)
            if len(df) > 1500: data[s] = (prep(df), float(df.ts.iloc[int(len(df) * 0.6)]), float(df.ts.iloc[-1]))
            print(s, len(df), "bars")
        except Exception as e: print(s, "failed", type(e).__name__, e)
    grid = []
    for m in BB:
        for rs in RSIS:
            for vm in VOLS:
                for gd in GUARD:
                    sigs = {s: signals(h, m, rs, vm, gd) for s, (h, _, _) in data.items()}
                    for tg in TARGETS:
                        rows = []
                        for s, (h, tt, te) in data.items(): rows += [(t, k, R, s, tt, (tt + te) / 2) for t, k, R in simulate(h, sigs[s], tg)]
                        trn = [r for r in rows if r[0] < r[4]]; tst = [r for r in rows if r[0] >= r[4]]
                        grid.append(dict(rule=f"bb{m}/rsi{rs}-{100 - rs}/vol{vm}x/{'trend-guard' if gd else 'no-guard'}/target{tg}R", train=stat(trn), test=stat(tst),
                                         test_h1=stat([r for r in tst if r[0] < r[5]]), test_h2=stat([r for r in tst if r[0] >= r[5]]),
                                         test_by_coin={s: stat([r for r in tst if r[3] == s]) for s in data}))
    ok = [g for g in grid if g["train"].get("n", 0) >= 100 and g["test"].get("n", 0) >= 50]
    by_train = sorted([g for g in ok if g["train"]["mean_R"] > 0], key=lambda g: -g["train"]["mean_R"])[:8]
    pos_share = round(100 * sum(g["test"]["mean_R"] > 0 for g in ok) / max(len(ok), 1), 1)
    top = by_train[0] if by_train else None
    verdict = ("PROMISING (paper-trade it first)" if top and top["test"].get("lo95", -9) > 0 and top["test_h1"].get("mean_R", -9) > 0 and top["test_h2"].get("mean_R", -9) > 0 else "NOT PROVEN" if top else "NO SETTING WAS PROFITABLE EVEN ON TRAIN")
    res = dict(coins=list(data), combos=len(grid), tested_ok=len(ok), pct_combos_positive_on_test=pos_share, verdict=verdict, chosen_on_train=by_train, all_combos=grid)
    json.dump(res, open("backtest_v13_results.json", "w"), indent=1)
    print(json.dumps(dict(coins=list(data), combos=len(grid), pct_positive_on_test=pos_share, verdict=verdict, best_by_train=[(g["rule"], g["train"], g["test"]) for g in by_train[:3]])))
    return res


if __name__ == "__main__": main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
