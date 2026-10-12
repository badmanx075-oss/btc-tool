"""Decision Desk data (spec 4, 12, 27, 29, 34, 37): everything the dashboard needs beyond the basic scan, computed once per scan.
levels ladder, point-move classes, derivatives reading, reversal evidence, multi-timeframe table."""
import numpy as np
import engine as E, levels, moves, derivs, reversal

ROLES = {"4H": "Market regime (big picture)", "1H": "Structure and key levels", "30m": "Setup context", "15m": "Setup", "5m": "Entry refinement"}


def mtf(frames, lean=None):
    tv = E.tf_view(frames); rows = []
    for tf in ("4H", "1H", "30m", "15m", "5m"):
        v = tv.get(tf)
        if v: rows.append(dict(tf=tf, role=ROLES[tf], direction=v["label"], strength=v["er"]))
    ups = sum(r["direction"] == "UP" for r in rows); dns = sum(r["direction"] == "DOWN" for r in rows); n = max(len(rows), 1)
    align = "ALIGNED UP" if ups == n else "ALIGNED DOWN" if dns == n else "MOSTLY UP" if ups >= n - 1 and ups > dns else "MOSTLY DOWN" if dns >= n - 1 and dns > ups else "MIXED (timeframes disagree: lower confidence)"
    return dict(rows=rows, alignment=align)


def build(frames, fr, oi, log=None, flow=None, stats=None, regime="UNCLEAR / NO-TRADE"):
    """frames: dict of DataFrames keyed '5m','15m','30m','1H','4H' (last row = live candle)."""
    h1, h4 = frames["1H"], frames["4H"]; px = float(h1.c.iloc[-1]); a1 = float(E.atr_series(h1.iloc[:-1]).iloc[-1]); a4 = float(E.atr_series(h4.iloc[:-1]).iloc[-1])
    out = dict(price=px, atr1h=a1, atr4h=a4)
    for key, fn in (("derivs", lambda: derivs.interpret(fr, oi, log, flow, px)), ):
        try: out[key] = fn()
        except Exception as e: out[key] = None; print("desk", key, "error", e)
    for key, fn in (("levels", lambda: levels.ladder(h1, px, a1, a4)), ("moves", lambda: moves.table(px, a1, a4, stats)),
                    ("reversal", lambda: reversal.evidence(h1, regime, out.get("derivs"))), ("mtf", lambda: mtf(frames))):
        try: out[key] = fn()
        except Exception as e: out[key] = None; print("desk", key, "error", e)
    return out
