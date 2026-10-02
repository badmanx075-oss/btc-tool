import json, os, io, datetime as dt, requests, pandas as pd, streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="BTC Tool", page_icon="📈", layout="wide")
RAW = "https://raw.githubusercontent.com/badmanx075-oss/btc-tool/main/"   # live data written by the 5-minute scanner

@st.cache_data(ttl=60)
def load(name, kind="json"):
    txt = None
    if not os.environ.get("DASH_LOCAL"):
        try: r = requests.get(RAW + name + f"?t={int(dt.datetime.now().timestamp())}", timeout=10); r.raise_for_status(); txt = r.text
        except Exception: txt = None
    if txt is None and os.path.exists(name): txt = open(name).read()
    if txt is None: return None
    try: return json.loads(txt) if kind == "json" else pd.read_csv(io.StringIO(txt))
    except Exception: return None

S = load("state.json") or {"trades": {}}
M, P, lp = S.get("market"), S.get("paper") or {}, S.get("last_price")
o = P.get("open"); bal, start = P.get("balance", 20000), P.get("start", 20000)
now = dt.datetime.now(dt.timezone.utc); inr = lambda x: f"₹{x:,.0f}"

def stage(score, active):
    if active: return "Stage 4-5: paper trade active"
    return "Stage 2: early setup (experimental)" if score >= 65 else "Stage 1-2: weak setup" if score >= 60 else "Stage 1: conditions developing" if score >= 40 else "Stage 0: no clear opportunity"

def pos_status(ur, left_h):
    if left_h <= 12: return "🟡 TIME ALMOST UP", "Trade closes automatically after 5 days."
    if ur >= 3: return "🟠 PROFIT-BOOKING ZONE", "Close to the 4R target. Paper rule exits at the target automatically."
    if ur >= 1.5: return "🟡 HOLD, PROTECT PROFIT", "Good profit. Real traders often raise the stop here (paper rule keeps it fixed)."
    if ur >= 0: return "🟢 HOLD: within plan", "In profit or flat. Stop and target unchanged."
    if ur > -0.7: return "🟢 HOLD: thesis intact", "Small dip is normal (backtest win rate is only ~33%)."
    return "🟡 CAUTION: near stop-loss", "If stop hits, the loss is limited to the planned risk."

LIVE = """<div style="font-family:sans-serif;color:#e6e6e6;padding:4px">
<div style="display:flex;gap:28px;align-items:baseline;flex-wrap:wrap"><div><div style="font-size:12px;opacity:.7">BTC perpetual live <span id="src"></span></div>
<div id="px" style="font-size:46px;font-weight:700">connecting...</div></div><div id="pl" style="font-size:22px"></div></div>
<div style="background:#333;height:10px;border-radius:5px;margin-top:8px"><div id="bar" style="background:#3b82f6;height:10px;border-radius:5px;width:0%"></div></div>
<div id="note" style="font-size:12px;opacity:.75;margin-top:4px"></div></div>
<script>
const pos=__POS__, $=i=>document.getElementById(i); let last=0, seen=0, prev=null, n=0;
const SRC=[["OKX","wss://ws.okx.com:8443/ws/v5/public",ws=>ws.send(JSON.stringify({op:"subscribe",args:[{channel:"tickers",instId:"BTC-USDT-SWAP"}]})),m=>m.data&&m.data[0]?+m.data[0].last:null],
["Binance","wss://fstream.binance.com/ws/btcusdt@aggTrade",ws=>0,m=>m.p?+m.p:null]];
function show(p){const t=Date.now(); seen=t; if(t-last<300) return; last=t;
 $("px").textContent="$"+p.toLocaleString("en-US",{minimumFractionDigits:1,maximumFractionDigits:1});
 $("px").style.color=prev===null||p===prev?"#e6e6e6":(p>prev?"#2ecc71":"#e74c3c"); prev=p;
 if(!pos.entry) return; const k=pos.side, inr=(p-pos.entry)*k*pos.qty*pos.fx, R=(p-pos.entry)*k/pos.risk;
 $("pl").innerHTML="Open P/L: <b style='color:"+(inr>=0?"#2ecc71":"#e74c3c")+"'>"+(inr>=0?"+":"-")+"₹"+Math.abs(inr).toFixed(0)+"</b> ("+R.toFixed(2)+"R)";
 $("bar").style.width=Math.min(Math.max((p-pos.sl)/(pos.tp-pos.sl),0),1)*100+"%";
 const x=(k==1&&(p<=pos.sl||p>=pos.tp))||(k==-1&&(p>=pos.sl||p<=pos.tp));
 $("note").textContent=x?"Price crossed stop/target. The scanner closes the paper order on its next run (within 5 min).":"Stop $"+Math.round(pos.sl).toLocaleString()+"  <-  now  ->  Target $"+Math.round(pos.tp).toLocaleString();}
function go(){const s=SRC[n%SRC.length]; $("src").textContent="("+s[0]+")"; let ws; try{ws=new WebSocket(s[1]);}catch(e){n++;setTimeout(go,2000);return;}
 ws.onopen=()=>s[2](ws); ws.onmessage=e=>{try{const p=s[3](JSON.parse(e.data)); if(p) show(p);}catch(x){}};
 ws.onclose=ws.onerror=()=>{n++; setTimeout(go,2000);};}
go();
setInterval(()=>{if(Date.now()-seen<8000) return; fetch("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT").then(r=>r.json()).then(j=>{last=0; show(+j.price); $("src").textContent="(Binance REST, ~3s)";}).catch(()=>{});},3000);
</script>"""
def live_widget(o):
    pos = {"entry": o["entry"], "side": o["side"], "qty": o.get("qty_btc", 0), "fx": o.get("fx", 88), "risk": o["risk"], "sl": o["sl"], "tp": o["tp"]} if o else {}
    html = LIVE.replace("__POS__", json.dumps(pos))
    if hasattr(st, "iframe"): st.iframe(html, height=170)
    else: components.html(html, height=170)

