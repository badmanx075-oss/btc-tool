"""Multi-method market analysis: 7 independent price-based methods vote LONG / SHORT / NEUTRAL, plus live 'second opinion' votes
(order flow, derivatives, multi-timeframe). Every trade gets this check; the 'confluence' strategy trades only when several methods agree.
Price methods use ONLY past candles, so the same code runs live and in the backtest (backtest_v9).
Methods: 1 Trend (EMAs) | 2 Market structure (HH/HL, LH/LL, break of structure) | 3 Candlestick patterns | 4 Support/Resistance location
         5 Momentum (RSI + MACD) | 6 Bollinger bands (squeeze/breakout/mean reversion) | 7 Volume (spike + OBV)."""
import numpy as np, pandas as pd

K = 3                                   # swing pivot needs K bars on each side
WEIGHTS = dict(trend=1.5, structure=1.5, candles=1.0, sr=1.0, momentum=1.0, bands=0.7, volume=0.8)
NAMES = dict(trend="Trend", structure="Market structure", candles="Candlestick", sr="Support/Resistance", momentum="Momentum", bands="Bollinger bands", volume="Volume")


def _ema(x, n): return pd.Series(x).ewm(span=n, adjust=False).mean().values


def prepare(df):
    """Indicators for every bar (vectorised, no look-ahead)."""
    o, h, l, c, v = (df[k].values.astype(float) for k in ("o", "h", "l", "c", "v")); n = len(c); s = pd.Series
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc))); atr = s(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    d = np.diff(c, prepend=c[0]); up, dn = s(np.clip(d, 0, None)).ewm(alpha=1 / 14, adjust=False).mean().values, s(np.clip(-d, 0, None)).ewm(alpha=1 / 14, adjust=False).mean().values
    rsi = 100 - 100 / (1 + up / np.maximum(dn, 1e-9)); macd = _ema(c, 12) - _ema(c, 26); hist = macd - _ema(macd, 9)
    ma, sd = s(c).rolling(20).mean().values, s(c).rolling(20).std().values; bw = (4 * sd) / np.maximum(ma, 1e-9); bw_pct = s(bw).rolling(240, min_periods=60).rank(pct=True).values
    obv = np.cumsum(np.sign(d) * v); vavg = s(v).rolling(24).mean().shift(1).values
    # confirmed swing pivots (known only K bars later)
    sh_val, sl_val = np.full(n, np.nan), np.full(n, np.nan); sh_at, sl_at = np.full(n, -1), np.full(n, -1)
    for j in range(K, n - K):
        if h[j] == h[j - K:j + K + 1].max() and h[j] > h[j - 1]: sh_val[j + K] = h[j]; sh_at[j + K] = j
        if l[j] == l[j - K:j + K + 1].min() and l[j] < l[j - 1]: sl_val[j + K] = l[j]; sl_at[j + K] = j
    return dict(o=o, h=h, l=l, c=c, v=v, atr=atr, rsi=rsi, hist=hist, ema20=_ema(c, 20), ema50=_ema(c, 50), ema200=_ema(c, 200), ma=ma, sd=sd, bw_pct=bw_pct, obv=obv, vavg=vavg, sh=sh_val, sl=sl_val, n=n)


def _last_pivots(I, i, arr, cnt=2, look=160):
    seg = arr[max(0, i - look):i + 1]; vals = seg[~np.isnan(seg)]; return vals[-cnt:][::-1]      # newest first


def votes(I, i):
    """List of (key, direction -1/0/1, strength 0..1, reason) for bar i (a completed candle)."""
    c, o, h, l, a = I["c"], I["o"], I["h"], I["l"], I["atr"][i]; out = []
    if i < 210 or not a == a: return out
    # 1 trend
    e20, e50, e200 = I["ema20"][i], I["ema50"][i], I["ema200"][i]; sep = abs(e20 - e200) / a
    if e20 > e50 > e200 and c[i] > e50: out.append(("trend", 1, min(0.4 + sep / 12, 1), "EMA20>EMA50>EMA200 aur bhaav EMA50 ke upar: uptrend"))
    elif e20 < e50 < e200 and c[i] < e50: out.append(("trend", -1, min(0.4 + sep / 12, 1), "EMA20<EMA50<EMA200 aur bhaav EMA50 ke neeche: downtrend"))
    else: out.append(("trend", 0, 0, "EMAs mile-jule: saaf trend nahi"))
    # 2 structure
    sh, sl = _last_pivots(I, i, I["sh"]), _last_pivots(I, i, I["sl"])
    if len(sh) == 2 and len(sl) == 2:
        hh, hl, lh, ll = sh[0] > sh[1], sl[0] > sl[1], sh[0] < sh[1], sl[0] < sl[1]
        if c[i] > sh[0] + 0.05 * a: out.append(("structure", 1, 1.0 if hl else 0.7, "Pichla swing-high toota (break of structure upar)"))
        elif c[i] < sl[0] - 0.05 * a: out.append(("structure", -1, 1.0 if lh else 0.7, "Pichla swing-low toota (break of structure neeche)"))
        elif hh and hl: out.append(("structure", 1, 0.6, "Higher-high aur higher-low: buyers control mein"))
        elif lh and ll: out.append(("structure", -1, 0.6, "Lower-high aur lower-low: sellers control mein"))
        else: out.append(("structure", 0, 0, "Swings mixed: sideways/range"))
    else: out.append(("structure", 0, 0, "Swing data kam"))
    # 3 candlesticks (with location bonus)
    body = lambda k: abs(c[k] - o[k]); rng = lambda k: max(h[k] - l[k], 1e-9); lw = lambda k: min(o[k], c[k]) - l[k]; uw = lambda k: h[k] - max(o[k], c[k])
    near_sup = len(sl) > 0 and abs(l[i] - sl[0]) < 1.0 * a or l[i] <= l[i - 24:i].min() + 0.5 * a; near_res = len(sh) > 0 and abs(h[i] - sh[0]) < 1.0 * a or h[i] >= h[i - 24:i].max() - 0.5 * a
    pat = None
    if c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body(i) > body(i - 1): pat = (1, "Bullish engulfing candle (pichli laal candle puri nigal li)", near_sup)
    elif c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] <= o[i - 1] and o[i] >= c[i - 1] and body(i) > body(i - 1): pat = (-1, "Bearish engulfing candle (pichli hari candle puri nigal li)", near_res)
    elif lw(i) >= 2 * max(body(i), 0.1 * rng(i)) and uw(i) <= 0.3 * rng(i) and (c[i] - l[i]) / rng(i) > 0.6: pat = (1, "Hammer / bullish pin bar (neeche se tez wapsi, lambi neeche ki wick)", near_sup)
    elif uw(i) >= 2 * max(body(i), 0.1 * rng(i)) and lw(i) <= 0.3 * rng(i) and (h[i] - c[i]) / rng(i) > 0.6: pat = (-1, "Shooting star / bearish pin bar (upar se rejection, lambi upar ki wick)", near_res)
    elif c[i - 2] < o[i - 2] and body(i - 1) < 0.35 * body(i - 2) and c[i] > o[i] and c[i] > (o[i - 2] + c[i - 2]) / 2: pat = (1, "Morning star (3 candle ka reversal pattern, neeche se upar)", near_sup)
    elif c[i - 2] > o[i - 2] and body(i - 1) < 0.35 * body(i - 2) and c[i] < o[i] and c[i] < (o[i - 2] + c[i - 2]) / 2: pat = (-1, "Evening star (3 candle ka reversal pattern, upar se neeche)", near_res)
    if pat: out.append(("candles", pat[0], 0.9 if pat[2] else 0.45, pat[1] + (" (support/resistance ke paas, isliye bharosemand)" if pat[2] else " (beech mein bana, kamzor)")))
    elif body(i) < 0.15 * rng(i): out.append(("candles", 0, 0, "Doji: market confuse hai"))
    elif h[i] < h[i - 1] and l[i] > l[i - 1]: out.append(("candles", 0, 0, "Inside bar: breakout ka intezaar"))
    else: out.append(("candles", 0, 0, "Koi khaas candle pattern nahi"))
    # 4 support / resistance location
    if len(sl) and len(sh):
        ds, dr = c[i] - sl[0], sh[0] - c[i]
        if 0 <= ds < 0.8 * a and c[i] > o[i]: out.append(("sr", 1, 0.8, f"Bhaav support (${sl[0]:,.0f}) ke bilkul paas aur wahan se upar bandh hua"))
        elif 0 <= dr < 0.8 * a and c[i] < o[i]: out.append(("sr", -1, 0.8, f"Bhaav resistance (${sh[0]:,.0f}) ke paas aur wahan se neeche bandh hua"))
        else: out.append(("sr", 0, 0, "Bhaav kisi major support/resistance ke paas nahi"))
    else: out.append(("sr", 0, 0, "Levels kam"))
    # 5 momentum
    r, hs = I["rsi"][i], I["hist"][i]; hp = I["hist"][i - 1]
    if r > 75: out.append(("momentum", -1, 0.5, f"RSI {r:.0f}: zyada garam (overbought), girne ka risk"))
    elif r < 25: out.append(("momentum", 1, 0.5, f"RSI {r:.0f}: zyada thanda (oversold), uchhalne ka mauka"))
    elif r > 55 and hs > 0 and hs >= hp: out.append(("momentum", 1, 0.8, f"RSI {r:.0f} aur MACD upar badh rahe hain"))
    elif r < 45 and hs < 0 and hs <= hp: out.append(("momentum", -1, 0.8, f"RSI {r:.0f} aur MACD neeche ja rahe hain"))
    else: out.append(("momentum", 0, 0, f"RSI {r:.0f}: momentum saaf nahi"))
    # 6 bollinger
    up_b, lo_b = I["ma"][i] + 2 * I["sd"][i], I["ma"][i] - 2 * I["sd"][i]; sq = (I["bw_pct"][i - 1] if i else 1) < 0.2
    if sq and c[i] > up_b: out.append(("bands", 1, 0.9, "Volatility dabne ke baad upper band ke upar breakout"))
    elif sq and c[i] < lo_b: out.append(("bands", -1, 0.9, "Volatility dabne ke baad lower band ke neeche breakdown"))
    elif c[i] < lo_b and r < 35: out.append(("bands", 1, 0.5, "Lower band ke bahar + RSI neeche: mean-reversion bounce"))
    elif c[i] > up_b and r > 65: out.append(("bands", -1, 0.5, "Upper band ke bahar + RSI upar: mean-reversion girawat"))
    else: out.append(("bands", 0, 0, "Bands ke andar normal chal"))
    # 7 volume
    vr = I["v"][i] / max(I["vavg"][i], 1e-9); obv_s = I["obv"][i] - I["obv"][i - 24]
    if vr >= 1.5 and c[i] > o[i]: out.append(("volume", 1, min(vr / 3, 1), f"Volume normal ka {vr:.1f} guna, buying ke saath"))
    elif vr >= 1.5 and c[i] < o[i]: out.append(("volume", -1, min(vr / 3, 1), f"Volume normal ka {vr:.1f} guna, selling ke saath"))
    elif obv_s > 0 and c[i] > c[i - 24]: out.append(("volume", 1, 0.4, "OBV aur bhaav dono upar: volume trend ka saath de raha hai"))
    elif obv_s < 0 and c[i] < c[i - 24]: out.append(("volume", -1, 0.4, "OBV aur bhaav dono neeche: volume trend ka saath de raha hai"))
    else: out.append(("volume", 0, 0, "Volume koi saaf sanket nahi de raha"))
    return out


