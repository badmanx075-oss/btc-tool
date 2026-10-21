"""Runs every 5 min (GitHub Actions): scan, track trades, Telegram alerts + button callbacks."""
import os, json, time, subprocess, requests, datetime as dt
from zoneinfo import ZoneInfo
import engine as E
import paper, learn, config, wallet, analysis, history, stats, flow, desk, review as rvw, notify, timing, sr, orderflow, ask, askstats, dailylog
import pandas as pd
import faulthandler; faulthandler.dump_traceback_later(330, exit=True)  # if stuck >5.5 min: print where, then exit

TOK, CHAT = os.environ["TG_TOKEN"].strip(), str(os.environ["TG_CHAT_ID"]).strip()
URL = os.environ.get("DASHBOARD_URL", "")
TZ = ZoneInfo(os.environ.get("TZ_NAME", "Asia/Kolkata"))
MH, EH = int(os.environ.get("MORNING_HOUR", 8)), int(os.environ.get("EVENING_HOUR", 20))
API = f"https://api.telegram.org/bot{TOK}/"
HEADER = "🤖 Notified from BTC Tool\n\n"
DISC = "\nEXPERIMENTAL: backtests show NO proven edge yet. Paper-trade only. Not a prediction."

def tg(method, **kw):
    ST = S.setdefault("telegram", {}); key = {"sendMessage": "last_error", "getUpdates": "poll_error"}.get(method, "api_error")
    for _ in range(3):
        try:
            r = requests.post(API + method, json=kw, timeout=20 + int(kw.get("timeout", 0)))
            if r.status_code == 429: time.sleep(min(int(r.json().get("parameters", {}).get("retry_after", 3)), 20)); continue
            if r.ok:
                ST[key] = ""
                if method == "sendMessage": ST["last_send_ok"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
                return r.json()
            ST[key] = f"{method}: {r.status_code} {r.text[:120]}"
        except requests.RequestException as e: ST[key] = f"{method}: network {type(e).__name__}"
        time.sleep(2)

def send(text, tid=None, cat=None, buttons=None):
    if cat and not config.load()["alerts"].get(cat, True): return      # user turned this category off (/notify)
    kw = dict(chat_id=CHAT, text=HEADER + text)
    if buttons: kw["reply_markup"] = {"inline_keyboard": [[b if isinstance(b, dict) else {"text": b[0], "callback_data": b[1]} for b in row] for row in buttons]}
    elif tid:
        rows = [[{"text": "🟢 TRADE TAKEN", "callback_data": f"taken|{tid}"}, {"text": "⚪ IGNORE", "callback_data": f"ign|{tid}"}],
                [{"text": "🟢 PROFIT", "callback_data": f"win|{tid}"}, {"text": "🔴 LOSS", "callback_data": f"loss|{tid}"}]]
        if URL.startswith("http"): rows.append([{"text": "🔎 CHECK THIS TRADE", "url": f"{URL}?trade={tid}"}])
        kw["reply_markup"] = {"inline_keyboard": rows}
    r = tg("sendMessage", **kw); lg = S.setdefault("telegram", {}).setdefault("log", [])       # delivery log: last 30 sends (shown in dashboard Health)
    lg.append(dict(ts=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), cat=cat or "-", ok=bool(r and r.get("ok")), text=text[:70].replace("\n", " "))); del lg[:-30]

def send_file(S_, now_, caption="Review pack"):
    """Builds the review pack and sends it to Telegram as two files (full JSON + short readable .md)."""
    pk = rvw.pack(S_, now_); json.dump(pk, open("review_pack.json", "w"), indent=1, default=str); open("review_pack.md", "w").write(rvw.pack_md(pk))
    ok = True
    for fn in ("review_pack.md", "review_pack.json"):
        try:
            with open(fn, "rb") as fh: r = requests.post(API + "sendDocument", data=dict(chat_id=CHAT, caption=HEADER + caption if fn.endswith("md") else fn), files=dict(document=fh), timeout=60)
            ok = ok and r.ok
            if not r.ok: S_.setdefault("telegram", {})["api_error"] = f"sendDocument: {r.status_code} {r.text[:100]}"
        except requests.RequestException as e: ok = False; S_.setdefault("telegram", {})["api_error"] = f"sendDocument: network {type(e).__name__}"
    return ok

