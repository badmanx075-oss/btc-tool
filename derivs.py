"""Plain-language reading of derivatives data (spec 2, 22, 29, 34): funding, open interest vs price, taker flow, liquidations.
Everything is a heuristic reading of positioning, not a prediction. Missing data is reported as missing, never guessed."""
import numpy as np


def interpret(fr, oi, log=None, flow=None, px=None):
    """fr: funding rate per 8h (fraction). oi: open interest USD. log: market_log.csv DataFrame. flow: flow_log.csv DataFrame."""
    items, score = [], 0.0; crowd = "balanced"; quad = None
    f = (fr or 0) * 100
    if fr is not None:
        if f >= 0.03: crowd = "long"; items.append(f"Funding {f:.4f}% per 8h is high: longs are paying a lot, the long side is crowded (squeezes against longs become more likely)"); score -= 1
        elif f <= -0.01: crowd = "short"; items.append(f"Funding {f:.4f}% per 8h is negative: shorts are paying, the short side is crowded (squeezes against shorts become more likely)"); score += 1
        else: items.append(f"Funding {f:.4f}% per 8h is normal: no obvious crowding")
    ch4 = ch24 = pc4 = None
    if log is not None and len(log) > 49 and "oi_usd" in log:
        try:
            oi_now = float(log.oi_usd.iloc[-1]); ch4 = oi_now / float(log.oi_usd.iloc[-49]) - 1; pc4 = float(log.price.iloc[-1] / log.price.iloc[-49] - 1)
            if len(log) > 288: ch24 = oi_now / float(log.oi_usd.iloc[-289]) - 1
            if abs(ch4) > 0.003 and abs(pc4) > 0.002:
                quad = ("new_longs" if pc4 > 0 else "new_shorts") if ch4 > 0 else ("short_covering" if pc4 > 0 else "long_liquidation")
                items.append({"new_longs": "Price up and open interest up: new longs are entering, the move has fresh participation (healthier)",
                              "new_shorts": "Price down and open interest up: new shorts are entering, selling pressure has fresh participation",
                              "short_covering": "Price up but open interest down: the rise is short-covering, not new buying (weaker, can fade)",
                              "long_liquidation": "Price down and open interest down: longs are closing or being liquidated (can be near exhaustion of the fall)"}[quad])
                score += {"new_longs": 1, "new_shorts": -1, "short_covering": 0.3, "long_liquidation": -0.3}[quad]
            else: items.append(f"Open interest {ch4 * 100:+.2f}% over 4h with small price change: no clear signal")
        except Exception: pass
    else: items.append("Open interest history is still being collected (needs a few hours of scans)")
    delta = None; liq = None
    if flow is not None and len(flow) >= 6:
        try:
            t = flow.tail(12); b, s = float(t.buy_ct.sum()), float(t.sell_ct.sum()); delta = (b - s) / max(b + s, 1e-9)
            items.append(f"Taker flow (last ~1h of samples): {'buyers' if delta > 0.05 else 'sellers' if delta < -0.05 else 'balanced'} ({delta:+.2f})")
            score += float(np.clip(delta * 3, -1, 1))
            lq = t[["liq_long_usd", "liq_short_usd"]].astype(float); ll, ls = float(lq.liq_long_usd.max(skipna=True) or 0), float(lq.liq_short_usd.max(skipna=True) or 0)
            if ll == ll and ls == ls and (ll > 1e6 or ls > 1e6): liq = dict(long_usd=ll, short_usd=ls); items.append(f"Recent liquidations: longs ${ll / 1e6:.1f}M, shorts ${ls / 1e6:.1f}M (forced closing can extend or end a move)")
        except Exception: pass
    else: items.append("Order-flow (taker buy/sell) history is still being collected")
    return dict(crowding=crowd, quadrant=quad, oi_change_4h=None if ch4 is None else round(ch4 * 100, 2), oi_change_24h=None if ch24 is None else round(ch24 * 100, 2), price_change_4h=None if pc4 is None else round(pc4 * 100, 2),
                taker_delta=None if delta is None else round(delta, 3), liquidations=liq, bias=round(float(np.clip(score, -2, 2)), 2), items=items)
