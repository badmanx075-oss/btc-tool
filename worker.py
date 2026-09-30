"""Runs every 5 min (GitHub Actions): scan, track trades, Telegram alerts + button callbacks."""
import os, json, time, requests, datetime as dt
from zoneinfo import ZoneInfo
import engine as E

TOK, CHAT = os.environ["TG_TOKEN"], str(os.environ["TG_CHAT_ID"])
URL = os.environ.get("DASHBOARD_URL", "")
TZ = ZoneInfo(os.environ.get("TZ_NAME", "Asia/Kolkata"))
MH, EH = int(os.environ.get("MORNING_HOUR", 8)), int(os.environ.get("EVENING_HOUR", 20))
API = f"https://api.telegram.org/bot{TOK}/"
DISC = "\nStatistical setup, NOT a guaranteed prediction."

def tg(method, **kw):
    for _ in range(3):
        try:
            r = requests.post(API + method, json=kw, timeout=20)
            if r.status_code == 429: time.sleep(r.json().get("parameters", {}).get("retry_after", 3)); continue
            if r.ok: return r.json()
        except requests.RequestException: pass
        time.sleep(2)

def send(text, tid=None):
    kw = dict(chat_id=CHAT, text=text)
    if tid:
        rows = [[{"text": "🟢 TRADE TAKEN", "callback_data": f"taken|{tid}"}, {"text": "⚪ IGNORE", "callback_data": f"ign|{tid}"}],
                [{"text": "🟢 PROFIT", "callback_data": f"win|{tid}"}, {"text": "🔴 LOSS", "callback_data": f"loss|{tid}"}]]
        if URL.startswith("http"): rows.append([{"text": "🔎 CHECK THIS TRADE", "url": f"{URL}?trade={tid}"}])
        kw["reply_markup"] = {"inline_keyboard": rows}
    tg("sendMessage", **kw)

S = json.load(open("state.json")) if os.path.exists("state.json") else {"trades": {}, "offset": 0, "n": {}, "sent": {}}
now = dt.datetime.now(dt.timezone.utc)
P = lambda x: f"${x:,.0f}"

def ev(t, typ, price, note="", once=True):
    if once and any(e["type"] == typ for e in t["events"]): return False
    t["events"].append(dict(id=f"{t['id']}-{len(t['events'])+1}", type=typ, ts=now.isoformat(timespec="seconds"), price=price, note=note))
    return True

def review(t):
    f = lambda x: f"{x:,.0f}"
    tl = "\n".join(f"{e['ts'][11:16]} {e['type']} @ {f(e['price'])}" for e in t["events"])
    return (f"📝 {t['id']}\n{t['signal']} | {t['regime']} | score {t['score']}\nWhy: {', '.join(t['pro'])}\nAgainst: {', '.join(t['con']) or '-'}\n"
            f"Entry {f(t['entry'])} SL {f(t['sl0'])} T1 {f(t['t1'])} T2 {f(t['t2'])} T3 {f(t['t3'])}\n"
            f"MFE {f(t['mfe'])} MAE {f(t['mae'])} pts\nSystem outcome: {t['outcome'] or 'open'}\nUser: {t['user']}\n\nTimeline:\n{tl}")

def handle_updates():
    r = tg("getUpdates", offset=S["offset"] + 1, timeout=0) or {"result": []}
    for u in r["result"]:
        S["offset"] = u["update_id"]
        cb, msg = u.get("callback_query"), u.get("message")
        if cb and str(cb["message"]["chat"]["id"]) == CHAT:
            act, tid = cb["data"].split("|"); t = S["trades"].get(tid)
            if t:
                lp = S.get("last_price", t["entry"])
                if act == "taken": t["user"].update(taken=True, entry=lp); ev(t, "USER TRADE TAKEN", lp, once=True)
                elif act == "ign": t["user"]["taken"] = False; ev(t, "USER IGNORED", lp)
                elif act in ("win", "loss"): t["user"]["result"] = act.upper(); ev(t, "USER FEEDBACK " + act.upper(), lp, once=False)
                tg("answerCallbackQuery", callback_query_id=cb["id"], text=f"{tid}: {act} saved")
        elif msg and str(msg["chat"]["id"]) == CHAT:
            txt = msg.get("text", "").split()
            if not txt: continue
            if txt[0] == "/active": send("\n".join(f"{i}: {t['signal']} {t['status']}" for i, t in S["trades"].items() if not t["outcome"]) or "No active trades")
            elif txt[0] == "/review" and len(txt) > 1 and txt[1] in S["trades"]: send(review(S["trades"][txt[1]]))
            else: send("Commands: /active, /review TRADE_ID\nUse buttons under alerts for Taken / Profit / Loss.")

def alert(t, title, extra=""):
    send(f"{title}\nTrade ID: {t['id']}\nPrice: {P(S['last_price'])}\n{extra}", t["id"])