def settings_kb():
    on = config.load()["alerts"]; btns = [{"text": ("✅ " if on.get(k, True) else "❌ ") + lab, "callback_data": "tgl|" + k} for k, lab in notify.CATS]
    return {"inline_keyboard": [btns[i:i + 2] for i in range(0, len(btns), 2)]}

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

HELP = ("📖 COMMANDS\n/status  wallet + position + radar\n/wallet /ledger /trades  money, every rupee movement, trade list\n/history [n]  last n trades (permanent record)\n/timeline ID  full story of one trade\n"
        "/stats  win rate, avg R, drawdown, streaks (+ honest verdict)\n/today  today's summary\n/analysis  market analysis\n/active  open early-signal alerts\n/review ID  review an alert\n"
        "/note ID text  add your remark | /myexit ID price  your own exit\n/pause  stop NEW trades and alerts (open trades keep being managed) | /resume\n"
        "/config /set name value /notify name on|off  settings\n/lessons /approve N /revert N  what the tool learned\n/weekly  weekly report\n/ask sawaal  KOI BHI sawaal (ya seedha message bhejo) | /daily  kal kitna upar/neeche gaya | /daily 14, /daily stats, /daily csv  saved daily history\n/radar  good move aane wala hai? | /flow  aggressive buy/sell kahan | /levels  timeframe-wise support/resistance | /methods  saare tareeke ka vote | /timing  kis samay kitni move hoti hai | /export  review pack (file) to send to Claude | /readiness  kitna data bacha\n/settings  notification ON/OFF buttons | /deliveries  last sends\n/demo  test the pipeline\n/ping  is the bot alive\n/resetwallet confirm")
MENU = [("status", "Wallet, position, radar"), ("history", "Last trades"), ("timeline", "One trade in detail"), ("stats", "Performance"), ("today", "Today's summary"), ("wallet", "Wallet"), ("analysis", "Market analysis"),
        ("ask", "Kuch bhi poochho"), ("daily", "Kal kitna move hua"), ("radar", "Good move radar"), ("flow", "Aggressive buy/sell"), ("levels", "Support/Resistance"), ("methods", "Multi-method check"), ("timing", "Active time windows"), ("export", "Review pack file"), ("readiness", "Data readiness"), ("settings", "Notification buttons"), ("pause", "Pause new trades"), ("resume", "Resume trades"), ("help", "All commands"), ("ping", "Is the bot alive")]

ASK_Q = {"5m": "5 min me kya hoga?", "1h": "1 ghante me upar ya neeche?", "4h": "4 ghante me upar ya neeche?", "mkt": "market kaisa hai?", "adv": "abhi trade lena chahiye?", "day": "kal kitna move hua?", "lvl": "support resistance kahan hai?"}
def ask_kb():
    b = [("⏱ 5 min", "ask|5m"), ("⏱ 1 ghanta", "ask|1h"), ("⏱ 4 ghante", "ask|4h"), ("📊 Market kaisa", "ask|mkt"), ("🎯 Trade lu?", "ask|adv"), ("📆 Kal ka move", "ask|day"), ("🧭 Levels", "ask|lvl")]
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in b[i:i + 2]] for i in range(0, len(b), 2)]}
def send_doc(path, caption):
    try:
        with open(path, "rb") as fh: r = requests.post(API + "sendDocument", data=dict(chat_id=CHAT, caption=HEADER + caption), files=dict(document=fh), timeout=60)
        if not r.ok: S.setdefault("telegram", {})["api_error"] = f"sendDocument: {r.status_code} {r.text[:100]}"
        return r.ok
    except Exception as e: S.setdefault("telegram", {})["api_error"] = f"sendDocument: {type(e).__name__}"; return False
def daily_cmd(args):
    arc = dailylog.load(); a = (args[0].lower() if args else "")
    if a in ("csv", "file", "export"):
        if not os.path.exists(dailylog.CSVF): return send("Daily archive abhi khaali hai.")
        return send_doc(dailylog.CSVF, f"Daily archive: {len(arc['days'])} din (Excel mein khulega, ya mujhe bhejo analysis ke liye)") or send("File bhejne mein dikkat aayi. Dashboard ke Ask tab se download karo.")
    if a in ("stats", "analysis", "analyze"): return send(dailylog.text_stats(arc))
    if a.isdigit(): return send(dailylog.text_days(arc, max(1, min(int(a), 30))))
    send(askstats.daily_text(S.get("daily")) + f"\n\n🗂 {len(arc['days'])} din hamesha ke liye saved hain. /daily 14 (pichhle din) | /daily stats (analysis) | /daily csv (poori file)")
