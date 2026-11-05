"""Full analysis for the extra coins (ETH, SOL ...): the SAME functions that analyse BTC (regime/signal, multi-timeframe trend, support/resistance,
decision-desk data, snapshot with stage/checklist) run on that coin's own candles. Stored in state.json under S["coindesk"][COIN] so the dashboard can show every
tab for the coin you select. Things that need BTC-only history files (order-flow tape, hour-of-day stats, move statistics) are left out for the coins and say so.
Never raises: a coin whose data fails this scan keeps its previous snapshot."""
import datetime as dt
import engine as E, analysis, desk, sr


def build(sym, now, has_pos=False):
    m5, m15, h1, h4 = (E.candles_sym(sym, b, 300) for b in ("5m", "15m", "1H", "4H"))
    try: d1 = E.candles_sym(sym, "1D", 250)
    except Exception: d1 = None
    px = float(m5.c.iloc[-1]); fr, oi = E.funding_sym(sym), E.oi_sym(sym); r = E.scan(m15, h4, h1)
    market = dict(price=px, regime=r["regime"], signal=r["signal"], side=r["side"], score=r["score"], scores=r["scores"], atr1h=r["atr1h"], atr4h=r["atr4h"], reversal=r["reversal"],
                  tf=E.tf_view({"5m": m5, "15m": m15, "1H": h1, "4H": h4}), funding=fr, oi=oi, pro=r["pro"], con=r["con"], ts=now.isoformat(timespec="seconds"))
    scan = {k: r.get(k) for k in ("signal", "side", "score", "entry", "zone", "sl", "t1", "t2", "t3", "ext", "confirm", "move_class", "risk", "regime") if k in r}
    out = dict(sym=sym, ts=now.isoformat(timespec="seconds"), market=market, scan=scan, analysis=None, desk=None, sr=None)
    try: out["analysis"] = analysis.snapshot(h1, fr, oi, None, None, r["regime"], r["scores"], has_pos)
    except Exception as e: print("coindesk analysis error", sym, e)
    try:
        frames = {"5m": m5, "15m": m15, "1H": h1, "4H": h4}; out["desk"] = desk.build(frames, fr, oi, None, None, None, r["regime"])
    except Exception as e: print("coindesk desk error", sym, e)
    try:
        frs = {"5m": m5, "15m": m15, "1H": h1, "4H": h4, **({"1D": d1} if d1 is not None else {})}; out["sr"] = sr.build(frs, px)
    except Exception as e: print("coindesk sr error", sym, e)
    return out


def run(S, now, coins):
    store = S.setdefault("coindesk", {}); pos = (S.get("paper") or {}).get("pos") or {}
    for sym in coins:
        try: store[sym] = build(sym, now, any(t and t.get("sym", "BTC") == sym for t in pos.values()))
        except Exception as e: print("coindesk error", sym, type(e).__name__, str(e)[:120])
