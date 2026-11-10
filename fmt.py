"""Small text helpers shared by every Telegram message about a paper trade: which STRATEGY took it, and the live picture (entry, live price, P/L)."""
import config


def strat_name(t):
    lab = (t.get("cfg") or {}).get("label") or t.get("label") or t.get("strategy") or "?"
    return lab.split(" · ")[0]


def sline(t):
    return f"🧠 Strategy: {strat_name(t)} | 🪙 {t.get('sym', 'BTC')} | {t.get('id', '')}"


def live_pl(t, px):
    """(inr, R) open + booked P/L of a trade at price px (booked parts included)."""
    usd = (px - t["entry"]) * t["side"] * t["qty"] * t["remaining"] + t.get("realized_usd", 0.0)
    return usd * t.get("fx", 88.0), (px - t["entry"]) * t["side"] / t["risk"]


def live_line(t, px):
    inr_, R = live_pl(t, px); tgt = t.get("tp") or t.get("t2")
    return (f"💵 {'BUY' if t['side'] == 1 else 'SELL'} price ${config.pf(t['entry'])} → live ${config.pf(px)} | {'🟢' if inr_ >= 0 else '🔴'} P/L {'+' if inr_ >= 0 else '-'}{config.inr(abs(inr_))} ({R:+.2f}R)"
            f" | stop ${config.pf(t['sl'])}" + (f" | target ${config.pf(tgt)}" if tgt else ""))