def answer_q(q):
    try: send(ask.answer(q, S, config.load(), askstats.load(), log=True, arc=dailylog.load()))
    except Exception as e: send(f"Ask mein dikkat aayi ({type(e).__name__}). Dobara try karo.")

def today_text():
    P_ = S.get("paper") or {}; d = (now + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    mine = [r for r in history.load()["records"].values() if history.ist(r.get("opened"))[:11] == (now + dt.timedelta(hours=5, minutes=30)).strftime("%d %b %Y")]
    closed = [r for r in mine if r["source"] == "PAPER" and r["status"] == "CLOSED"]
    return (f"📅 TODAY ({d} IST)\nNew trades/alerts: {len(mine)} | paper closed today: {len(closed)} | net ₹{sum(r.get('pnl_inr') or 0 for r in closed):,.0f}\n"
            f"{wallet.summary(P_)}\n{'⏸ PAUSED: no new trades' if S.get('paused') else '▶️ Running'}")

def handle_updates(timeout=0):
    ST = S.setdefault("telegram", {}); stamp = lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    r = tg("getUpdates", offset=S["offset"] + 1, timeout=timeout)
    if r is None: return 0
    for u in r["result"]:
        S["offset"] = u["update_id"]; cb, msg = u.get("callback_query"), u.get("message")
        src = (cb.get("message") if cb else msg) or {}; chat = str(src.get("chat", {}).get("id", ""))
        if not chat: continue
        if chat != CHAT: ST["foreign_chat"] = "…" + chat[-4:]; continue
        ST["last_cmd_ts"] = stamp()
        if cb:
            ST["last_cmd"] = "button"; act, tid = cb["data"].split("|")
            if act == "tgl":
                cur = config.load()["alerts"].get(tid, True); config.set_notify(tid, "off" if cur else "on")
                tg("answerCallbackQuery", callback_query_id=cb["id"], text=f"{tid}: {'OFF' if cur else 'ON'}")
                tg("editMessageReplyMarkup", chat_id=CHAT, message_id=src.get("message_id"), reply_markup=settings_kb()); continue
            if act == "ask":
                tg("answerCallbackQuery", callback_query_id=cb["id"], text="Soch raha hu…"); answer_q(ASK_Q.get(tid, tid)); continue
            if act in ("fbgood", "fbbad"):
                rep = paper.user_event(S, act, tid, now); tg("answerCallbackQuery", callback_query_id=cb["id"], text=rep[:180]); send(rep); continue
            t = S["trades"].get(tid)
            if t:
                lp = S.get("last_price", t["entry"])
                if act == "taken": t["user"].update(taken=True, entry=lp); ev(t, "USER TRADE TAKEN", lp, once=True)
                elif act == "ign": t["user"]["taken"] = False; ev(t, "USER IGNORED", lp)
                elif act in ("win", "loss"): t["user"]["result"] = act.upper(); ev(t, "USER FEEDBACK " + act.upper(), lp, once=False)
                tg("answerCallbackQuery", callback_query_id=cb["id"], text=f"{tid}: {act} saved")
            continue
        txt = msg.get("text", "").split()
        if not txt: continue
        c = txt[0].split("@")[0].lower(); ST["last_cmd"] = c; ts_ = (S.get("market") or {}).get("ts")
        if c == "/ping": send(f"🏓 pong. Bot is listening. Last market scan: {((now - dt.datetime.fromisoformat(ts_)).total_seconds() / 60):.0f} min ago." if ts_ else "🏓 pong. Bot is listening (no market scan saved yet).")
        elif c == "/status": send(paper.status_text(S))
        elif c == "/demo": S.setdefault("paper", {})["force_demo"] = True; send("Demo paper trade queued. It opens within seconds to a few minutes and closes within ~1 hour. Your wallet is NOT affected.")
        elif c == "/lessons": send(learn.lessons_text(S.get("paper") or {}))
        elif c == "/approve" and len(txt) > 1: send(learn.approve(S.setdefault("paper", {}), txt[1]))
        elif c == "/revert" and len(txt) > 1: send(learn.revert(S.setdefault("paper", {}), txt[1]))
        elif c == "/export": send("📦 Review pack bana raha hu…"); send_file(S, now) or send("Export bhejne mein dikkat aayi. Dashboard ke Review tab se download karo.")
        elif c in ("/readiness", "/ready"): send(rvw.readiness(S)["message"] + f"\nShadow (near-miss/filter) trades finished: {rvw.readiness(S)['shadow_finished']}")
        elif c in ("/settings", "/setting"): tg("sendMessage", chat_id=CHAT, text=HEADER + "🔔 NOTIFICATION SETTINGS\nButton dabao: ON/OFF badal jayega.", reply_markup=settings_kb())
        elif c == "/deliveries": send("📬 Last sends:\n" + "\n".join(f"{x['ts'][11:16]} {'✅' if x['ok'] else '❌'} [{x['cat']}] {x['text']}" for x in (ST.get("log") or [])[-10:]))
        elif c == "/radar": send(__import__("moveradar").text((S.get("paper") or {}).get("radar_move"), S.get("move_watch")))
        elif c == "/flow": send(orderflow.text(S.get("orderflow")))
        elif c in ("/levels", "/sr"): send(sr.text(S.get("sr")))
        elif c == "/methods": send(__import__("methods").text((S.get("paper") or {}).get("methods")))
        elif c == "/timing": send(timing.text(S.get("timing") or timing.now_context(timing.load(), now)))
        elif c == "/ask": qtxt = " ".join(txt[1:]); (answer_q(qtxt) if qtxt else tg("sendMessage", chat_id=CHAT, text=HEADER + "🤖 ASK: sawaal likho (jaise /ask 1 ghante me upar ya neeche?) ya seedha message bhejo. Ya button dabao:", reply_markup=ask_kb()))
        elif c == "/daily": daily_cmd(txt[1:])
        elif c in ("/help", "/start"): send(HELP)
        elif c == "/history": send(stats.history_text(history.load()["records"].values(), int(txt[1]) if len(txt) > 1 and txt[1].isdigit() else 5))
        elif c == "/timeline" and len(txt) > 1: rec = history.load()["records"].get(txt[1]); send(stats.timeline_text(rec) if rec else "Trade ID nahi mila. /history se ID dekho.")
        elif c == "/stats": send(stats.text(history.load()["records"].values(), ((S.get("paper") or {}).get("wallet") or {}).get("start", 20000)))
        elif c == "/today": send(today_text())
        elif c == "/pause": S["paused"] = True; send("⏸ Paused. Koi naya trade ya alert nahi aayega. Khule trades ka prabandhan chalta rahega. /resume se chalu karo.")
        elif c == "/resume": S["paused"] = False; send("▶️ Resumed. Naye trades/alerts wapas chalu.")
        elif c == "/weekly": send(paper.weekly_text(S.get("paper") or {}, now))
        elif c == "/active": send("\n".join(f"{i}: {t['signal']} {t['status']}" for i, t in S["trades"].items() if not t["outcome"]) or "No active old-style signals")
        elif c == "/review" and len(txt) > 1 and txt[1] in S["trades"]: send(review(S["trades"][txt[1]]))
        elif c == "/wallet": send(wallet.summary(S.get('paper') or {}))
        elif c == "/ledger": send(paper.ledger_text(S.get("paper") or {}))
        elif c == "/trades": send(wallet.trades_text(S.get("paper") or {}))
        elif c == "/analysis": send(analysis.text(S.get("analysis")))
        elif c == "/config": send(config.show())
        elif c == "/set" and len(txt) > 2: send(config.set_value(txt[1], txt[2]))
        elif c == "/notify" and len(txt) > 2: send(config.set_notify(txt[1], txt[2]))
        elif c == "/note" and len(txt) > 2: send(paper.add_note(S, txt[1], " ".join(txt[2:])))
        elif c == "/myexit" and len(txt) > 2: send(paper.my_exit(S, txt[1], txt[2], " ".join(txt[3:]), now))
        elif c == "/resetwallet": send(paper.reset_wallet(S, now) if txt[1:2] == ["confirm"] else "Wallet reset karne par purani history archive ho jati hai. Pakka ho to bhejo: /resetwallet confirm")
        elif not c.startswith("/"): answer_q(" ".join(txt))            # koi bhi seedha sawaal -> Ask
        else: send(HELP)
    return len(r["result"])

def alert(t, title, extra=""):
    send(f"{title}\nTrade ID: {t['id']}\nPrice: {P(S['last_price'])}\n{extra}", t["id"], cat="signals")

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

def record(px, fr, oi):  # builds our own OI/funding/order-book history for future backtests
    try:
        b = E._get("market/books", instId=E.INST, sz=20)[0]
        bv, av = sum(float(x[1]) for x in b["bids"]), sum(float(x[1]) for x in b["asks"]); imb = round((bv - av) / (bv + av), 4)
    except Exception: imb = ""
    new = not os.path.exists("market_log.csv")
    with open("market_log.csv", "a") as f:
        if new: f.write("ts,price,funding,oi_usd,book_imbalance\n")
        f.write(f"{now.isoformat(timespec='seconds')},{px},{fr},{oi},{imb}\n")

def scan_cycle():
    handle_updates()
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        send("Bot connected. Manual test run OK.")
    try:
        m5, m15, h1, h4 = (E.candles(b) for b in ("5m", "15m", "1H", "4H"))
        fr, oi = E.funding(), E.open_interest()
    except Exception as e:
        print("data error", e)
        if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
            send("Data error: " + str(e)[:250])
        json.dump(S, open("state.json", "w"), indent=1)
        return
    S["last_price"] = px = float(m5.c.iloc[-1])
    record(px, fr, oi); flow.record(now)
    try:                                                                 # per-timeframe support/resistance, aggressive buy/sell by price, chart fallback data
        d1 = None
        try: d1 = E.candles("1D", 250)
        except Exception: pass
        frs = {"5m": m5, "15m": m15, "1H": h1, "4H": h4, **({"1D": d1} if d1 is not None else {})}; S["sr"] = sr.build(frs, px); S["orderflow"] = orderflow.update(now, px)
        if not os.path.exists("chart_data.json") or (now - dt.datetime.fromisoformat(S.get("chart_ts", "2000-01-01T00:00:00+00:00"))).total_seconds() > 3 * 3600:
            json.dump(dict(built=now.isoformat(timespec="seconds"), **{k: [[int(r.ts), round(r.o, 1), round(r.h, 1), round(r.l, 1), round(r.c, 1), round(r.v, 1)] for r in v.tail(300).itertuples()] for k, v in frs.items()}), open("chart_data.json", "w"), separators=(",", ":")); S["chart_ts"] = now.isoformat(timespec="seconds")
    except Exception as e: print("sr/orderflow error", e)
    try: S["timing"] = timing.now_context(timing.ensure(now), now)        # when does BTC usually move? (rebuilt every ~3 days from 1 year of 1H data)
    except Exception as e: print("timing error", e)
    try:                                                                # Ask: live state for every question + yesterday/today move table + outcome of earlier forecasts
        S["ask_state"] = askstats.live_state(m5, h1); S["daily"] = askstats.daily(h1, now); askstats.resolve(S, m5, h1, now)
    except Exception as e: print("ask state error", e)
    try: dailylog.backfill(now, S); dailylog.update(h1, now, S)        # permanent daily archive (never deleted)
    except Exception as e: print("dailylog error", e)
    try: m30 = E.candles("30m")
    except Exception: m30 = None
    for t in S["trades"].values():
        if t["status"] != "CLOSED": track(t, m5)
    r = E.scan(m15, h4, h1)
    S["market"] = dict(price=px, regime=r["regime"], signal=r["signal"], side=r["side"], score=r["score"], scores=r["scores"], atr1h=r["atr1h"], atr4h=r["atr4h"], reversal=r["reversal"], tf=E.tf_view({"5m": m5, "15m": m15, **({"30m": m30} if m30 is not None else {}), "1H": h1, "4H": h4}), funding=fr, oi=oi,
                       pro=r["pro"], con=r["con"], ts=now.isoformat(timespec="seconds"))
    if r["reversal"] != S.get("rev_last", "none"):
        S["rev_last"] = r["reversal"]
        if r["reversal"] != "none": send(f"🔄 {r['reversal']}\nBTC ${px:,.0f}. Bade chart pe trend ke ulte palatne ka sanket mila (WATCH = shuruaati, CONFIRMED = pakka hota hua). Ye guarantee nahi, sirf chetavni hai.", cat="reversal")
    open_t = [t for t in S["trades"].values() if t["status"] != "CLOSED"]
    last = max((t["created"] for t in S["trades"].values()), default="2000")
    if r["signal"].startswith("EARLY") and not S.get("paused") and not open_t and (now - dt.datetime.fromisoformat(last if "T" in last else "2000-01-01T00:00:00+00:00")).total_seconds() > 3600:
        d = now.strftime("%Y%m%d"); S["n"][d] = S["n"].get(d, 0) + 1; tid = f"BTC-{r['side']}-{d}-{S['n'][d]:03d}"
        t = dict(id=tid, side=r["side"], signal=r["signal"], regime=r["regime"], score=r["score"], pro=r["pro"], con=r["con"],
                 entry=r["entry"], zone=r["zone"], sl=r["sl"], sl0=r["sl"], t1=r["t1"], t2=r["t2"], t3=r["t3"], ext=r["ext"], confirm=r["confirm"],
                 move_class=r["move_class"], risk=r["risk"], created=now.isoformat(timespec="seconds"), last_ts=float(m5.ts.iloc[-1]),
                 mfe=0, mae=0, status="EARLY SETUP", outcome="", events=[], user={})
        ev(t, r["signal"], px); S["trades"][tid] = t
        mv = abs(t["t1"] - t["entry"]), abs(t["t3"] - t["entry"])
        send(f"🧪 EXPERIMENTAL BTC ALERT (EXPERIMENTAL, no proven edge yet)\nTrade ID: {tid}\nSignal: {r['signal']}\nRegime: {r['regime']}\nPrice: {P(px)}\n"
             f"Entry Zone: {P(t['zone'][0])} – {P(t['zone'][1])}\nInvalidation/SL: {P(t['sl'])}\nT1 {P(t['t1'])} | T2 {P(t['t2'])} | T3 {P(t['t3'])}\nExtended: {P(t['ext'])}+\n"
             f"Confirmation: {'above' if r['side']=='LONG' else 'below'} {P(t['confirm'])}\nMove to T1–T3: {mv[0]:,.0f} to {mv[1]:,.0f} pts ({t['move_class']} vs 4H ATR)\n"
             f"Setup Score: {r['score']}/100 | False-signal risk: {r['risk']}\nFor: {', '.join(r['pro'])}\nAgainst: {', '.join(r['con']) or '-'}{DISC}", tid, cat="signals")
    mstats = lg = None
    try:   # full snapshot (spec 31): scores, stage, zones, expected move, checklist
        mstats = json.load(open("move_stats.json")) if os.path.exists("move_stats.json") else None
        lg = pd.read_csv("market_log.csv") if os.path.exists("market_log.csv") else None
        S["analysis"] = analysis.snapshot(h1, fr, oi, lg, mstats, r["regime"], r["scores"], any((S.get("paper") or {}).get("pos", {}).values()))
    except Exception as e: print("analysis error", e)
    try:   # Decision Desk data (key levels, point-move classes, derivatives, reversal evidence, multi-timeframe) + stage history (spec 28)
        fl = pd.read_csv("flow_log.csv") if os.path.exists("flow_log.csv") else None
        frames = {"5m": m5, "15m": m15, "1H": h1, "4H": h4}
        if m30 is not None: frames["30m"] = m30
        S["desk"] = desk.build(frames, fr, oi, lg, fl, mstats, r["regime"])
        A_ = S.get("analysis")
        if A_:
            sl = S.setdefault("stage_log", [])
            if not sl or sl[-1]["stage"] != A_["stage"]: sl.append(dict(ts=now.isoformat(timespec="seconds"), stage=A_["stage"], status=A_["status"], regime=A_["regime"], price=px)); del sl[:-300]
    except Exception as e: print("desk error", e)
    try: paper.run(S, send, now, scan=r)
    except Exception as e: print("paper error", e)
    try: askstats.ensure(now)                                           # history stats for Ask (rebuilt weekly, ~1-2 min only when due)
    except Exception as e: print("ask stats error", e)
    try: notify.setup_alerts(S, send, now); notify.milestone_alert(S, send, send_file, now)
    except Exception as e: print("notify error", e)
    loc = now.astimezone(TZ); key = loc.strftime("%Y-%m-%d"); CF = dict(config.load()["schedule"])
    for name, hr in (("morning", CF["morning_hour"]), ("evening", CF["evening_hour"])):
        if loc.hour == hr and S["sent"].get(name) != key:
            S["sent"][name] = key
            today = [t for t in S["trades"].values() if t["created"][:10] == now.strftime("%Y-%m-%d")]
            cnt = lambda s: sum(any(e["type"] == s for e in t["events"]) for t in today)
            if name == "morning":
                send(f"🌅 GOOD MORNING\nBTC Perpetual Brief\nPrice: {P(px)}\nRegime: {r['regime']}\nSignal: {r['signal']}\nActive trades: {len(open_t)}\nFunding: {fr*100:.4f}%\n{wallet.summary(S.get('paper') or {})}\n{paper.radar_line(S.get('paper', {}))}\nSignals are statistical, not guaranteed.", cat="morning")
            else:
                send(f"🌆 GOOD EVENING\nDaily Review\nPrice: {P(px)}\nRegime: {r['regime']}\nSignals: {len(today)}\nT1: {cnt('T1 HIT')} T2: {cnt('T2 HIT')} T3: {cnt('T3 HIT')} SL: {cnt('SL HIT')}\n{wallet.summary(S.get('paper') or {})}\n{paper.radar_line(S.get('paper', {}))}", cat="evening")
    if loc.hour == CF["evening_hour"] and loc.weekday() == 6 and S["sent"].get("weekly") != key:
        S["sent"]["weekly"] = key; send(paper.weekly_text(S.get("paper") or {}, now), cat="weekly")
    json.dump(S, open("state.json", "w"), indent=1)

def publish():  # push state to GitHub right away so the dashboard shows new trades within seconds (not at the end of the run)
    json.dump(S, open("state.json", "w"), indent=1)
    try: history.seed_from_backups(); history.sync(S)            # permanent trade record (never deleted, separate from state.json)
    except Exception as e: print("history error", e)
    if not os.environ.get("GITHUB_ACTIONS"): return
    try:
        run = lambda *c: subprocess.run(c, timeout=60, capture_output=True)
        run("git", "config", "user.name", "bot"); run("git", "config", "user.email", "bot@users.noreply.github.com"); run("git", "add", "state.json")
        if os.path.exists("config.json"): run("git", "add", "config.json")
        if os.path.exists("market_log.csv"): run("git", "add", "market_log.csv")
        if os.path.exists("trade_history.json"): run("git", "add", "trade_history.json")
        if os.path.exists("time_stats.json"): run("git", "add", "time_stats.json")
        for fn_ in ("orderflow_profile.json", "chart_data.json", "ask_stats.json", "daily_history.json", "daily_history.csv"):
            if os.path.exists(fn_): run("git", "add", fn_)
        if os.path.exists("flow_log.csv"): run("git", "add", "flow_log.csv")
        if run("git", "diff", "--cached", "--quiet").returncode: run("git", "commit", "-m", "state"); run("git", "pull", "--rebase"); run("git", "push")
    except Exception as e: print("publish error", e)

LISTEN_S = int(os.environ.get("LISTEN_SECONDS", 210))
def listen(seconds):  # stay online and answer commands/buttons within seconds
    end = time.time() + seconds
    while time.time() < end:
        globals()["now"] = dt.datetime.now(dt.timezone.utc)
        if handle_updates(timeout=int(min(20, max(end - time.time(), 1)))):
            if (S.get("paper") or {}).get("force_demo"):
                try: paper.run(S, send, globals()["now"])
                except Exception as e: print("paper error", e)
            publish()

def main():
    ST = S.setdefault("telegram", {}); ST["chat_mask"] = "…" + CHAT[-4:]
    tg("setMyCommands", commands=[dict(command=a, description=b) for a, b in MENU])
    me = tg("getMe"); ST["token_ok"] = bool(me and me.get("ok")); ST["bot"] = ((me or {}).get("result") or {}).get("username", "")
    scan_cycle(); publish(); listen(int(os.environ.get("LISTEN_SECONDS", config.load()["schedule"]["listen_seconds"]))); ST["last_run"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"); json.dump(S, open("state.json", "w"), indent=1)

main()
