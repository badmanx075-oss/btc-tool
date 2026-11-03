"""V12: is there ANY simple rule set that gives BOTH a better win rate AND a positive profit (after 0.1% round-trip fees)? Not a guess: a grid of rule combinations is tested on the
first 60% of ~5 years of 1H data (train); the combos that look best on TRAIN are then judged on the unseen last 40% (test). The test part is never used for choosing.
Two families, both only trade WITH the bigger trend: (A) pullback resume (RSI turns back up/down inside a trend), (B) breakout of the last 24/48h high/low with the trend.
Each is tried with stop 1.5/2/3 ATR (min 0.5% like the live bot), target 1/1.5/2/3 R, and with/without the Asia hours (01-07 UTC). Entry = next bar open, stop checked first inside a candle.
Output: win%, mean R, profit factor for every combo + the 'honest verdict'. Because ~240 combos are tried, a few will look good by pure luck: the verdict therefore needs test mean R > 0 at 95%
one-sided AND positive in both halves of the test part, and the share of all combos that are positive on test is printed (about half = noise)."""
import sys, json, math
import numpy as np, pandas as pd
import methods as MT, backtest_v5 as X

FEE, EXPIRY, MIN_STOP = 0.0005, 48, 0.005
STOPS, TARGETS = (1.5, 2.0, 3.0), (1.0, 1.5, 2.0, 3.0)


def signals(I, fam, trend, par, asia_ok, TS):
    c, a, rsi, e20, e50, e200 = I["c"], I["atr"], I["rsi"], I["ema20"], I["ema50"], I["ema200"]; n = I["n"]
    up = (e50 > e200) & (c > e200); dn = (e50 < e200) & (c < e200)
    if trend == "strong": up = up & (e20 > e50) & ((e50 - e200) / np.maximum(a, 1e-9) > 2); dn = dn & (e20 < e50) & ((e200 - e50) / np.maximum(a, 1e-9) > 2)
    sig = np.zeros(n, int)
    if fam == "pullback":
        p = np.r_[50, rsi[:-1]]; sig[up & (p < par) & (rsi >= par)] = 1; sig[dn & (p > 100 - par) & (rsi <= 100 - par)] = -1
    else:
        hi, lo = pd.Series(I["h"]).rolling(par).max().shift(1).values, pd.Series(I["l"]).rolling(par).min().shift(1).values
        sig[up & (c > hi)] = 1; sig[dn & (c < lo)] = -1
    if not asia_ok: hr = ((TS // 3600000) % 24).astype(int); sig[(hr >= 1) & (hr <= 7)] = 0
    sig[:260] = 0; return sig


def simulate(I, sig, stop_atr, tgt_r, TS):
    o, h, l, c, a = I["o"], I["h"], I["l"], I["c"], I["atr"]; n = I["n"]; out = []; i = 260
    while i < n - EXPIRY - 2:
        k = sig[i]
        if k == 0: i += 1; continue
        e = o[i + 1]; d = max(stop_atr * a[i], MIN_STOP * e); sl = e - k * d; tp = e + k * tgt_r * d; ex = None; j = i + 1
        for j in range(i + 1, i + 1 + EXPIRY):
            if (l[j] <= sl) if k == 1 else (h[j] >= sl): ex = sl; break                    # stop first (conservative)
            if (h[j] >= tp) if k == 1 else (l[j] <= tp): ex = tp; break
        if ex is None: ex = c[j]
        R = ((ex - e) * k - FEE * (e + ex)) / d; out.append((float(TS[i]), int(k), float(R))); i = j + 1
    return out


def stat(rows):
    R = np.array([r[2] for r in rows]); n = len(R)
    if n < 3: return dict(n=n)
    m, se = float(R.mean()), float(R.std(ddof=1) / math.sqrt(n)); gp, gl = R[R > 0].sum(), -R[R < 0].sum()
    return dict(n=n, win_pct=round(float((R > 0).mean() * 100), 1), mean_R=round(m, 3), se=round(se, 3), lo95=round(m - 1.645 * se, 3), pf=round(float(gp / gl), 2) if gl > 0 else None, sum_R=round(float(R.sum()), 1))


def main(days=2000):
    df = X.hist1h(days).reset_index(drop=True); I = MT.prepare(df); TS = df.ts.values; t_train = float(TS[int(len(df) * 0.6)]); t_mid = float((t_train + TS[-1]) / 2); grid = []
    cfgs = [("pullback", tr, par) for tr in ("basic", "strong") for par in (40, 45, 50)] + [("breakout", tr, par) for tr in ("basic", "strong") for par in (24, 48)]
    for fam, tr, par in cfgs:
        for asia_ok in (True, False):
            sig = signals(I, fam, tr, par, asia_ok, TS)
            for sa in STOPS:
                for tg in TARGETS:
                    rows = simulate(I, sig, sa, tg, TS); trn = [r for r in rows if r[0] < t_train]; tst = [r for r in rows if r[0] >= t_train]
                    grid.append(dict(rule=f"{fam}/{tr}/{par}/{'all-hours' if asia_ok else 'no-Asia'}/stop{sa}ATR/target{tg}R", train=stat(trn), test=stat(tst), test_h1=stat([r for r in tst if r[0] < t_mid]), test_h2=stat([r for r in tst if r[0] >= t_mid]), all=stat(rows)))
    ok = [g for g in grid if g["train"].get("n", 0) >= 80 and g["test"].get("n", 0) >= 40]
    by_train = sorted([g for g in ok if g["train"]["mean_R"] > 0], key=lambda g: -g["train"]["mean_R"])[:8]
    pos_share = round(100 * sum(g["test"]["mean_R"] > 0 for g in ok) / max(len(ok), 1), 1)
    best_test_pos = sorted([g for g in ok if g["train"]["mean_R"] > 0 and g["test"]["mean_R"] > 0 and g["test_h1"].get("mean_R", -9) > 0 and g["test_h2"].get("mean_R", -9) > 0], key=lambda g: -g["test"]["mean_R"])[:8]
    top = by_train[0] if by_train else None
    verdict = ("PROMISING (paper-trade it first)" if top and top["test"].get("lo95", -9) > 0 and top["test_h1"].get("mean_R", -9) > 0 and top["test_h2"].get("mean_R", -9) > 0 else "NOT PROVEN" if top else "NO RULE WAS PROFITABLE EVEN ON TRAIN")
    res = dict(rows=len(df), combos=len(grid), tested_ok=len(ok), pct_combos_positive_on_test=pos_share, verdict=verdict, chosen_on_train=by_train, positive_in_train_and_both_test_halves=best_test_pos, all_combos=grid)
    json.dump(res, open("backtest_v12_results.json", "w"), indent=1)
    print(json.dumps(dict(rows=len(df), combos=len(grid), pct_positive_on_test=pos_share, verdict=verdict, best_by_train=[(g["rule"], g["train"], g["test"]) for g in by_train[:3]])))
    return res


if __name__ == "__main__": main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