T = S.get("telegram") or {}
def amin(iso): return (now - dt.datetime.fromisoformat(iso)).total_seconds() / 60 if iso else None
head, btn = st.columns([6, 1]); head.title("📈 BTC Perpetual Tool")
if btn.button("🔄 Refresh"): st.cache_data.clear(); st.rerun()
if M:
    age = (now - dt.datetime.fromisoformat(M["ts"])).total_seconds() / 60
    head.caption(f"Last scan {age:.0f} min ago | BTC ${M['price']:,.0f} | Funding {M['funding'] * 100:.4f}% | OI ${M['oi'] / 1e9:.2f}B")
    if age > 30: st.warning("Scanner looks delayed (more than 30 min). Check GitHub Actions.")
if T.get("token_ok") and not T.get("last_error"): head.caption(f"📨 Telegram: ✅ connected (@{T.get('bot', '')}, checked {(amin(T.get('last_run')) or 0):.0f} min ago)")
elif T: head.caption(f"📨 Telegram: ❌ problem. {T.get('last_error') or 'bot token not accepted'}")
else: head.caption("📨 Telegram: no status yet (upload the new worker.py and run the scan once)")
st.caption("⚠️ Informational and statistical only. Virtual money. Backtests show NO proven edge yet.")

t1, t2, tL, tH, t3, t4, t5 = st.tabs(["🏠 Home", "💰 Wallet", "🧠 Learning", "🩺 Health", "📡 Old signals (experimental)", "📊 Backtests", "📘 Guide"])