def track(t, m5):
    k = 1 if t["side"] == "LONG" else -1
    for c in m5[m5.ts > t["last_ts"]].itertuples():
        fav = (c.h - t["entry"]) if k == 1 else (t["entry"] - c.l); adv = (t["entry"] - c.l) if k == 1 else (c.h - t["entry"])
        t["mfe"], t["mae"] = max(t["mfe"], fav), max(t["mae"], adv)
        if (c.l <= t["sl"]) if k == 1 else (c.h >= t["sl"]):   # conservative: SL checked first
            prot = t["sl"] != t["sl0"]
            ev(t, "PROTECTED EXIT" if prot else "SL HIT", t["sl"]); t["outcome"] = t["outcome"] or ("PROTECTED EXIT" if prot else "SL HIT")
            t["status"] = "CLOSED"; alert(t, "🛑 STOP / INVALIDATION HIT" if not prot else "🔒 PROTECTED STOP HIT", f"System outcome: {t['outcome']}"); t["last_ts"] = c.ts; return
        for n, key, new_sl in (("T1", "t1", t["entry"]), ("T2", "t2", t["t1"]), ("T3", "t3", t["t2"])):
            if ((c.h >= t[key]) if k == 1 else (c.l <= t[key])) and ev(t, n + " HIT", t[key]):
                t["outcome"] = n + " REACHED"; t["sl"] = new_sl; t["status"] = {"T1": "HOLD / PROTECT PROFIT", "T2": "EXTENDED MOVE WATCH", "T3": "EXHAUSTION WATCH"}[n]
                ev(t, "SL MOVED", new_sl, once=False)
                alert(t, f"🎯 {n} HIT", f"Level {P(t[key])}. Stop moved to {P(new_sl)}. Status: {t['status']}. Booking is your call.")
        t["last_ts"] = c.ts
    v = m5.v
    if t["outcome"] and not t["status"] == "CLOSED" and v.tail(3).mean() < 0.6 * v.tail(30).mean() and ev(t, "EXHAUSTION WATCH", S["last_price"]):
        alert(t, "⚠️ PROFIT EXHAUSTION WATCH", "Volume fading; continuation probability decreasing. Consider protecting profit.")
    if (now - dt.datetime.fromisoformat(t["created"])).total_seconds() > 72 * 3600 and t["status"] != "CLOSED":
        t["status"] = "CLOSED"; t["outcome"] = t["outcome"] or "EXPIRED"; ev(t, "TRADE CLOSED", S["last_price"])

def main():
    handle_updates()
    try:
        m5, m15, h1, h4 = (E.candles(b) for b in ("5m", "15m", "1H", "4H"))
        fr, oi = E.funding(), E.open_interest()
    except Exception as e:
        print("data error", e); json.dump(S, open("state.json", "w"), indent=1); return
    S["last_price"] = px = float(m5.c.iloc[-1])
    for t in S["trades"].values():
        if t["status"] != "CLOSED": track(t, m5)
    r = E.scan(m15, h4, h1)
    S["market"] = dict(price=px, regime=r["regime"], signal=r["signal"], side=r["side"], score=r["score"], funding=fr, oi=oi,
                       pro=r["pro"], con=r["con"], ts=now.isoformat(timespec="seconds"))
    open_t = [t for t in S["trades"].values() if t["status"] != "CLOSED"]
    last = max((t["created"] for t in S["trades"].values()), default="2000")
    if r["signal"] != "NO TRADE" and not open_t and (now - dt.datetime.fromisoformat(last if "T" in last else "2000-01-01T00:00:00+00:00")).total_seconds() > 3600:
        d = now.strftime("%Y%m%d"); S["n"][d] = S["n"].get(d, 0) + 1; tid = f"BTC-{r['side']}-{d}-{S['n'][d]:03d}"
        t = dict(id=tid, side=r["side"], signal=r["signal"], regime=r["regime"], score=r["score"], pro=r["pro"], con=r["con"],
                 entry=r["entry"], zone=r["zone"], sl=r["sl"], sl0=r["sl"], t1=r["t1"], t2=r["t2"], t3=r["t3"], ext=r["ext"], confirm=r["confirm"],
                 move_class=r["move_class"], risk=r["risk"], created=now.isoformat(timespec="seconds"), last_ts=float(m5.ts.iloc[-1]),
                 mfe=0, mae=0, status="EARLY SETUP", outcome="", events=[], user={})
        ev(t, r["signal"], px); S["trades"][tid] = t
        mv = abs(t["t1"] - t["entry"]), abs(t["t3"] - t["entry"])
        send(f"🚨 BTC TRADE ALERT\nTrade ID: {tid}\nSignal: {r['signal']}\nRegime: {r['regime']}\nPrice: {P(px)}\n"
             f"Entry Zone: {P(t['zone'][0])} – {P(t['zone'][1])}\nInvalidation/SL: {P(t['sl'])}\nT1 {P(t['t1'])} | T2 {P(t['t2'])} | T3 {P(t['t3'])}\nExtended: {P(t['ext'])}+\n"
             f"Confirmation: {'above' if r['side']=='LONG' else 'below'} {P(t['confirm'])}\nMove to T1–T3: {mv[0]:,.0f} to {mv[1]:,.0f} pts ({t['move_class']} vs 4H ATR)\n"
             f"Setup Score: {r['score']}/100 | False-signal risk: {r['risk']}\nFor: {', '.join(r['pro'])}\nAgainst: {', '.join(r['con']) or '-'}{DISC}", tid)
    loc = now.astimezone(TZ); key = loc.strftime("%Y-%m-%d")
    for name, hr in (("morning", MH), ("evening", EH)):
        if loc.hour == hr and S["sent"].get(name) != key:
            S["sent"][name] = key
            today = [t for t in S["trades"].values() if t["created"][:10] == now.strftime("%Y-%m-%d")]
            cnt = lambda s: sum(any(e["type"] == s for e in t["events"]) for t in today)
            if name == "morning":
                send(f"🌅 GOOD MORNING\nBTC Perpetual Brief\nPrice: {P(px)}\nRegime: {r['regime']}\nSignal: {r['signal']}\nActive trades: {len(open_t)}\nFunding: {fr*100:.4f}%\nSignals are statistical, not guaranteed.")
            else:
                send(f"🌆 GOOD EVENING\nDaily Review\nPrice: {P(px)}\nRegime: {r['regime']}\nSignals: {len(today)}\nT1: {cnt('T1 HIT')} T2: {cnt('T2 HIT')} T3: {cnt('T3 HIT')} SL: {cnt('SL HIT')}")
    json.dump(S, open("state.json", "w"), indent=1)

main()
