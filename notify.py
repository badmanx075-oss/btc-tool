"""Extra Telegram notifications: setup forming, stage change, milestones. Every alert is de-duplicated (cooldown per key)
and can be switched on/off from /settings. Alerts never open or close a trade."""
import datetime as dt
import review

COOLDOWN_H = dict(radar=4, stage=1)
CATS = [("paper_open", "Trade khula"), ("paper_close", "Trade band"), ("advice", "Position advice"), ("setup", "Setup ban raha hai"), ("stage_alerts", "Stage change"),
        ("signals", "Early signals"), ("reversal", "Reversal"), ("learning", "Learning"), ("milestone", "Milestone"), ("morning", "Subah"), ("evening", "Shaam"), ("weekly", "Weekly")]


def _due(S, key, hours, now):
    d = S.setdefault("alert_sent", {}); last = d.get(key)
    if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < hours * 3600: return False
    d[key] = now.isoformat(timespec="seconds"); return True


def setup_alerts(S, send, now):
    if S.get("paused"): return
    P = S.setdefault("paper", {}); rad = P.get("radar") or {}; px = S.get("last_price")
    for side in ("LONG", "SHORT"):                                   # trend-pullback radar: 3 of 4 conditions true = setup banne ke kareeb
        rows = rad.get(side) or []; n = sum(c[1] for c in rows)
        if n == 3 and not (P.get("pos") or {}).get("trend_pullback") and _due(S, "radar-" + side, COOLDOWN_H["radar"], now):
            miss = [c for c in rows if not c[1]]
            send(f"👀 SETUP BAN RAHA HAI ({'BUY' if side == 'LONG' else 'SELL'}) 3/4\nBTC ${px:,.0f}\nBaaki ek shart: {miss[0][0]} ({miss[0][2]}).\nPoori ho gayi to paper trade khud khulega. Abhi kuch karna nahi hai, bas nazar rakho.", cat="setup")
    sl = S.get("stage_log") or []
    if len(sl) >= 2 and sl[-1]["ts"] != (S.get("alert_sent") or {}).get("stage_ts"):
        S.setdefault("alert_sent", {})["stage_ts"] = sl[-1]["ts"]
        if _due(S, f"stage-{sl[-2]['stage']}>{sl[-1]['stage']}", COOLDOWN_H["stage"], now):
            send(f"🔀 STAGE BADLA\n{sl[-2]['stage']}  →  {sl[-1]['stage']}\nStatus: {sl[-1]['status']} | Regime: {sl[-1]['regime']} | BTC ${sl[-1]['price']:,.0f}", cat="stage_alerts")
    nm = [x for x in (P.get("nearmiss") or []) if x.get("created") and (now - dt.datetime.fromisoformat(x["created"])).total_seconds() < 400 and not x.get("alerted")]
    for x in nm:
        x["alerted"] = True
        send(f"🟡 B/C-GRADE SETUP (trade nahi liya)\nEarly signal aaya par score {x['score']} tha, entry ke liye {x.get('min_score', 65)} chahiye. Isse sirf shadow mein track kar rahe hain, taaki pata chale bar sahi hai ya nahi.", cat="setup")


def milestone_alert(S, send, send_file, now):
    m = review.milestone(S)
    if not m: return
    rd = review.readiness(S)
    send(f"🏁 MILESTONE: {m} paper trades band ho gaye.\n{rd['message']}\nReview pack neeche bhej raha hu. Ye file mujhe (Claude ko) bhejo, main rules tune kar dunga.", cat="milestone")
    if m >= review.TARGET_FIRST: send_file(S, now, f"Review pack after {m} trades")