def consensus(vs, need=4, net_min=35):
    if not vs: return dict(verdict="WAIT", net=0, long=0, short=0, total=0, votes=[], confidence="data kam")
    W = sum(WEIGHTS[k] for k, *_ in vs); net = sum(d * s * WEIGHTS[k] for k, d, s, _ in vs) / W * 100
    nl, ns = sum(d == 1 for _, d, _, _ in vs), sum(d == -1 for _, d, _, _ in vs)
    verdict = "LONG" if nl >= need and ns <= 1 and net >= net_min else "SHORT" if ns >= need and nl <= 1 and net <= -net_min else "WAIT"
    return dict(verdict=verdict, net=round(float(net), 1), long=nl, short=ns, total=len(vs), confidence=f"{max(nl, ns)}/{len(vs)} methods ek taraf",
                votes=[dict(key=k, name=NAMES[k], dir=d, strength=round(float(s), 2), why=t) for k, d, s, t in vs])


def live_extras(S):
    """Second-opinion votes that only exist live (not in price history): order flow, derivatives, multi-timeframe."""
    D = (S.get("desk") or {}); d = D.get("derivs") or {}; ex = []
    td = d.get("taker_delta")
    if td is not None: ex.append(dict(name="Order flow (taker)", dir=1 if td > 0.05 else -1 if td < -0.05 else 0, why=f"Taker delta {td:+.2f}: {'buyers aggressive' if td > 0.05 else 'sellers aggressive' if td < -0.05 else 'balanced'}"))
    q = d.get("quadrant")
    if q: ex.append(dict(name="OI + price", dir={"long_buildup": 1, "short_covering": 1, "short_buildup": -1, "long_liquidation": -1}.get(q, 0), why=f"Open interest/price: {q.replace('_', ' ')}"))
    cr = d.get("crowding")
    if cr and cr != "balanced": ex.append(dict(name="Crowding", dir=-1 if "long" in str(cr) else 1 if "short" in str(cr) else 0, why=f"Market {cr}: bheed ke ulte side ka risk"))
    of = (S.get("orderflow") or {}).get("now") or {}
    if of.get("state") and of["state"] != "NO DATA": ex.append(dict(name="Aggression (60 min)", dir=1 if "BUY" in of["state"] else -1 if "SELL" in of["state"] else 0, why=f"{of['state']} (delta {of['ratio'] * 100:+.0f}%, bade orders {of['big_share'] * 100:.0f}%)"))
    rows = {r["tf"]: r["direction"] for r in (D.get("mtf") or {}).get("rows", [])}
    if rows:
        ups, dns = sum(v == "UP" for v in rows.values()), sum(v == "DOWN" for v in rows.values()); ex.append(dict(name="Multi-timeframe", dir=1 if ups >= 4 else -1 if dns >= 4 else 0, why=f"{ups} timeframe UP, {dns} DOWN (5m..4H)"))
    return ex


