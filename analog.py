"""Analog engine: the 'AI' of this tool, with NO API key and NO paid service. It is a nearest-neighbour model (a standard machine-learning method).
Every past hour of the last year is described by 10 numbers (trend distance in ATR, RSI, MACD, 6h momentum, volatility rank, volume, position in 48h range, band width...).
For the CURRENT hour we find the ~150 most similar past hours and look at what happened next (1h / 4h / 24h): up or down, how big the range was,
how far price went against/with a trade (-> stop-loss guide). It is re-checked on UNSEEN data (walk-forward) and the result is shown with every answer:
volatility/range is usually predictable, direction usually is not, and the tool says so instead of pretending.
Files: analog_lib.npz (history features + outcomes, rebuilt weekly) and analog_stats.json (validation)."""
import os, json, math, datetime as dt
import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
import methods as MT

LIB = "analog_lib.npz"; META = "analog_stats.json"; HB = (1, 4, 24); K = 150; WARM = 250; SPACE = 3; REBUILD_DAYS = 7
GRID = [0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]                  # % distance grid for the stop-loss table
FN = ["trend20", "trend50", "trend200", "rsi", "macd", "mom6", "vol_rank", "vol_ratio", "pos48", "bands"]
_CACHE = {}


def features(I):
    c, atr, n = I["c"], np.maximum(I["atr"], 1e-9), I["n"]; f = np.full((n, len(FN)), np.nan)
    f[:, 0] = (c - I["ema20"]) / atr; f[:, 1] = (I["ema20"] - I["ema50"]) / atr; f[:, 2] = (I["ema50"] - I["ema200"]) / atr; f[:, 3] = I["rsi"] / 100; f[:, 4] = I["hist"] / atr
    f[6:, 5] = (c[6:] - c[:-6]) / atr[6:]; f[:, 6] = pd.Series(atr / np.maximum(c, 1e-9)).rolling(240, min_periods=60).rank(pct=True).values
    f[:, 7] = np.clip(I["v"] / np.maximum(I["vavg"], 1e-9), 0, 5); hi, lo = pd.Series(I["h"]).rolling(48).max().values, pd.Series(I["l"]).rolling(48).min().values
    f[:, 8] = (c - lo) / np.maximum(hi - lo, 1e-9); f[:, 9] = I["bw_pct"]; f[:WARM] = np.nan
    return f


def targets(I):
    """T[i, h, :] = (return %, range %, max-up %, max-down %) over the NEXT HB[h] bars after bar i closes."""
    n, c, hh, ll = I["n"], I["c"], I["h"], I["l"]; T = np.full((n, len(HB), 4), np.nan, np.float32)
    for a, H in enumerate(HB):
        m = n - H
        if m <= 1: continue
        mx, mn = sliding_window_view(hh, H).max(axis=1), sliding_window_view(ll, H).min(axis=1)
        T[:m, a, 0] = (c[H:] - c[:m]) / c[:m] * 100; T[:m, a, 1] = (mx[1:m + 1] - mn[1:m + 1]) / c[:m] * 100; T[:m, a, 2] = (mx[1:m + 1] - c[:m]) / c[:m] * 100; T[:m, a, 3] = (c[:m] - mn[1:m + 1]) / c[:m] * 100
    return T


def zscore(f, mu, sd): return np.clip((f - mu) / sd, -3, 3)


def nearest(Z, idx, z, k=K, space=SPACE):
    """k nearest library rows (de-duplicated: neighbours of the same episode are >space bars apart)."""
    d = ((Z[idx] - z) ** 2).sum(axis=1); cand = idx[np.argsort(d)[:k * 5]]; blocked, out = set(), []
    for j in cand:
        j = int(j)
        if j in blocked: continue
        out.append(j); blocked.update(range(j - space, j + space + 1))
        if len(out) >= k: break
    return np.array(out, int)


def wilson(p, n, z=1.96):
    if n <= 0: return 0.0, 1.0
    den = 1 + z * z / n; c = (p + z * z / (2 * n)) / den; m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den; return c - m, c + m


def horizon_stats(T, nb, a, base_up):
    r, rng, up, dn = (T[nb, a, j].astype(float) for j in range(4)); ok = ~np.isnan(r); r, rng, up, dn = r[ok], rng[ok], up[ok], dn[ok]; n = len(r)
    if n < 20: return None
    H = HB[a]; neff = n / (1 + (H - 1) / 3); p = float((r > 0).mean()); lo, hi = wilson(p, neff)
    return dict(h=H, n=int(n), neff=round(neff), p_up=round(p, 4), lo=round(lo, 4), hi=round(hi, 4), base=round(base_up, 4), avg=round(float(r.mean()), 3), rng=[round(float(q), 3) for q in np.percentile(rng, [50, 75, 90])],
                up50=round(float(np.median(up)), 3), dn50=round(float(np.median(dn)), 3), touch_up=[round(float((up >= g).mean()), 3) for g in GRID], touch_dn=[round(float((dn >= g).mean()), 3) for g in GRID])


def signal(st):
    """Rule used by the optional 'analog_edge' strategy (needs a clear, statistically supported lean at the 4h horizon)."""
    if not st: return None
    if st["p_up"] >= 0.58 and st["lo"] >= 0.50: return "LONG"
    if st["p_up"] <= 0.42 and st["hi"] <= 0.50: return "SHORT"
    return None