with t1:
    live_widget(o)
    c = st.columns(4); c[0].metric("Paper wallet", inr(bal), f"{(bal / start - 1) * 100:+.1f}% since start")
    if o and lp:
        k, q = o["side"], o.get("qty_btc", 0); ur = (lp - o["entry"]) * k / o["risk"]; usd = (lp - o["entry"]) * k * q
        c[1].metric("Open trade P/L", f"{ur:+.2f}R", f"{inr(usd * o.get('fx', 88))}")
    else: c[1].metric("Open trade P/L", "No trade")
    c[2].metric("Market regime", M["regime"] if M else "-"); c[3].metric("Stage", stage(M["score"] if M else 0, bool(o)).split(":")[0])
    if o: st.info(f"Paper position is OPEN ({'BUY' if o['side'] == 1 else 'SELL'}). Nothing to do. The tool closes it at stop, target or after 5 days.")
    elif M and M["signal"].startswith("EARLY"): st.warning(f"Experimental signal: {M['signal']}. Backtests show no proven edge. Do NOT use real money.")
    else: st.success("WAIT: no trade setup right now. 'No trade' is a valid result.")
    st.subheader("Live position")
    if o and lp:
        k, q = o["side"], o.get("qty_btc", 0); hrs = (now - dt.datetime.fromisoformat(o["created"])).total_seconds() / 3600
        title, why = pos_status(ur, 120 - hrs)
        if o.get("demo"): title, why = "🧪 DEMO TRADE (pipeline test, wallet not affected)", "Closes at stop/target or within 1 hour."
        st.markdown(f"### {title}"); st.caption(why)
        if o.get("why"): st.info("💬 **Kyun liya:** " + o["why"])
        st.progress(float(min(max((lp - o["sl"]) / (o["tp"] - o["sl"]), 0), 1)), text=f"Stop ${o['sl']:,.0f}  ←  now ${lp:,.0f}  →  Target ${o['tp']:,.0f}")
        st.table(pd.DataFrame([{"Order": o["id"], "Action": "BUY (LONG)" if k == 1 else "SELL (SHORT)", "Qty BTC": q, "Entry": round(o["entry"]), "Now": round(lp),
                                "Stop": round(o["sl"]), "Target": round(o["tp"]), "Open P/L": inr(usd * o.get("fx", 88)), "Time left": f"{max(120 - hrs, 0):.0f} h"}]))
    else: st.write("No open position.")
    RD = P.get("radar")
    if RD and not o:
        st.subheader("Setup radar: how close is a trade?"); x, y = st.columns(2)
        for col, side in ((x, "LONG"), (y, "SHORT")):
            rows = RD[side]; col.markdown(f"**{'BUY' if side == 'LONG' else 'SELL'} setup: {sum(r[1] for r in rows)}/4 conditions met**")
            for nm, ok_, val in rows: col.markdown(f"{'✅' if ok_ else '❌'} {nm}: {val}")
        st.caption("A paper trade opens only when all 4 are ✅ (about 1-2 times a week in backtests). Checked on the last closed 1-hour candle.")
    st.subheader("Market now")
    if M:
        a, b = st.columns(2); a.markdown(f"**Signal:** {M['signal']} (score {M['score']}/100)"); a.markdown("**For:** " + (", ".join(M["pro"]) or "-")); b.markdown("**Against:** " + (", ".join(M["con"]) or "-"))
        if M.get("scores"): st.markdown(f"**Accumulation score** (buy-side evidence): {M['scores'].get('LONG', '-')}/100 | **Distribution score** (sell-side evidence): {M['scores'].get('SHORT', '-')}/100")
        st.caption(stage(M["score"], bool(o)))
    lg = load("market_log.csv", "csv")
    if lg is not None and len(lg) > 5:
        lg = lg.tail(288).set_index("ts"); x, y = st.columns(2); x.caption("BTC price (last ~24h)"); x.line_chart(lg["price"]); y.caption("Open interest USD (last ~24h)"); y.line_chart(lg["oi_usd"])