def analyze(h1df, S=None, need=4, net_min=35):
    """Live: consensus on the last COMPLETED 1H candle (+ live second-opinion votes)."""
    I = prepare(h1df.reset_index(drop=True)); i = I["n"] - 2; res = consensus(votes(I, i), need, net_min); res["bar_ts"] = float(h1df.ts.iloc[-2])
    res["atr"] = float(I["atr"][i]); res["price"] = float(I["c"][i])
    if S is not None: res["extras"] = live_extras(S)
    return res


def text(R):
    if not R or not R.get("votes"): return "Multi-method analysis abhi ready nahi."
    L = [f"🧩 MULTI-METHOD CHECK: {R['verdict']} (net {R['net']:+.0f}, {R['confidence']}; LONG {R['long']} | SHORT {R['short']} | neutral {R['total'] - R['long'] - R['short']})"]
    for v in R["votes"]: L.append(f"{'🟢' if v['dir'] == 1 else '🔴' if v['dir'] == -1 else '⚪'} {v['name']}: {v['why']}")
    for x in R.get("extras") or []: L.append(f"{'🟢' if x['dir'] == 1 else '🔴' if x['dir'] == -1 else '⚪'} (live) {x['name']}: {x['why']}")
    return "\n".join(L)


def short(R):
    """One line for trade messages."""
    if not R or not R.get("votes"): return ""
    return f"{R['verdict']} (LONG {R['long']}/SHORT {R['short']} of {R['total']}, net {R['net']:+.0f})"