# ------------------------------------------------------------------ build + validation (weekly)
def _validate(F, T, I, step=3):
    n = len(F); t0 = int(n * 0.6); mu = np.nanmean(F[WARM:t0], axis=0); sd = np.nanstd(F[WARM:t0], axis=0) + 1e-9; Z = zscore(F, mu, sd); okf = ~np.isnan(Z).any(axis=1); out = {}
    atrp = I["atr"] / np.maximum(I["c"], 1e-9) * 100
    for a, H in enumerate(HB):
        P, A, PM, P90, AT = [], [], [], [], []; ok_t = ~np.isnan(T[:, a, 0])
        for i in range(t0, n - 25, step):
            if not okf[i] or not ok_t[i]: continue
            idx = np.where(okf[:i - 24] & ok_t[:i - 24])[0]
            if len(idx) < 300: continue
            nb = nearest(Z, idx, Z[i]); r, rng = T[nb, a, 0], T[nb, a, 1]; P.append(float((r > 0).mean())); A.append(float(T[i, a, 0] > 0)); PM.append(float(np.median(rng))); P90.append(float(np.percentile(rng, 90))); AT.append(float(T[i, a, 1]));
        if len(P) < 100: continue
        P, A, PM, P90, AT = map(np.array, (P, A, PM, P90, AT)); base = float(np.nanmean((T[WARM:t0 - 25, a, 0] > 0))); lean = np.abs(P - 0.5) >= 0.05
        hit = float(((P > 0.5) == (A > 0.5))[lean].mean() * 100) if lean.sum() >= 30 else None
        brier, brier0 = float(np.mean((P - A) ** 2)), float(np.mean((base - A) ** 2)); ap = atrp[t0:n - 25:step][:len(P)]
        corr = float(pd.Series(PM).corr(pd.Series(AT), method="spearman")); corr0 = float(pd.Series(ap).corr(pd.Series(AT), method="spearman")) if len(ap) == len(AT) else None
        out[str(H)] = dict(tests=int(len(P)), lean_n=int(lean.sum()), hit_pct=None if hit is None else round(hit, 1), brier=round(brier, 4), brier_base=round(brier0, 4), range_corr=round(corr, 3), range_corr_atr=None if corr0 is None else round(corr0, 3), p90_coverage=round(float((AT <= P90).mean() * 100), 1))
    return out


def build(df):
    I = MT.prepare(df.reset_index(drop=True)); F, T = features(I), targets(I); n = len(F); ok = ~np.isnan(F).any(axis=1)
    if ok.sum() < 1500: return None
    mu, sd = np.nanmean(F[ok], axis=0), np.nanstd(F[ok], axis=0) + 1e-9; Z = zscore(F, mu, sd)
    np.savez_compressed(LIB, Z=np.nan_to_num(Z, nan=99).astype(np.float16), T=T.astype(np.float16), mu=mu, sd=sd, ts=np.array([float(df.ts.iloc[0]), float(df.ts.iloc[-1])]))
    val = _validate(F, T, I); meta = dict(built=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), rows=int(ok.sum()), days=int((df.ts.iloc[-1] - df.ts.iloc[0]) / 86400000), val=val)
    json.dump(meta, open(META, "w"), separators=(",", ":")); _CACHE.clear(); return meta


def ensure(now, budget_s=40, force=False):
    """Rebuild weekly (fetches 1 year of 1H candles). Never raises."""
    try:
        m = load_meta()
        if m and not force and os.path.exists(LIB) and (now - dt.datetime.fromisoformat(m["built"])).total_seconds() < REBUILD_DAYS * 86400: return m
        import askstats as AS
        df = AS.fetch("1H", 365, budget_s)
        return build(df) if len(df) > 1500 else m
    except Exception as e: print("analog ensure error", e); return load_meta()


def load_meta():
    try: return json.load(open(META))
    except Exception: return None


def _lib():
    if "lib" not in _CACHE:
        L = np.load(LIB); _CACHE["lib"] = dict(Z=L["Z"].astype(np.float32), T=L["T"].astype(np.float32), mu=L["mu"], sd=L["sd"], ts=L["ts"])
    return _CACHE["lib"]


def live(h1):
    """Called every scan: nearest-neighbour stats for the last completed 1H candle. Small dict stored in state.json (the dashboard needs no files)."""
    if not os.path.exists(LIB): return None
    L = _lib(); I = MT.prepare(h1.reset_index(drop=True)); n = I["n"]; i = n - 2; f = features(I)[i]
    if n <= WARM + 5 or np.isnan(f).any(): return None
    z = zscore(f, L["mu"], L["sd"]); Z, T = L["Z"], L["T"]; okf = Z.max(axis=1) < 90; out = dict(ts=float(h1.ts.iloc[-2]), price=round(float(I["c"][i]), 1), feats={k: round(float(v), 2) for k, v in zip(FN, f)}, hz={})
    for a, H in enumerate(HB):
        idx = np.where(okf & ~np.isnan(T[:, a, 0]))[0]
        if len(idx) < 300: continue
        nb = nearest(Z, idx, z); base = float((T[idx, a, 0] > 0).mean()); st = horizon_stats(T, nb, a, base)
        if st: st["dist"] = round(float(np.sqrt(((Z[nb] - z) ** 2).sum(axis=1)).mean()), 2); out["hz"][str(H)] = st
    m = load_meta() or {}; out["val"] = m.get("val", {}); out["days"] = m.get("days"); out["built"] = m.get("built")
    s4 = out["hz"].get("4"); out["signal"] = signal(s4); out["p4"] = s4["p_up"] if s4 else None
    v4 = (out["val"] or {}).get("4") or {}; out["validated"] = bool(v4.get("hit_pct") and v4["hit_pct"] >= 53 and v4.get("lean_n", 0) >= 300 and v4.get("brier", 1) < v4.get("brier_base", 0))
    return out


if __name__ == "__main__":
    import askstats as AS
    m = ensure(dt.datetime.now(dt.timezone.utc), 120, force=True); print(json.dumps(m, indent=1)[:2000])
