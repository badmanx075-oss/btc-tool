"""Post-entry CONFIRMATION tracker. After the tool opens a (paper) trade, this watches whether the market is really
following through. It only reports (Telegram + dashboard + trade timeline). It never changes or closes the trade.
Checks (each True/False): confirm level broken, in profit >= +0.5R, momentum with trade, 15m+1H direction with trade,
order flow (taker) with trade, no reversal flags."""
import datetime as dt

NEED = 4            # checks needed (out of 6) for CONFIRMED
LOST_AT = 2         # at or below this after being confirmed -> CONFIRMATION LOST


def checks(t, S, px):
    k, m = t["side"], t.get("mgmt") or {}; D = S.get("desk") or {}; rows = {r["tf"]: r["direction"] for r in (D.get("mtf") or {}).get("rows", [])}
    want = "UP" if k == 1 else "DOWN"; d = D.get("derivs") or {}; uR = (px - t["entry"]) * k / t["risk"]; lvl = t.get("confirm_lvl")
    out = []
    if lvl: out.append(["Confirm level toda", bool((px > lvl) if k == 1 else (px < lvl)), f"level ${lvl:,.0f}, ab ${px:,.0f}"])
    else: out.append(["Entry ke baad bhaav aage chala", uR > 0.25, f"{uR:+.2f}R"])
    out += [["Profit +0.5R se zyada", uR >= 0.5, f"{uR:+.2f}R"],
            ["Momentum trade ke saath", (m.get("momentum_atr") or 0) * 1 > 0.3, f"{m.get('momentum_atr', 0):+.1f} ATR (3h)" if m else "n/a"],
            ["15m aur 1H direction trade ke saath", rows.get("15m") == want and rows.get("1H") in (want, "FLAT"), f"15m {rows.get('15m', '?')}, 1H {rows.get('1H', '?')}"],
            ["Order flow (taker) trade ke saath", (d.get("taker_delta") or 0) * k > 0.03, f"taker delta {d.get('taker_delta', 0):+.2f}"],
            ["Reversal ke sanket nahi", bool(m) and not any((m.get("reversal_flags") or {}).values()), "koi flag nahi" if m and not any((m.get("reversal_flags") or {}).values()) else "flag hai"]]
    return out


def step(S, P, C, t, px, now, send, ev, ist):
    ch = checks(t, S, px); n = sum(c[1] for c in ch); prev = (t.get("confirm_info") or {}).get("state", "WAITING")
    state = prev
    if prev != "CONFIRMED" and n >= NEED and ch[0][1]: state = "CONFIRMED"
    elif prev == "CONFIRMED" and n <= LOST_AT: state = "LOST"
    elif prev == "LOST" and n >= NEED and ch[0][1]: state = "CONFIRMED"
    t["confirm_info"] = dict(state=state, score=n, total=len(ch), checks=ch, ts=now.isoformat(timespec="seconds"), first=(t.get("confirm_info") or {}).get("first"))
    if state == prev: return
    if state == "CONFIRMED":
        t["confirm_info"]["first"] = t["confirm_info"]["first"] or now.isoformat(timespec="seconds"); R = (px - t["entry"]) * t["side"] / t["risk"]; t["confirmed_at_R"] = round(R, 2)
        ev(t, now, "CONFIRMED", px, f"{n}/{len(ch)} checks")
        txt = (f"✅ TRADE CONFIRM HUA  🕒 {ist(now)} IST\n{t['id']} ({'LONG' if t['side'] == 1 else 'SHORT'})\nBhaav ${px:,.0f} | Open P/L {R:+.2f}R | {n}/{len(ch)} checks pass\n"
               + "\n".join(f"{'✅' if c[1] else '❌'} {c[0]}: {c[2]}" for c in ch) + "\nMatlab: entry ke baad market follow-through de raha hai. Trade apne rule par chalta rahega (stop/target same).")
    else:
        ev(t, now, "CONFIRMATION LOST", px, f"{n}/{len(ch)} checks")
        txt = (f"⚠️ CONFIRMATION KAMZOR  🕒 {ist(now)} IST\n{t['id']}: ab sirf {n}/{len(ch)} checks pass.\n" + "\n".join(f"{'✅' if c[1] else '❌'} {c[0]}: {c[2]}" for c in ch)
               + "\nMatlab: follow-through ruk gaya. Stop/target wahi hain; position ko dhyan se dekho.")
    send(txt, cat="confirm")