with t2:
    c = st.columns(4); c[0].metric("Wallet", inr(bal), f"{(bal / start - 1) * 100:+.1f}%"); c[1].metric("Start", inr(start)); c[2].metric("Trades closed", len(P.get("closed", []))); c[3].metric("Max drawdown", f"{P.get('max_dd_pct', 0)}%")
    st.caption("Rules: strategy trend_pullback | risk 1% of wallet per trade | stop 3×ATR(1H) | target 4R | exit after 5 days | fees 0.10% | no real orders.")
    with st.expander("🧮 Position size calculator (for your own manual trades)"):
        x1, x2, x3 = st.columns(3); wv = x1.number_input("Wallet ₹", value=float(bal), step=1000.0); rp = x2.number_input("Risk % per trade", value=1.0, step=0.25); fxv = x3.number_input("₹ per $1", value=88.0)
        y1, y2 = st.columns(2); en = y1.number_input("Entry price $", value=float(lp or 80000)); sv = y2.number_input("Stop price $", value=float((lp or 80000) * 0.985))
        if abs(en - sv) > 0: q = (wv * rp / 100) / (abs(en - sv) * fxv); st.write(f"Quantity **{q:.4f} BTC** | position ${q * en:,.0f} (₹{q * en * fxv:,.0f}, {q * en * fxv / wv:.1f}x wallet) | money at risk ₹{wv * rp / 100:,.0f}")
    cl = P.get("closed", [])
    if cl:
        d = pd.DataFrame(cl); d["wallet"] = start + d["pnl_inr"].fillna(0).cumsum(); st.line_chart(d.set_index("closed")["wallet"])
        st.subheader("Trade book"); st.dataframe(d.reindex(columns=["closed", "id", "qty_btc", "entry", "exit", "outcome", "gross_usd", "fees_usd", "pnl_inr", "R", "why", "lesson"]).rename(
            columns={"closed": "Closed", "id": "Order", "qty_btc": "Qty BTC", "entry": "Entry", "exit": "Exit", "outcome": "Result", "gross_usd": "Gross $", "fees_usd": "Fees $", "pnl_inr": "Net ₹", "why": "Kyun liya", "lesson": "Kya hua"}))
        w = int((d.pnl_inr > 0).sum()); st.caption(f"Wins {w} | Losses {len(d) - w} | Total {d.R.sum():+.2f}R")
    else: st.info("No closed trades yet. A signal needs several conditions together, so 1-2 trades per week is normal.")
    st.subheader("Trade journal (saved on GitHub: page refresh ya browser band hone se kuch nahi jaata)")
    jr = ([o] if o else []) + list(reversed(cl))
    for t_ in jr[:15]:
        with st.expander(f"{'🟢 OPEN' if t_ is o else '✔️ CLOSED'}  {t_['id']}  |  {t_.get('outcome', 'running')}  {('%+.2fR' % t_['R']) if 'R' in t_ else ''}", expanded=t_ is o):
            st.markdown("**Kyun liya:** " + (t_.get("why") or "-")); st.markdown("**Kya hua:** " + (t_.get("lesson") or "abhi trade chal raha hai"))
            st.caption(f"Qty {t_.get('qty_btc')} BTC | entry ${t_['entry']:,.0f} | stop ${t_['sl']:,.0f} | target ${t_['tp']:,.0f}" + (f" | exit ${t_['exit']:,.0f}, net ₹{t_.get('pnl_inr', 0):,.0f}" if "exit" in t_ else ""))
    if P.get("orders"): st.subheader("Order log (newest first)"); st.dataframe(pd.DataFrame(P["orders"]).iloc[::-1])

with tL:
    st.info("The tool records every trade, studies its losses, and proposes filters. It does NOT rewrite its rules after each loss: with a ~33% win rate most losses are normal, and reacting to each one causes overfitting. "
            "A filter starts only after you approve it in Telegram (/approve N), and it switches itself off if the trades it blocks do as well as the ones it allows.")
    L = P.get("lessons") or {}; cl = [t for t in P.get("closed", []) if t.get("lesson")]
    c = st.columns(3); c[0].metric("Trades studied", L.get("n", 0)); c[1].metric("Active filters", sum(f.get("active", True) for f in P.get("filters", []))); c[2].metric("Ideas waiting", len(P.get("proposals", [])))
    st.subheader("Lesson from each trade")
    if cl: st.dataframe(pd.DataFrame(cl).reindex(columns=["closed", "id", "outcome", "R", "mfe_R", "mae_R", "hold_h", "lesson"]).rename(columns={"mfe_R": "Best R", "mae_R": "Worst R", "hold_h": "Hours held"}))
    else: st.write("No closed paper trades yet.")
    st.subheader("Patterns across trades"); st.caption(L.get("note", ""))
    if L.get("patterns"): st.dataframe(pd.DataFrame(L["patterns"])[["feature", "bucket", "n", "mean_R", "rest_R", "z"]].rename(columns={"mean_R": "This group R", "rest_R": "Others R"}))
    for p in P.get("proposals", []): st.warning(f"💡 #{p['id']}: {p['text']} (n={p['n']}, {p['mean_R']:+.2f}R vs {p['rest_R']:+.2f}R). To use it, send **/approve {p['id']}** in Telegram.")
    for f in P.get("filters", []):
        b = [s["R"] for s in P.get("shadow", []) if s.get("filter") == f["text"] and "R" in s]
        st.write(f"{'✅ ON' if f.get('active', True) else '⏸ OFF'}  Filter #{f['id']}: {f['text']} | blocked trades checked: {len(b)}" + (f", average {sum(b) / len(b):+.2f}R" if b else ""))

