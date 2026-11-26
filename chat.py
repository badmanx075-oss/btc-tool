"""Two-person chat (A and V) inside the dashboard. Free, no new service. Password-protected (needs CHAT_PIN_A / CHAT_PIN_V or CHAT_PIN in the Streamlit secrets).
How it works: messages live in ONE shared list inside the running dashboard process, so everybody who opens the same dashboard link sees them within ~3 seconds (also saved to a temp file so a page reload / quick restart keeps them).
Honest limits: if Streamlit Cloud puts the app to sleep or redeploys it, the history can be lost. The chat is LOCKED until a password is set in the Streamlit secrets (CHAT_PIN_A / CHAT_PIN_V, or one shared CHAT_PIN): nothing is readable or writable without logging in.
Optional (only if YOU add them to the Streamlit Cloud secrets): TG_TOKEN + TG_CHAT_ID (same values as the bot) -> every message is also forwarded to Telegram (so the other person gets a notification and a permanent copy)."""
import os, json, time, threading, tempfile, datetime as dt
import requests

USERS = ("A", "V")
FILE = os.path.join(tempfile.gettempdir(), "btc_tool_chat.json")
KEEP = 500
_LOCK = threading.Lock()
_SEEN = {}                                                       # user -> last heartbeat (epoch s)


def _load():
    try: return json.load(open(FILE))[-KEEP:]
    except Exception: return []


_MSGS = _load()


def _save():
    try:
        tmp = FILE + ".tmp"; json.dump(_MSGS[-KEEP:], open(tmp, "w")); os.replace(tmp, FILE)
    except Exception: pass


def _secret(st, name):
    try: v = st.secrets.get(name)
    except Exception: v = None
    return str(v or os.environ.get(name, "")).strip()


def add(user, text, tg=None):
    """Adds one message (max 1000 chars). Returns the stored message or None for empty / unknown user."""
    text = (text or "").strip()[:1000]
    if user not in USERS or not text: return None
    m = dict(u=user, t=text, ts=time.time())
    with _LOCK: _MSGS.append(m); del _MSGS[:-KEEP]; _save()
    if tg and tg[0] and tg[1]:
        try: requests.post(f"https://api.telegram.org/bot{tg[0]}/sendMessage", data=dict(chat_id=tg[1], text=f"🤖 Notified from BTC Tool\n💬 {user}: {text}"), timeout=8)
        except Exception: pass                                    # never let a Telegram problem break the chat (and never print the token)
    return m


def recent(n=100):
    with _LOCK: return list(_MSGS[-n:])


def heartbeat(user):
    if user in USERS: _SEEN[user] = time.time()


def online(user, within=15): return time.time() - _SEEN.get(user, 0) <= within


def _ist(ts): return (dt.datetime.fromtimestamp(ts, dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).strftime("%d %b %H:%M")


_FAILS = {}                                                      # user -> [count, locked_until]  (shared by all sessions: brute force protection)


def pins(st):
    """{user: password}. Per-person CHAT_PIN_A / CHAT_PIN_V win; CHAT_PIN is the shared fallback. Passwords come ONLY from the Streamlit secrets (the repo is public, never hard-code one)."""
    shared = _secret(st, "CHAT_PIN")
    return {u: (_secret(st, f"CHAT_PIN_{u}") or shared) for u in USERS}


def check(user, typed, pin):
    """True only for the right password. After 5 wrong tries the user is locked for 5 minutes (any device)."""
    import hmac
    f = _FAILS.setdefault(user, [0, 0.0])
    if time.time() < f[1]: return False, f"Bahut galat try. {int(f[1] - time.time())} second baad dobara try karo."
    if pin and hmac.compare_digest(str(typed).encode(), str(pin).encode()): f[0] = 0; return True, ""
    f[0] += 1
    if f[0] >= 5: f[0] = 0; f[1] = time.time() + 300; return False, "5 galat try: 5 minute ke liye lock."
    return False, "Galat password."


def render(st):
    st.subheader("👥 Chat: A aur V")
    P = pins(st)
    if not any(P.values()):
        st.warning("🔒 Chat abhi band hai kyunki password set nahi hai.\n\nStreamlit Cloud → App → Settings → Secrets me ye likho aur Save karo:\n\n`CHAT_PIN_A = \"A-ka-password\"`\n\n`CHAT_PIN_V = \"V-ka-password\"`\n\n(Dono ka ek hi chahiye to sirf `CHAT_PIN = \"...\"`.) Password code ya GitHub me mat likhna.")
        return
    me = st.session_state.get("chat_user")
    if me not in USERS:                                          # ---- login screen (shown every time the tab is opened in a new session)
        st.info("🔐 Chat secure hai. Naam chuno aur password daalo.")
        with st.form("chat_login"):
            u = st.radio("Tum kaun ho?", USERS, horizontal=True); pw = st.text_input("Password", type="password"); ok = st.form_submit_button("Login")
        if ok:
            good, msg = check(u, pw, P.get(u, ""))
            if good: st.session_state["chat_user"] = u; st.rerun()
            else: st.error(msg)
        return
    c1, c2 = st.columns([5, 1]); c1.success(f"Login: **{me}**")
    if c2.button("Logout", key="chat_logout"): st.session_state.pop("chat_user", None); st.rerun()
    tg = (_secret(st, "TG_TOKEN"), _secret(st, "TG_CHAT_ID"))
    other = USERS[1] if me == USERS[0] else USERS[0]
    st.caption("Dono apne-apne device par yehi dashboard kholo aur login karo. Naye message ~3 second me dikhte hain." + (" Har message Telegram par bhi jata hai." if tg[0] and tg[1] else ""))

    def feed():
        heartbeat(me)
        st.caption(("🟢" if online(other) else "⚪") + f" {other} " + ("online" if online(other) else "abhi nahi dikha"))
        box = st.container(height=420)
        ms = recent(100)
        if not ms: box.info("Abhi koi message nahi. Pehla message tum likho.")
        for m in ms:
            with box.chat_message("user" if m["u"] == me else "assistant", avatar="🧑" if m["u"] == me else "👤"):
                st.markdown(f"**{m['u']}** · {_ist(m['ts'])}\n\n{m['t']}")
    if hasattr(st, "fragment"): st.fragment(run_every=3)(feed)()
    else: feed(); st.button("🔄 Refresh", key="chat_refresh")
    with st.form("chat_form", clear_on_submit=True):
        c1, c2 = st.columns([6, 1]); txt = c1.text_input("Message", label_visibility="collapsed", placeholder=f"{me} ke naam se likho…"); go = c2.form_submit_button("Send")
    if go and txt.strip(): add(me, txt, tg); st.rerun()
