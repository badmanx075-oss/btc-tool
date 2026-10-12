"""Reversal evidence (spec 29). Looks for several INDEPENDENT signs that the current trend may be turning, instead of one indicator.
Output is WATCH (early, 2+ signs) or CONFIRMED (4+ signs including a structure break). Never a guarantee."""
import numpy as np
import engine as E


def _pivots(hi, lo, w=3):
    return ([i for i in range(w, len(hi) - w) if hi[i] == hi[i - w:i + w + 1].max()], [i for i in range(w, len(lo) - w) if lo[i] == lo[i - w:i + w + 1].min()])


def evidence(h1, regime, derivs=None):
    """h1 includes the live candle (dropped here). regime: engine.regime() text. derivs: derivs.interpret() output or None."""
    d = h1.iloc[:-1].reset_index(drop=True)
    if len(d) < 80: return dict(direction="none", status="none", score=0, signs=[], against=[], note="not enough data")
    c, o, hi, lo, v = (d[x].values for x in ("c", "o", "h", "l", "v")); a = float(E.atr_series(d).iloc[-1]); ph, pl = _pivots(hi[-150:], lo[-150:]); off = len(hi) - 150 if len(hi) > 150 else 0
    ph, pl = [i + off for i in ph], [i + off for i in pl]
    if regime in ("BULLISH TREND", "TRANSITION BULL->BEAR"): k = 1                 # uptrend (or one already turning): test for a BULL->BEAR turn
    elif regime in ("BEARISH TREND", "TRANSITION BEAR->BULL"): k = -1             # downtrend: test for a BEAR->BULL turn
    else: k = 1 if c[-1] > (hi[-48:].max() + lo[-48:].min()) / 2 else -1          # range / unclear: which edge is price at?
    # k = 1: uptrend, looking for BULL->BEAR turn. k = -1: downtrend, looking for BEAR->BULL turn. Mirror the arrays for the downtrend case.
    cc, oo, H, L = (c, o, hi, lo) if k == 1 else (-c, -o, -lo, -hi); pH = ph if k == 1 else pl
    pL = pl if k == 1 else ph; signs, against = [], []
    # 1) momentum divergence: new price extreme but weaker push (close-to-close move per 6 bars, in ATR)
    if len(pH) >= 2:
        i1, i2 = pH[-2], pH[-1]; mom = lambda i: (cc[i] - cc[max(i - 6, 0)]) / a
        if H[i2] >= H[i1] * (1 - 0.0005) and mom(i2) < mom(i1) - 0.3 and len(H) - 1 - i2 <= 30: signs.append("Momentum divergence: price made a similar/new extreme but the push behind it is weaker")
    # 2) volume exhaustion at the extreme: volume spike with a rejection wick, or fading volume on the last push
    wick = (H[-3:] - np.maximum(cc[-3:], oo[-3:])) / np.maximum(H[-3:] - L[-3:], 1e-9)
    vr = float(v[-3:].mean() / max(v[-48:].mean(), 1e-9))
    if float(wick.max()) > 0.5 and vr > 1.3: signs.append("High volume with a long rejection wick at the extreme (buyers/sellers absorbed)")
    elif vr < 0.7 and (cc[-1] - cc[-13]) / a > 1: signs.append("The last push happened on fading volume")
    # 3) liquidity sweep: pierced the prior swing extreme then closed back inside
    if len(pH) >= 2 and H[-6:].max() > H[pH[-2]] and cc[-1] < H[pH[-2]]: signs.append("Liquidity sweep: price poked above the previous swing extreme and closed back below it")
    # 4) structure break: close beyond the last swing low (in trend direction terms)
    if len(pL) >= 1 and cc[-1] < L[pL[-1]]: signs.append("Structure break: price closed beyond the last swing point that was holding the trend")
    elif len(pL) >= 2 and L[pL[-1]] < L[pL[-2]]: signs.append("The last swing point is now lower than the one before (trend structure weakening)")
    else: against.append("Trend structure (swing points) is still intact")
    # 5) failed retest / support-resistance failure: the broken level was retested and rejected
    if len(pL) >= 1 and cc[-6:].min() < L[pL[-1]] and cc[-1] < L[pL[-1]] and H[-3:].max() >= L[pL[-1]] - 0.2 * a: signs.append("Failed retest: the broken level was retested from the other side and rejected")
    # 6) derivatives: crowding / positioning against the trend
    if derivs:
        crowd = derivs.get("crowding")
        if (k == 1 and crowd == "long") or (k == -1 and crowd == "short"): signs.append("Positioning is crowded in the trend direction (funding/OI), so a squeeze against it is possible")
        if derivs.get("quadrant") in ("long_liquidation",) and k == 1: signs.append("Open interest falling with price falling (longs closing)")
        if derivs.get("quadrant") in ("short_covering",) and k == -1: signs.append("Open interest falling with price rising (shorts closing)")
    structure = any(s.startswith("Structure break") for s in signs); n = len(signs); score = int(min(100, n * 20 + (15 if structure else 0)))
    status = "CONFIRMED" if (n >= 4 and structure) else "WATCH" if n >= 2 else "none"
    direction = ("BULL->BEAR" if k == 1 else "BEAR->BULL") if status != "none" else "none"
    return dict(direction=direction, status=status, score=score, signs=signs, against=against, trend_tested="up" if k == 1 else "down",
                note="REVERSAL " + status + (" (" + direction + ")" if status != "none" else "") + ": evidence is probabilistic, not a guarantee.")