with tH:
    st.caption("One-glance check that every part of the tool is alive.")
    rl = load("market_log.csv", "csv"); sa = amin(M["ts"]) if M else None; ls = amin(T.get("last_send_ok")); lc = amin(T.get("last_cmd_ts")); pr = amin((P.get("radar") or {}).get("ts"))
    rows_h = [
        ["Scanner (GitHub Action)", sa is not None and sa < 30, f"last scan {sa:.0f} min ago" if sa is not None else "no scan yet", "Open the Actions tab, cancel any stuck run, then Run workflow"],
        ["Exchange data", bool(M) and (M.get("price") or 0) > 0, f"BTC ${M['price']:,.0f}" if M else "no data", "The exchange may be blocking GitHub servers"],
        ["Telegram bot token", bool(T.get("token_ok")), f"bot @{T.get('bot')}" if T.get("token_ok") else "not verified yet", "Recheck the TG_TOKEN secret"],
        ["Telegram sending", bool(T.get("last_send_ok")) and not T.get("last_error"), f"last message {ls:.0f} min ago" if ls is not None else "none yet", T.get("last_error") or "Run the workflow manually: 'Bot connected' should arrive"],
        ["Telegram commands (/ping)", lc is not None, f"last '{T.get('last_cmd')}' {lc:.0f} min ago" if lc is not None else "no command received yet", "Send /ping to your bot. It answers within seconds while the scanner is listening, else on the next run"],
        ["Data recorder (OI, funding)", rl is not None and len(rl) > 0, f"{len(rl)} rows logged" if rl is not None else "no log yet", "market_log.csv must exist in the repo (scan.yml must git add it)"],
        ["Paper trading engine", (pr is not None and pr < 30) or bool(o), f"radar updated {pr:.0f} min ago" if pr is not None else ("trade open" if o else "not running"), "Look for 'paper error' in the Run worker log"],
        ["Learning module", "lessons" in P, "ready" if "lessons" in P else "not started", "Upload learn.py, paper.py and worker.py"]]
    bad = [r for r in rows_h if not r[1]]
    (st.success("All checks green.") if not bad else st.warning(f"{len(bad)} check(s) need attention."))
    st.table(pd.DataFrame([["✅" if r[1] else "❌", r[0], r[2], "" if r[1] else r[3]] for r in rows_h], columns=["", "Check", "Detail", "If red, do this"]))
    if T.get("foreign_chat"): st.error(f"A message reached the bot from a chat ending {T['foreign_chat']}, but your TG_CHAT_ID secret ends {T.get('chat_mask', '?')}. The bot ignores other chats. Fix the TG_CHAT_ID secret (spaces or a wrong ID).")
    if T.get("poll_error"): st.error(f"Telegram polling problem: {T['poll_error']}")

with t3:
    st.warning("Early-signal engine. Its backtest was negative (about -0.2R per trade), so this is for learning only. Not connected to the wallet.")
    T = S.get("trades", {})
    if T:
        df = pd.DataFrame(T.values()); st.dataframe(df[["id", "signal", "score", "entry", "sl", "t1", "t2", "t3", "status", "outcome"]].round(0))
        pick = st.query_params.get("trade"); ids = list(T); tid = st.selectbox("Review a trade", ids, index=ids.index(pick) if pick in ids else len(ids) - 1); t = T[tid]
        a, b = st.columns(2); a.markdown(f"**Why:** {', '.join(t['pro'])}"); b.markdown(f"**Against:** {', '.join(t['con']) or '-'}")
        st.table(pd.DataFrame([{"Zone": f"{t['zone'][0]:,.0f}-{t['zone'][1]:,.0f}", "Stop": round(t["sl0"]), "T1": round(t["t1"]), "T2": round(t["t2"]), "T3": round(t["t3"]),
                                "Extended": round(t["ext"]), "Confirm": round(t["confirm"]), "Best move pts": round(t["mfe"]), "Worst dip pts": round(t["mae"])}]))
        st.caption(f"System outcome: {t['outcome'] or 'open'} | Your input: {t['user'] or 'none'}"); st.markdown("**Timeline**")
        st.dataframe(pd.DataFrame(t["events"])[["ts", "type", "price", "note"]])
    else: st.write("No old-style signals yet.")

with t4:
    st.caption("What was tested on past data, in plain words.")
    rows = []; v1, v3, v4, v5 = (load(f) for f in ("backtest_results.json", "backtest_v3_results.json", "backtest_v4_results.json", "backtest_v5_results.json"))
    if v1: a = v1["all"]; rows.append(["V1: early signals", f"{a['n']} signals, target 1 reached before stop {a['t1_before_stop_%']}% (random is ~40%)", "No edge"])
    if v3: rows.append(["V3: tuned stops and targets", f"unseen test {v3['best']['test'].get('mean_R')}R per trade (original rules {v3['original_rules']['test'].get('mean_R')}R)", v3["verdict"]])
    if v4: rows.append(["V4: 4 other strategies", "trend_pullback looked best, others failed", v4["verdict"]])
    if v5: f = v5["central_fresh_oos"]; rows.append(["V5: 5-year check of trend_pullback", f"older unseen trades: {f.get('mean_R')}R per trade (n={f.get('n')}, error ±{f.get('se')})", v5["verdict"]])
    if rows: st.table(pd.DataFrame(rows, columns=["Test", "Result", "Verdict"]))
    if v1:
        a_ = v1["all"]; st.subheader("Historical odds of point moves (early-signal setups, 1 year)")
        st.table(pd.DataFrame([{"Move reached before the stop": f"+{x:,} points", "Share of setups": f"{a_[f'p{x}_before_stop_%']}%"} for x in (500, 1000, 2000, 5000)]))
        st.caption(f"Based on {a_['n']} setups. Depends on the stop distance used. An estimate, not a promise.")
    st.info("R = result in units of risk. +0.10R means earning 10% of the amount risked per trade on average. Errors this large mean it cannot be told apart from zero yet.")
    for n, v in (("V5 details", v5), ("V4 details", v4), ("V3 details", v3)):
        if v:
            with st.expander(n): st.json(v)

with t5:
    st.markdown("""
**How the wallet works (every 5 minutes)**
1. The scanner reads 1-hour candles and checks for the *trend pullback* pattern.
2. If it appears, a **virtual** BUY/SELL order opens. Quantity comes from risking 1% of the wallet.
3. Each scan checks whether price touched the stop-loss or target, or 5 days passed.
4. The order closes, fees are deducted, and the net ₹ is added to or removed from the wallet.
5. A Telegram message (marked *Notified from BTC Tool*) is sent at open and close.

**Words used**
- **Regime**: what the market is doing (trend, range, unclear).
- **Stage**: how far a setup has developed (0 nothing, 2 early setup, 4-5 trade active).
- **Score**: how many evidence points line up (0-100). Higher did *not* mean better in backtests.
- **R**: one unit of risk (distance to stop). Target 4R = four times the risk.
- **Funding / OI**: crowd positioning in perpetual futures (open interest).
- **Paper trade**: practice trade with virtual money. No exchange connection, no real orders.

**Telegram commands:** `/ping` (is the bot alive?), `/weekly` (weekly review), `/lessons` (what the tool learned), `/approve N` and `/revert N` (turn a learned filter on/off), `/status` (wallet, position, radar), `/demo` (opens a test trade that never touches the wallet, to prove the pipeline works). Replies come on the next scan, within a few minutes.

**Honest status**: the machine (scanner, alerts, wallet, dashboard) works. A reliably profitable signal is **not proven**. Treat everything as practice.
""")
