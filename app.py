import json, os, io, datetime as dt, requests, pandas as pd, streamlit as st
import streamlit.components.v1 as components
import config, history, stats, decision, review, timing, moveradar as MRD, sr as SRM, orderflow as OFM
try:
    import chart as CH, engine as ENG
except Exception as _e: CH = None; _CH_ERR = str(_e)

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
    if kind == "text": return txt
    try: return json.loads(txt) if kind == "json" else pd.read_csv(io.StringIO(txt))
    except Exception: return None

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
    pos = {"entry": o["entry"], "side": o["side"], "qty": o.get("qty", 0) * o.get("remaining", 1), "fx": o.get("fx", 88), "risk": o["risk"], "sl": o["sl"], "tp": o.get("tp") or o.get("t2") or o["entry"] + o["side"] * 4 * o["risk"]} if o else {}
    html = LIVE.replace("__POS__", json.dumps(pos))
    if hasattr(st, "iframe"): st.iframe(html, height=170)
    else: components.html(html, height=170)

S = load("state.json") or {"trades": {}}
M, P, A, T = S.get("market"), S.get("paper") or {}, S.get("analysis"), S.get("telegram") or {}
lp = S.get("last_price"); now = dt.datetime.now(dt.timezone.utc); inr = config.inr
CFG = config._merge(config.DEFAULTS, load("config.json") or {})
W = P.get("wallet") or {}; eq = W.get("cash", 0) + W.get("margin", 0); start = W.get("start", CFG["wallet"]["start_inr"])
POS = [t for t in (P.get("pos") or {}).values() if t]; CL = P.get("closed", [])
def amin(iso): return (now - dt.datetime.fromisoformat(iso)).total_seconds() / 60 if iso else None
def side_txt(k): return "BUY (LONG)" if k == 1 else "SELL (SHORT)"
def pl_usd(t, px): return (px - t["entry"]) * t["side"] * t["qty"] * t["remaining"]

head, btn = st.columns([6, 1]); head.title("📈 BTC Perpetual Tool")
if btn.button("🔄 Refresh"): st.cache_data.clear(); st.rerun()
if M:
    age = amin(M["ts"]); head.caption(f"Last scan {age:.0f} min ago | BTC ${M['price']:,.0f} | Funding {M['funding'] * 100:.4f}% | OI ${M['oi'] / 1e9:.2f}B")
    if age > 30: st.warning("Scanner looks delayed (more than 30 min). Check GitHub Actions.")
if T.get("token_ok") and not T.get("last_error"): head.caption(f"📨 Telegram: ✅ connected (@{T.get('bot', '')}, checked {(amin(T.get('last_run')) or 0):.0f} min ago)")
elif T: head.caption(f"📨 Telegram: ❌ problem. {T.get('last_error') or 'bot token not accepted'}")
else: head.caption("📨 Telegram: no status yet (upload the latest worker.py and run the scan once)")
if S.get("paused"): st.warning("⏸ PAUSED: no new trades or alerts will start. Open trades are still managed. Send /resume on Telegram to restart.")
st.caption("⚠️ Informational and statistical only. Virtual money, no real orders. Backtests show NO proven edge yet.")
tH_, tAsk, tCH, tDD, tA, tW, tTH, tRV, tTM, tL, tHl, tS, tO, tB, tG = st.tabs(["🏠 Home", "💬 Ask", "📈 Chart", "🧭 Decision Desk", "📋 Analysis", "💰 Wallet", "📒 Trade History", "📦 Review", "🕒 Time", "🧠 Learning", "🩺 Health", "⚙️ Settings", "📡 Old signals", "📊 Backtests", "📘 Guide"])

def position_card(t):
    px = lp or t["entry"]; ur = (px - t["entry"]) * t["side"] / t["risk"]; usd = pl_usd(t, px) + t.get("realized_usd", 0); m = t.get("mgmt")
    hrs = (now - dt.datetime.fromisoformat(t["created"])).total_seconds() / 3600; tgt = t.get("tp") or t.get("t2")
    st.markdown(f"### {t['label']}: {side_txt(t['side'])} {t['qty']} BTC"); st.caption(f"{t['id']} | stage {t['stage']} | open {hrs:.0f} h of {t['expiry_h']} h | leverage {t.get('leverage')}x")
    if m: st.markdown(f"**{m['status']}**  (stage: {m['stage']}, exhaustion {m['exhaustion']}/100)")
    ci = t.get("confirm_info")
    if ci:
        (st.success if ci["state"] == "CONFIRMED" else st.warning if ci["state"] == "LOST" else st.info)(f"{'✅ CONFIRMED' if ci['state'] == 'CONFIRMED' else '⚠️ CONFIRMATION KAMZOR' if ci['state'] == 'LOST' else '⏳ Confirmation ka intezaar'}: {ci['score']}/{ci['total']} checks")
        with st.expander("Confirmation checks"):
            for c_ in ci["checks"]: st.markdown(f"{'✅' if c_[1] else '❌'} {c_[0]}: {c_[2]}")
    st.progress(float(min(max((px - t["sl"]) / (tgt - t["sl"]), 0), 1)), text=f"Stop ${t['sl']:,.0f}  ←  now ${px:,.0f}  →  Target ${tgt:,.0f}")
    st.table(pd.DataFrame([{"Entry": round(t["entry"]), "Now": round(px), "Open P/L": inr(usd * t.get("fx", 88)), "R": f"{ur:+.2f}", "Stop": round(t["sl"]), "Target": round(tgt), "Margin": inr(t["margin_inr"]), "Booked": ", ".join(e["kind"] for e in t.get("exits", [])) or "-"}]))
    if t.get("why"): st.info("💬 **Kyun liya:** " + t["why"])
    if (t.get("entry_ctx") or {}).get("methods_text"): st.caption("🧩 Doosri raay (entry ke waqt): " + t["entry_ctx"]["methods_text"])
    if m:
        for r_ in m["reasons"]: st.markdown("• " + r_)
        st.markdown(m["hold_vs_book"]); st.markdown("🔧 " + m["stop_advice"] + "  (salah hai, paper rule nahi badalta)"); st.caption(f"Agla decision zone ${m['next_zone']:,.0f}")

with tH_:
    live_widget(POS[0] if POS else None)
    c = st.columns(4); c[0].metric("Wallet equity", inr(eq), f"{(eq / start - 1) * 100:+.1f}% since start"); c[1].metric("Free cash", inr(W.get("cash", 0))); c[2].metric("In open trades", inr(W.get("margin", 0)))
    c[3].metric("Open positions", len(POS))
    if POS: st.info("Paper position(s) OPEN. Nothing to do: the tool closes them at stop, target or expiry.")
    elif M and M["signal"].startswith("EARLY"): st.warning(f"Experimental signal: {M['signal']}. No proven edge. Do NOT use real money.")
    else: st.success("WAIT: no trade setup right now. 'No trade' is a valid result.")
    st.subheader("Live positions")
    for t in POS: position_card(t); st.divider()
    if not POS: st.write("No open position.")
    RM = P.get("radar_move"); MW = S.get("move_watch")
    if RM:
        st.subheader("🚀 Move radar: kya achhi move aane wali hai?")
        a_, b_ = st.columns([1, 2]); a_.metric("Radar score", f"{RM['score']}/100", RM["state"].title()); b_.progress(min(RM["score"] / 100, 1.0), text=f"{RM['state']} | jhukaav: {({1: 'UPAR', -1: 'NEECHE', 0: 'saaf nahi'})[RM['lean']]} | typical move ~{RM['exp_pts']:,.0f} pts | trigger: ${RM['box_lo']:,.0f} ke neeche / ${RM['box_hi']:,.0f} ke upar band")
        (st.success if RM["state"] == "GOOD MOVE LIKELY" else st.info)("Parts: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in RM["parts"].items()) + (" | " + "; ".join(RM["notes"]) if RM["notes"] else ""))
        if MW:
            _mt = ("move shuru " + ("UPAR" if MW["triggered"] == 1 else "NEECHE") + " (start $" + format(MW.get("start", 0), ",.0f") + ")") if MW.get("triggered") else "trigger ka intezaar"
            st.warning(f"👀 Watch chalu: {_mt} | radar {MW['score']} par fire hua. Move poora hone par Telegram alert aayega.")
        if S.get("move_log"): 
            with st.expander("Pichle radar alerts ka natija (kitni baar sach nikla)"): st.dataframe(pd.DataFrame([{"time": x["ts"][5:16], "score": x["score"], "jhukaav": x["lean"], "natija": x["result"], "pts": x.get("traveled")} for x in S["move_log"][::-1]]), hide_index=True)
        st.caption("Radar sambhavna batata hai, guarantee nahi. Backtest (V10) ka sach Backtests tab mein hai.")
    MR = P.get("methods")
    if MR and MR.get("votes"):
        st.subheader("🧩 Multi-method analysis (7 tareeke)")
        (st.success if MR["verdict"] != "WAIT" else st.info)(f"Consensus: **{MR['verdict']}**  |  net {MR['net']:+.0f}  |  LONG {MR['long']} - SHORT {MR['short']} - neutral {MR['total'] - MR['long'] - MR['short']}")
        st.dataframe(pd.DataFrame([{"": "🟢" if v["dir"] == 1 else "🔴" if v["dir"] == -1 else "⚪", "Method": v["name"], "Vote": {1: "LONG", -1: "SHORT", 0: "neutral"}[v["dir"]], "Strength": v["strength"], "Kyun": v["why"]} for v in MR["votes"]]), hide_index=True, use_container_width=True)
        if MR.get("extras"): st.caption("Live second opinion: " + " | ".join(f"{'🟢' if x['dir'] == 1 else '🔴' if x['dir'] == -1 else '⚪'} {x['name']}: {x['why']}" for x in MR["extras"]))
        st.caption("Har trade ke saath ye 'doosri raay' bhi save hoti hai. Confluence strategy tabhi trade leti hai jab 4+ tareeke ek taraf hon.")
    RD = P.get("radar")
    if RD and not POS:
        st.subheader("Setup radar: how close is a trade?"); x, y = st.columns(2)
        for col, side in ((x, "LONG"), (y, "SHORT")):
            rows = RD[side]; col.markdown(f"**{'BUY' if side == 'LONG' else 'SELL'} setup (trend pullback): {sum(r[1] for r in rows)}/4**")
            for nm, ok_, val in rows: col.markdown(f"{'✅' if ok_ else '❌'} {nm}: {val}")
        st.caption("A trend-pullback trade opens only when all 4 are ✅ (about 1-2 times a week in backtests).")
    st.subheader("Market now")
    if M:
        a, b = st.columns(2); a.markdown(f"**Regime:** {M['regime']} | **Signal:** {M['signal']} (score {M['score']}/100)"); a.markdown("**For:** " + (", ".join(M["pro"]) or "-")); b.markdown("**Against:** " + (", ".join(M["con"]) or "-"))
        if M.get("scores"): st.markdown(f"**Accumulation** (buy-side evidence): {M['scores'].get('LONG', '-')}/100 | **Distribution** (sell-side evidence): {M['scores'].get('SHORT', '-')}/100")
        if M.get("reversal") not in (None, "none"): st.warning(f"🔄 {M['reversal']}")
    lg = load("market_log.csv", "csv")
    if lg is not None and len(lg) > 5:
        lg = lg.tail(288).set_index("ts"); x, y = st.columns(2); x.caption("BTC price (last ~24h)"); x.line_chart(lg["price"]); y.caption("Open interest USD (last ~24h)"); y.line_chart(lg["oi_usd"])

with tDD:
    D = S.get("desk") or {}; V7 = load("backtest_v7_results.json")
    if not A: st.info("Decision Desk appears after the next scan (needs the latest worker.py).")
    else:
        top = st.columns(4); top[0].metric("Price", f"${A['price']:,.0f}"); top[1].metric("Regime", A["regime"]); top[2].metric("Stage", A["stage"].split(":")[0]); top[3].metric("Timeframes", ((D.get("mtf") or {}).get("alignment") or "n/a").split(" (")[0])
        st.markdown(f"### {A['status']}"); st.caption(A["stage"] + "  |  Informational and probabilistic. Never a guaranteed prediction.")
        Qs = decision.build(A, M, D, POS[0] if POS else None, V7)
        with st.expander("❓ Before entry: is there a trade? (questions 1 to 16)", expanded=True):
            for n_, q_, a_ in Qs[:16]: st.markdown(f"**{n_}. {q_}**  \n{a_}")
        with st.expander("📊 After entry: hold or book? (questions 17 to 27)", expanded=bool(POS)):
            for n_, q_, a_ in Qs[16:]: st.markdown(f"**{n_}. {q_}**  \n{a_}")
        Lv = D.get("levels")
        if Lv:
            st.subheader("🧱 Key levels around price")
            rows_ = [dict(Level=f"${r['price']:,.0f}", Side="▲ resistance", Why=", ".join(r["names"]), Strength=r["strength"], Points=f"{r['dist_pts']:+,.0f}", Percent=f"{r['dist_pct']:+.2f}%", ATR_1h=f"{r['dist_atr1h']:+.1f}") for r in reversed(Lv["resistance"])]
            rows_.append(dict(Level=f"${Lv['price']:,.0f}", Side="● PRICE NOW", Why="", Strength="", Points="", Percent="", ATR_1h=""))
            rows_ += [dict(Level=f"${r['price']:,.0f}", Side="▼ support", Why=", ".join(r["names"]), Strength=r["strength"], Points=f"{r['dist_pts']:+,.0f}", Percent=f"{r['dist_pct']:+.2f}%", ATR_1h=f"{r['dist_atr1h']:+.1f}") for r in Lv["support"]]
            st.dataframe(pd.DataFrame(rows_), hide_index=True, use_container_width=True)
            if Lv.get("vwap"): st.caption(f"Today's VWAP ${Lv['vwap']['vwap']:,.0f}: price is {Lv['vwap']['dev_atr']:+.1f} ATR from it ({Lv['vwap']['note']}). Several reasons at one price (strong) means price has reacted there before. Not a guarantee.")
        Mv = D.get("moves")
        if Mv:
            st.subheader("📏 Point-move classes (adapt to current volatility)")
            st.table(pd.DataFrame([{"Move": f"{r['points']:,} pts", "% of price": f"{r['pct']}%", "x 4H ATR": r["atr4h_multiple"], "Size class": r["size_class"], **({"Up in 24h": f"{r['up_24h'] * 100:.0f}%", "Down in 24h": f"{r['dn_24h'] * 100:.0f}%", "Up in 72h": f"{r['up_72h'] * 100:.0f}%", "Down in 72h": f"{r['dn_72h'] * 100:.0f}%"} if "up_24h" in r else {})} for r in Mv["rows"]]))
            if Mv.get("typical_24h_points"): t_ = Mv["typical_24h_points"]; st.caption(f"Volatility now: {Mv['bucket_name']} (history sample {Mv['sample']} hours). Typical 24h travel (50/75/90/95th percentile): up {t_['up']} pts, down {t_['dn']} pts. {Mv['note']}")
            else: st.caption("Run the research workflow once to add the history-based odds. " + Mv["note"])
        c1, c2 = st.columns(2)
        with c1:
            Mt = D.get("mtf")
            if Mt: st.subheader("🕐 Multi-timeframe"); st.table(pd.DataFrame([{"Timeframe": r["tf"], "Role": r["role"], "Direction": r["direction"], "Trend strength": r["strength"]} for r in Mt["rows"]])); st.caption("Alignment: " + Mt["alignment"])
            Rv = D.get("reversal")
            if Rv:
                st.subheader("🔄 Reversal evidence"); st.progress(min(Rv["score"] / 100, 1.0), text=f"{Rv['note']} (score {Rv['score']}/100)")
                for s_ in Rv["signs"]: st.markdown("• " + s_)
                for s_ in Rv["against"]: st.markdown("✅ " + s_)
        with c2:
            Dv = D.get("derivs")
            if Dv:
                st.subheader("📡 Derivatives and order flow"); k_ = st.columns(3); k_[0].metric("Crowding", Dv["crowding"]); k_[1].metric("OI 4h", "n/a" if Dv["oi_change_4h"] is None else f"{Dv['oi_change_4h']:+.2f}%"); k_[2].metric("Taker delta", "n/a" if Dv["taker_delta"] is None else f"{Dv['taker_delta']:+.2f}")
                for s_ in Dv["items"]: st.markdown("• " + s_)
        SL_ = S.get("stage_log") or []
        if SL_:
            st.subheader("🪜 Stage history (the model can move backwards)"); st.dataframe(pd.DataFrame([{"Time (IST)": history.ist(x["ts"]), "Stage": x["stage"], "Status": x["status"], "Regime": x["regime"], "Price": round(x["price"])} for x in reversed(SL_[-15:])]), hide_index=True, use_container_width=True)
        Lz = A.get("levels")
        with st.expander("🧮 Profit-booking planner (choose your own percentages)"):
            if not Lz: st.write("No active setup, so there are no targets to plan with.")
            else:
                st.caption("Test different splits. The system does not assume you booked anything: you decide. The % are yours to customise (the spec says do not hard-code them).")
                p1 = st.slider("Book at Target 1 (%)", 0, 100, 30); p2 = st.slider("Book at Target 2 (%)", 0, 100 - p1, min(30, 100 - p1)); p3 = st.slider("Book at Target 3 (%)", 0, 100 - p1 - p2, min(20, 100 - p1 - p2)); run_ = 100 - p1 - p2 - p3
                g1, g2, g3 = st.columns(3); en_ = g1.number_input("Entry $", value=float(A["price"]), key="pl_en"); q_ = g2.number_input("Quantity BTC", value=0.01, step=0.001, format="%.4f", key="pl_q"); fx_ = g3.number_input("₹ per $1", value=float(P.get("fx", 88.0)), key="pl_fx")
                sd = 1 if A["direction"] != "SHORT" else -1; ex_ = Lz["extended"]; plan_ = [("Target 1", Lz["t1"], p1), ("Target 2", Lz["t2"], p2), ("Target 3", Lz["t3"], p3), (f"Runner (trail, shown at extended {ex_:,.0f})", ex_, run_)]
                rws = [{"Stage": n_, "Price": f"${p_:,.0f}", "Closes": f"{pc}%", "Points": f"{(p_ - en_) * sd:+,.0f}", "Profit ₹": inr((p_ - en_) * sd * q_ * pc / 100 * fx_)} for n_, p_, pc in plan_]
                st.table(pd.DataFrame(rws)); tot = sum((p_ - en_) * sd * q_ * pc / 100 * fx_ for _, p_, pc in plan_); loss = (en_ - Lz["preferred_sl"]) * sd * q_ * fx_
                st.write(f"If everything goes to plan: **{inr(tot)}**. If the stop {Lz['preferred_sl']:,.0f} is hit first: **{inr(-abs(loss))}**. The runner is only reached if the trade keeps going; trailing stops protect it.")

with tA:
    if not A: st.info("Analysis appears after the next scan (needs the latest worker.py).")
    else:
        c = st.columns(4); c[0].metric("Price", f"${A['price']:,.0f}"); c[1].metric("Regime", A["regime"]); c[2].metric("Direction lean", A["direction"]); c[3].metric("False-signal risk", A["false_signal_risk"])
        st.markdown(f"### {A['status']}"); st.caption(A["stage"]); s_ = A["scores"]
        names = [("Setup score", "setup"), ("Structure", "structure"), ("Momentum", "momentum"), ("Volume", "volume"), ("Order flow", "order_flow"), ("Liquidity", "liquidity"), ("Higher timeframe", "htf"),
                 ("Accumulation", "accumulation"), ("Distribution", "distribution"), ("Large-move potential", "large_move_potential"), ("Continuation", "continuation"), ("Exhaustion risk", "exhaustion_risk"), ("Volatility percentile", "volatility_pct")]
        c1, c2 = st.columns(2)
        for i, (lab, key) in enumerate(names):
            v = s_.get(key); (c1 if i % 2 == 0 else c2).progress(min(max((v or 0) / 100, 0), 1), text=f"{lab}: {'n/a' if v is None else round(v)}/100")
        st.caption("Scores are transparent heuristics, not calibrated probabilities. Order-flow uses the order-book imbalance and open interest the tool records itself.")
        L = A.get("levels")
        if L:
            st.subheader("Levels (informational)")
            st.table(pd.DataFrame([["Early entry zone", f"${L['early_zone'][0]:,.0f} - ${L['early_zone'][1]:,.0f}"], ["Confirmation entry", f"beyond ${L['confirmation']:,.0f}"], ["Retest entry zone", f"${L['retest_zone'][0]:,.0f} - ${L['retest_zone'][1]:,.0f}"],
                                   ["Late entry / avoid", f"beyond ${L['late_above']:,.0f}"], ["Hard invalidation", f"${L['hard_invalidation']:,.0f}"], ["Preferred stop", f"${L['preferred_sl']:,.0f}"], ["Emergency risk zone", f"${L['emergency_sl']:,.0f}"],
                                   ["Target 1 / 2 / 3", f"${L['t1']:,.0f} / ${L['t2']:,.0f} / ${L['t3']:,.0f}"], ["Extended", f"${L['extended']:,.0f}"], ["Risk/reward to T1", str(L["rr_t1"])]], columns=["Level", "Value"]))
            st.caption(f"{L['entry_state']}. Targets from: {L['targets_from']}.")
        E_ = A.get("expected_move")
        if E_:
            st.subheader("Expected move from history (similar volatility)"); mv = lambda r: f"${r[0]:,.0f} to ${r[1]:,.0f}"
            st.table(pd.DataFrame([["Expected", mv(E_["expected"])], ["Strong", mv(E_["strong"])], ["Extended", mv(E_["extended"])]], columns=["Move size (points, direction lean)", "Range"]))
            st.table(pd.DataFrame([{"Move": f"{k} pts", "Up within 24h": f"{v[0] * 100:.1f}%", "Down within 24h": f"{v[1] * 100:.1f}%"} for k, v in E_["odds"].items()])); st.caption(f"Based on {E_['sample']} similar hours. Estimates, not promises.")
        else: st.info("Run the 'research' workflow once to add history-based expected moves and point-move odds.")
        if A.get("checklist"): st.subheader("False-signal checklist")
        if A.get("checklist"):
            for t_, f in A["checklist"]: st.markdown(f"{'⚠️' if f else '✅'} {t_}")
        r_ = A["range"]; st.subheader("Range and breakout"); st.write(f"Range high ${r_['high']:,.0f} | mid ${r_['mid']:,.0f} | low ${r_['low']:,.0f} | price at {r_['position_pct']:.0f}% of range | **{A['breakout']}**")

with tW:
    c = st.columns(5); c[0].metric("Equity", inr(eq), f"{(eq / start - 1) * 100:+.1f}%"); c[1].metric("Start", inr(start)); c[2].metric("Free cash", inr(W.get("cash", 0))); c[3].metric("Trades closed", len(CL)); c[4].metric("Max drawdown", f"{P.get('max_dd_pct', 0)}%")
    st.caption(f"Rules: risk per trade {CFG['strategies']['trend_pullback']['risk_pct']}% (trend pullback) / {CFG['strategies']['early_signal']['risk_pct']}% (early signal) | leverage {CFG['wallet']['leverage']}x | fee {CFG['wallet']['fee_rate_per_side'] * 100:.2f}% per side | no real orders. Change with /set.")
    with st.expander("🧮 Position size calculator (for your own manual trades)"):
        x1, x2, x3 = st.columns(3); wv = x1.number_input("Wallet ₹", value=float(eq or 20000), step=1000.0); rp = x2.number_input("Risk % per trade", value=1.0, step=0.25); fxv = x3.number_input("₹ per $1", value=88.0)
        y1, y2 = st.columns(2); en = y1.number_input("Entry price $", value=float(lp or 80000)); sv = y2.number_input("Stop price $", value=float((lp or 80000) * 0.985))
        if abs(en - sv) > 0: q = (wv * rp / 100) / (abs(en - sv) * fxv); st.write(f"Quantity **{q:.4f} BTC** | position ${q * en:,.0f} (₹{q * en * fxv:,.0f}, {q * en * fxv / wv:.1f}x wallet) | money at risk ₹{wv * rp / 100:,.0f}")
    led = W.get("ledger", [])
    if led: st.markdown("**Equity curve**"); st.line_chart(pd.DataFrame(led).set_index("ts")["equity"])
    st.subheader("Trade journal (saved on GitHub: refresh ya browser band hone se kuch nahi jaata)")
    for t_ in (POS + list(reversed(CL)))[:15]:
        isopen = "R" not in t_
        with st.expander(f"{'🟢 OPEN' if isopen else '✔️ CLOSED'}  {t_['id']}  |  {t_.get('label', '')}  |  {t_.get('outcome', 'running')}  {('%+.2fR' % t_['R']) if not isopen else ''}", expanded=isopen):
            st.markdown("**Kyun liya:** " + (t_.get("why") or "-")); st.markdown("**Kya hua:** " + (t_.get("lesson") or "abhi trade chal raha hai"))
            fb = (t_.get("feedback") or {}); au = fb.get("auto") or {}
            if au: st.markdown("**Tool ka feedback:** " + au.get("verdict", ""))
            if fb.get("user"): st.markdown(f"**Aapka feedback:** {fb['user'].get('rating', '-')} {fb['user'].get('note', '')}")
            if t_.get("user_exit"): st.markdown(f"**Aapka exit:** ${t_['user_exit']['price']:,.0f} ({t_['user_exit']['pct']:+.2f}%) vs system {t_.get('R', '-')}R")
            st.caption(f"Qty {t_.get('qty')} BTC | entry ${t_['entry']:,.0f} | stop ${t_.get('sl0', t_.get('sl', 0)):,.0f} | exits: " + (", ".join(f"{e['kind']} {e['frac'] * 100:.0f}% @ ${e['price']:,.0f}" for e in t_.get("exits", [])) or "-"))
    if CL: st.subheader("Trade book"); st.dataframe(pd.DataFrame(CL).reindex(columns=["closed", "id", "label", "qty", "entry", "exit", "outcome", "gross_usd", "fees_usd", "pnl_inr", "R", "hold_h"]))
    if P.get("journal"): st.subheader("Activity log (newest first)"); st.dataframe(pd.DataFrame(P["journal"]).iloc[::-1].head(60))
    if led: st.subheader("Wallet ledger (newest first)"); st.dataframe(pd.DataFrame(led).iloc[::-1].head(80))
    if P.get("orders"): st.subheader("Order log (newest first)"); st.dataframe(pd.DataFrame(P["orders"]).iloc[::-1].head(60))

with tTH:
    st.caption("Permanent record of every trade the tool has ever taken or alerted. It is stored in its own file (trade_history.json): refreshing the page, upgrading the code or resetting the wallet never deletes it. All times are Indian time (IST).")
    HF = load("trade_history.json"); rec = dict((HF or {}).get("records", {}))
    for r_ in history._all_trades(S): rec[r_["id"]] = history._merge(rec.get(r_["id"]), r_)      # live trades not yet written to the file are shown too
    rows_ = sorted(rec.values(), key=lambda r: r.get("opened") or "", reverse=True)
    if not rows_: st.info("No trades recorded yet. The first one will appear here as soon as the tool takes or alerts a trade.")
    else:
        cl = [r for r in rows_ if r["source"] == "PAPER" and r["status"] == "CLOSED"]; wins = sum(1 for r in cl if (r.get("pnl_inr") or 0) > 0); net = sum(r.get("pnl_inr") or 0 for r in cl)
        m = st.columns(5); m[0].metric("All trades", len(rows_)); m[1].metric("Open now", sum(r["status"] == "OPEN" for r in rows_)); m[2].metric("Paper closed", len(cl), f"{wins} win / {len(cl) - wins} loss"); m[3].metric("Paper net P/L", inr(net)); m[4].metric("Alert signals", sum(r["source"] == "SIGNAL" for r in rows_))
        with st.expander("📊 Performance (paper-wallet closed trades)", expanded=len(cl) > 0):
            A = stats.analyse(rec.values(), float((S.get("paper") or {}).get("wallet", {}).get("start", 20000))); o = A["overall"]; st.info("🧪 " + A["verdict"])
            if o.get("n"):
                q = st.columns(6); q[0].metric("Win rate", f"{o['win_pct']}%"); q[1].metric("Avg R / trade", f"{o['mean_R']:+.2f}", f"± {o['se']}" if o.get("se") is not None else None); q[2].metric("Profit factor", o["profit_factor"] or "-"); q[3].metric("Max drawdown", f"{A['max_drawdown_pct']}%")
                q[4].metric("Best win streak", A["streaks"]["best_win_streak"]); q[5].metric("Worst loss streak", A["streaks"]["worst_loss_streak"])
                st.line_chart(pd.DataFrame({"Equity ₹ (closed trades)": A["curve"]}))
                for title, key in (("By side", "by_side"), ("By strategy", "by_strategy"), ("By how it ended", "by_outcome"), ("By weekday (IST, entry time)", "by_weekday"), ("By time of day (IST, entry time)", "by_hour_block")):
                    if A[key]: st.markdown(f"**{title}**"); st.table(pd.DataFrame(A[key]).T[["n", "win_pct", "mean_R", "net_inr", "profit_factor"]].rename(columns={"n": "Trades", "win_pct": "Win %", "mean_R": "Avg R", "net_inr": "Net ₹", "profit_factor": "Profit factor"}))
                st.caption("Small groups (under 30 trades) are noise. Do not change any rule based on them.")
        f1, f2, f3, f4 = st.columns(4)
        fs = f1.multiselect("Type", ["PAPER", "SIGNAL"], default=["PAPER", "SIGNAL"], format_func=lambda x: "Paper wallet trade" if x == "PAPER" else "Early-signal alert")
        fst = f2.multiselect("Status", ["OPEN", "CLOSED"], default=["OPEN", "CLOSED"]); fsd = f3.multiselect("Side", ["LONG", "SHORT"], default=["LONG", "SHORT"]); q = f4.text_input("Search (ID, reason, outcome)").strip().lower()
        sel = [r for r in rows_ if r["source"] in fs and r["status"] in fst and r.get("side") in fsd and (not q or q in json.dumps({k: r.get(k) for k in ("id", "why", "outcome", "label", "user_note", "lesson")}, default=str).lower())]
        fbtxt = lambda r: {"good": "👍 good", "bad": "👎 bad"}.get(r.get("user_rating"), "") + (" " + r["user_note"] if r.get("user_note") else "")
        tbl = pd.DataFrame([{"Trade ID": r["id"], "Type": "Paper" if r["source"] == "PAPER" else "Alert", "Strategy": r.get("label") or r.get("strategy"), "Side": r.get("side"), "Opened (IST)": r.get("opened_ist"), "Closed (IST)": r.get("closed_ist") or "-",
                             "Entry": round(r["entry"]) if r.get("entry") else None, "Exit": round(r["exit"]) if r.get("exit") else None, "Status": r["status"], "Outcome": r.get("outcome") or "-", "R": r.get("R"),
                             "P/L ₹": r.get("pnl_inr"), "Your feedback": fbtxt(r), "Why taken": r.get("why", "")} for r in sel])
        st.dataframe(tbl, hide_index=True, use_container_width=True); st.download_button("⬇️ Download full history (CSV)", tbl.to_csv(index=False).encode(), "trade_history.csv", "text/csv")
        if sel:
            pick_ = st.selectbox("Open one trade", [r["id"] for r in sel]); r = rec[pick_]; st.markdown(f"### {r['id']}  ·  {r.get('label') or ''}  ·  {r.get('side')}")
            st.write(f"**Opened:** {r.get('opened_ist')}  |  **Closed:** {r.get('closed_ist') or 'still open'}  |  **Status:** {r['status']}  |  **Outcome:** {r.get('outcome') or '-'}")
            st.info("💬 **Why this trade was taken:** " + (r.get("why") or "-"))
            plan = {"Entry": r.get("entry"), "Stop-loss": r.get("stop"), **{f"Target {i + 1}": x for i, x in enumerate(r.get("targets") or [])}, "Exit (avg)": r.get("exit"), "Qty BTC": r.get("qty_btc"), "Margin ₹": r.get("margin_inr"), "R": r.get("R"), "P/L ₹": r.get("pnl_inr"), "Hold hours": r.get("hold_h"), "Best R": r.get("best_R"), "Worst R": r.get("worst_R")}
            st.table(pd.DataFrame([{k: (round(v, 2) if isinstance(v, float) else v) for k, v in plan.items() if v is not None}]))
            if r.get("lesson"): st.write("**What happened:** " + r["lesson"])
            if r.get("auto_feedback"): st.write("**Tool's own review:** " + r["auto_feedback"])
            st.write("**Your feedback:** " + (fbtxt(r) or "none yet (use the 👍 / 👎 buttons or /note on Telegram)") + (f"  ({r['user_feedback_ist']})" if r.get("user_feedback_ist") else ""))
            if r.get("user_exit"): st.write(f"**Your own exit:** ${r['user_exit']['price']:,.0f} ({r['user_exit']['pct']:+.2f}%) {r['user_exit'].get('note') or ''}")
            if r.get("timeline"): st.write("**Timeline**"); st.dataframe(pd.DataFrame(r["timeline"]).rename(columns={"time_ist": "Time (IST)", "type": "Event", "price": "Price", "note": "Note"}), hide_index=True, use_container_width=True)
            with st.expander("Everything stored for this trade (raw)"): st.json(r.get("raw", r))
    st.caption(f"Record file last updated: {history.ist((HF or {}).get('updated')) or 'not created yet (it is created on the next scan)'}")

with tCH:
    st.caption("Price action chart: candles, EMA20/50, swing points, candle patterns (▲ bullish / ▼ bearish, sirf support/resistance ke paas wale), support/resistance, trade ki entry/stop/target, aur daayen taraf har price par buy (hara) vs sell (laal) volume.")
    if CH is None: st.error("Chart ke liye 'plotly' chahiye. GitHub par requirements.txt upload karo (usme plotly likha hai), phir app Reboot karo. Detail: " + _CH_ERR)
    else:
        @st.cache_data(ttl=60)
        def candles_for(tf):
            try: return ENG.candles(tf, 300), "live"
            except Exception: pass
            cd = load("chart_data.json")
            if cd and cd.get(tf): return pd.DataFrame(cd[tf], columns=["ts", "o", "h", "l", "c", "v"]), "saved " + str(cd.get("built", ""))[:16] + " UTC"
            return None, "no data"
        c1, c2, c3 = st.columns([3, 2, 2]); tf = c1.radio("Timeframe", ["5m", "15m", "1H", "4H"], index=2, horizontal=True); nb = c2.selectbox("Candles", [60, 100, 150, 220], index=1); pw = c3.selectbox("Order-flow window", ["4 ghante", "24 ghante", "off"])
        o1, o2, o3 = st.columns(3); sp = o1.checkbox("Candle patterns", True); ss = o2.checkbox("Sirf mazboot patterns", True); sw = o3.checkbox("Swing points", True)
        dfc, srcn = candles_for(tf)
        if dfc is None or len(dfc) < 100: st.warning("Candle data nahi mil raha (exchange block ya data nahi). Thodi der baad Refresh karo.")
        else:
            px_ = float(dfc.c.iloc[-1]); lv_ = SRM.levels_for(dfc, px_); zones_ = ((S.get("sr") or {}).get("zones")) or []
            OP = load("orderflow_profile.json"); prof_ = OFM.profile_rows(OP, dt.datetime.now(dt.timezone.utc), 240 if pw.startswith("4") else 1440) if (OP and pw != "off") else None
            closed_ = [r for r in ((load("trade_history.json") or {}).get("records") or {}).values() if r.get("source") == "PAPER" and r.get("entry")][-12:]
            fig_ = CH.make_figure(dfc, tf, lv_, zones_, POS, closed_, prof_, bars=nb, show_patterns=sp, show_swings=sw, strong_only=ss, height=620)
            st.plotly_chart(fig_, use_container_width=True, config=dict(displayModeBar=False, scrollZoom=False)); st.caption(f"Candle data: {srcn} | time IST | blue = entry, red dashed = stop, green dashed = target, shaded = kai timeframe ke saath wali zone")
        OFA = S.get("orderflow")
        if OFA and OFA.get("now"):
            st.subheader("🌊 Kahan aggressive buying / selling ho rahi hai")
            nw_ = OFA["now"]; (st.success if "BUY" in nw_["state"] and "AGGRESSIVE" in nw_["state"] else st.error if "SELL" in nw_["state"] and "AGGRESSIVE" in nw_["state"] else st.info)(f"Abhi (60 min): **{nw_['state']}** | buy {nw_['buy']:,.0f} BTC vs sell {nw_['sell']:,.0f} BTC | delta {nw_['ratio'] * 100:+.0f}% | bade orders {nw_['big_share'] * 100:.0f}%")
            q1, q2, q3 = st.columns(3); q1.metric("4 ghante", OFA["h4"]["state"].title(), f"delta {OFA['h4']['ratio'] * 100:+.0f}%"); q2.metric("24 ghante", OFA["h24"]["state"].title(), f"delta {OFA['h24']['ratio'] * 100:+.0f}%"); q3.metric("Data jama", f"{OFA['history_h']} ghante", f"coverage {OFA.get('coverage_pct', '?')}%")
            za, zb = st.columns(2)
            za.markdown("**🟢 Buying ka dabaav wale price zones (4h, delta +40% se zyada = aggressive)**"); za.dataframe(pd.DataFrame([{"zone": f"${z['lo']:,.0f}-{z['hi']:,.0f}", "volume BTC": z["vol"], "delta %": round(z["ratio"] * 100), "bade orders %": round(z["big_share"] * 100)} for z in OFA["buy_zones"]]) if OFA["buy_zones"] else pd.DataFrame({"info": ["koi saaf zone nahi"]}), hide_index=True)
            zb.markdown("**🔴 Selling ka dabaav wale price zones (4h, delta -40% se kam = aggressive)**"); zb.dataframe(pd.DataFrame([{"zone": f"${z['lo']:,.0f}-{z['hi']:,.0f}", "volume BTC": z["vol"], "delta %": round(z["ratio"] * 100), "bade orders %": round(z["big_share"] * 100)} for z in OFA["sell_zones"]]) if OFA["sell_zones"] else pd.DataFrame({"info": ["koi saaf zone nahi"]}), hide_index=True)
            if OFA.get("poc"): st.caption(f"📍 Sabse zyada trading: ${OFA['poc']['lo']:,.0f}-{OFA['poc']['hi']:,.0f} ({OFA['poc']['vol']:,.0f} BTC). Aggressive = taker (market order) bahut zyada, bade orders (2+ BTC) ya volume normal se 1.5x. Delta = (buy-sell)/total.")
        else: st.info("Order-flow data abhi jama ho raha hai (naya worker chalne ke ~1 ghante baad poori tasveer aati hai).")
        SRD = S.get("sr")
        if SRD and SRD.get("tf"):
            st.subheader("📐 Timeframe ke hisaab se Support / Resistance")
            rows_ = []
            for tf_ in SRM.TFS:
                v_ = SRD["tf"].get(tf_)
                if v_: rows_.append({"Timeframe": tf_, "Support (paas wala pehle)": " | ".join(f"${x['price']:,.0f} ({x['touches']}x, {x['dist_pct']:+.1f}%)" for x in v_["supports"]) or "-", "Resistance": " | ".join(f"${x['price']:,.0f} ({x['touches']}x, {x['dist_pct']:+.1f}%)" for x in v_["resistances"]) or "-"})
            st.dataframe(pd.DataFrame(rows_), hide_index=True, use_container_width=True)
            if SRD.get("zones"): st.markdown("**🎯 Confluence zones (kai timeframe ek jagah, sabse mazboot):**\n\n" + "\n\n".join(f"{'🟢' if z['kind'] == 'support' else '🔴'} {z['kind']} **${z['lo']:,.0f}-{z['hi']:,.0f}** ({' + '.join(z['tfs'])}, score {z['score']})" for z in SRD["zones"][:5]))
            st.caption("touches = kitni baar bhaav is level se palta. Zyada touches + zyada timeframe = mazboot level. Bade timeframe (4H, 1D) ke level chhote timeframe se zyada maane jaate hain.")

with tRV:
    st.caption("Tool ko chalne do. Jab 30+ trades band ho jayein, neeche se review pack download karo aur mujhe (Claude ko) bhejo. Main uske hisaab se rules tune karunga.")
    _rec = list(((load("trade_history.json") or {}).get("records") or {}).values())
    try: PK = review.pack(S, records=_rec)
    except Exception as e: PK = None; st.error(f"Review pack error: {e}")
    if PK:
        rd = PK["readiness"]; st.progress(min(rd["closed"] / rd["target"], 1.0), text=f"{rd['closed']}/{rd['target']} paper trades band (strong review: {rd['strong_target']})"); (st.success if rd["ready"] else st.info)(rd["message"])
        c1, c2, c3 = st.columns(3); o = PK["overall"]; c1.metric("Closed trades", o.get("n", 0)); c2.metric("Win rate", f"{o.get('win_pct', 0)}%" if o.get("n") else "-"); c3.metric("Average R", o.get("mean_R", "-"))
        sh = PK["shadows"]; st.markdown(f"**Shadow trades (bina risk ke extra data):** near-miss {sh['near_miss']['finished']}/{sh['near_miss']['tracked']} poore, filter-blocked {sh['filter_blocked']['finished']}/{sh['filter_blocked']['tracked']} poore.")
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Review pack (JSON, poora)", json.dumps(PK, indent=1, default=str).encode(), "review_pack.json", "application/json")
        d2.download_button("⬇️ Short summary (.md, chat mein paste karne ke liye)", review.pack_md(PK).encode(), "review_pack.md", "text/markdown")
        st.caption("Telegram par bhi: /export bhejo to dono files aa jayengi. 30 trades hone par bot khud bhej dega.")
        for nm, g in PK["calibration"].items():
            if g: 
                with st.expander("Calibration: " + nm.replace("by_", "by ")): st.dataframe(pd.DataFrame(g).T[["n", "win_pct", "mean_R", "net_inr", "small_sample"]], use_container_width=True)
        SC = PK.get("smart_exit_compare") or {}
        if SC.get("finished") or SC.get("pending"):
            st.markdown(f"**Smart exit vs asli rule** (shadow copy): {SC['finished']} poore, {SC['pending']} baaki. " + (f"Smart avg {SC['mean_smart_R']}R vs asli rule {SC['mean_fixed_R']}R | smart behtar {SC['smart_better']} baar, asli rule behtar {SC['fixed_better']} baar." if SC.get("finished") else "Natija shadow trades poore hone par aayega."))
        with st.expander("Review pack ka text preview"): st.code(review.pack_md(PK))

with tTM:
    TS = load("time_stats.json"); TC = S.get("timing")
    st.caption("BTC kis samay (IST) zyada hilta hai, kitne points, upar aur neeche alag. Pichle 1 saal ki 1H candles se bana. Samay ka pattern bharosemand hai, direction ka nahi.")
    if TC:
        c1, c2, c3, c4 = st.columns(4); c1.metric("Abhi (IST)", TC["ist"], f"{TC['session']} session"); c2.metric("Activity", TC["cls"], f"{TC['activity']}% of average")
        c3.metric("Typical range / ghanta", f"{TC['avg_range']:,.0f} pts", f"up {TC['avg_up']:,.0f} | down {TC['avg_down']:,.0f}"); c4.metric("500+ pts ki sambhavna", f"{TC['p_range_500'] * 100:.0f}%", f"1000+: {TC['p_range_1000'] * 100:.0f}%")
        if TC.get("next_high"): n_ = TC["next_high"]; st.info(f"⏰ Agla HIGH window: {n_['ist']} IST ({n_['in_min']} min baad). Typical range {n_['avg_range']:,.0f} pts (upar {n_['avg_up']:,.0f} / neeche {n_['avg_down']:,.0f}).")
    if TS:
        hh = pd.DataFrame(TS["hours"]); hh["ghanta (IST)"] = hh["ist"]
        st.subheader("Ghante ke hisaab se move (points)"); st.bar_chart(hh.set_index("ghanta (IST)")[["avg_up", "avg_down"]])
        show_ = hh[["ist", "cls", "session", "avg_range", "avg_up", "avg_down", "p_range_500", "p_range_1000", "pct_green", "significant_bias", "n"]].rename(columns={"ist": "IST", "cls": "activity", "avg_range": "avg range", "avg_up": "avg up", "avg_down": "avg down", "p_range_500": "P(range>=500)", "p_range_1000": "P(>=1000)", "pct_green": "% green", "significant_bias": "direction bias?"})
        st.dataframe(show_, hide_index=True, use_container_width=True)
        a_, b_ = st.columns(2); a_.subheader("Sessions"); a_.dataframe(pd.DataFrame(TS["sessions"]), hide_index=True); b_.subheader("Weekday (daily range)"); b_.dataframe(pd.DataFrame(TS["weekdays"]), hide_index=True)
        if TS.get("recent"):
            with st.expander("Pichle 60 din vs poori history (activity %)"): st.dataframe(pd.DataFrame({"IST": [r["ist"] for r in TS["hours"]], "poori history": [r["activity"] for r in TS["hours"]], "pichle 60 din": [r["activity"] for r in TS["recent"]]}), hide_index=True)
        st.caption(f"Data: {TS['days']} din ({TS['first']} se), {TS['rows']} candles. Last build {TS['built'][:16]} UTC. {TS['note']}")
    else: st.info("Time stats abhi bani nahi. Naya worker pehli baar chalte hi ~1 minute mein bana lega (history download hoti hai).")
    try:
        _p = review.pack(S, records=list(((load("trade_history.json") or {}).get("records") or {}).values()))["calibration"]
        for k_, t_ in (("by_hour_class", "Tool ke apne trades: activity class ke hisaab se"), ("by_hour_utc", "Tool ke apne trades: ghante (UTC) ke hisaab se")):
            if _p.get(k_): st.markdown(f"**{t_}**"); st.dataframe(pd.DataFrame(_p[k_]).T[["n", "win_pct", "mean_R", "net_inr"]], use_container_width=True)
    except Exception: pass

with tL:
    st.info("The tool records every trade, studies its losses, and proposes filters. It does NOT rewrite its rules after each loss: with a ~33% win rate most losses are normal. A filter starts only after you approve it in Telegram (/approve N) and switches itself off if the trades it blocks do as well as the ones it allows.")
    L_ = P.get("lessons") or {}; cl = [t for t in CL if t.get("lesson")]
    c = st.columns(3); c[0].metric("Trades studied", L_.get("n", 0)); c[1].metric("Active filters", sum(f.get("active", True) for f in P.get("filters", []))); c[2].metric("Ideas waiting", len(P.get("proposals", [])))
    st.subheader("Lesson from each trade")
    if cl: st.dataframe(pd.DataFrame(cl).reindex(columns=["closed", "id", "outcome", "R", "mfe_R", "mae_R", "hold_h", "lesson"]).rename(columns={"mfe_R": "Best R", "mae_R": "Worst R", "hold_h": "Hours held"}))
    else: st.write("No closed paper trades yet.")
    st.subheader("Patterns across trades"); st.caption(L_.get("note", ""))
    if L_.get("patterns"): st.dataframe(pd.DataFrame(L_["patterns"])[["feature", "bucket", "n", "mean_R", "rest_R", "z"]])
    for p in P.get("proposals", []): st.warning(f"💡 #{p['id']}: {p['text']} (n={p['n']}, {p['mean_R']:+.2f}R vs {p['rest_R']:+.2f}R). To use it, send /approve {p['id']} in Telegram.")
    for f in P.get("filters", []):
        b = [s["R"] for s in P.get("shadow", []) if s.get("filter") == f["text"] and "R" in s]
        st.write(f"{'✅ ON' if f.get('active', True) else '⏸ OFF'}  Filter #{f['id']}: {f['text']} | blocked trades checked: {len(b)}" + (f", average {sum(b) / len(b):+.2f}R" if b else ""))

with tHl:
    st.caption("One-glance check that every part of the tool is alive.")
    rl = load("market_log.csv", "csv"); sa = amin(M["ts"]) if M else None; ls = amin(T.get("last_send_ok")); lc = amin(T.get("last_cmd_ts")); pr = amin((P.get("radar") or {}).get("ts")); aa = amin(None)
    rows_h = [["Scanner (GitHub Action)", sa is not None and sa < 30, f"last scan {sa:.0f} min ago" if sa is not None else "no scan yet", "Open the Actions tab, cancel any stuck run, then Run workflow"],
              ["Exchange data", bool(M) and (M.get("price") or 0) > 0, f"BTC ${M['price']:,.0f}" if M else "no data", "The exchange may be blocking GitHub servers"],
              ["Telegram bot token", bool(T.get("token_ok")), f"bot @{T.get('bot')}" if T.get("token_ok") else "not verified yet", "Recheck the TG_TOKEN secret"],
              ["Telegram sending", bool(T.get("last_send_ok")) and not T.get("last_error"), f"last message {ls:.0f} min ago" if ls is not None else "none yet", T.get("last_error") or "Run the workflow manually: 'Bot connected' should arrive"],
              ["Telegram commands (/ping)", lc is not None, f"last '{T.get('last_cmd')}' {lc:.0f} min ago" if lc is not None else "no command received yet", "Send /ping to your bot"],
              ["Data recorder (OI, funding)", rl is not None and len(rl) > 0, f"{len(rl)} rows logged" if rl is not None else "no log yet", "market_log.csv must exist (scan.yml must git add it)"],
              ["Paper wallet + engine", bool(W) and pr is not None and pr < 30, f"wallet ok, radar {pr:.0f} min ago" if pr is not None else "not running", "Look for 'paper error' in the Run worker log"],
              ["Analysis snapshot", bool(A), "ready" if A else "missing", "Needs the latest worker.py and analysis.py"],
              ["Learning module", "lessons" in P, "ready" if "lessons" in P else "not started", "Upload learn.py"]]
    bad = [r for r in rows_h if not r[1]]; (st.success("All checks green.") if not bad else st.warning(f"{len(bad)} check(s) need attention."))
    st.table(pd.DataFrame([["✅" if r[1] else "❌", r[0], r[2], "" if r[1] else r[3]] for r in rows_h], columns=["", "Check", "Detail", "If red, do this"]))
    _lg = T.get("log") or []
    if _lg:
        with st.expander(f"📬 Telegram delivery log (last {len(_lg)} sends)"): st.dataframe(pd.DataFrame([dict(time_utc=x["ts"][5:16], ok="✅" if x["ok"] else "❌", category=x["cat"], message=x["text"]) for x in _lg[::-1]]), hide_index=True, use_container_width=True)
    if T.get("foreign_chat"): st.error(f"A message reached the bot from a chat ending {T['foreign_chat']}, but your TG_CHAT_ID secret ends {T.get('chat_mask', '?')}. The bot ignores other chats. Fix the TG_CHAT_ID secret.")
    if T.get("poll_error"): st.error(f"Telegram polling problem: {T['poll_error']}")

with tS:
    st.caption("Current settings (read from config.json). Change from Telegram: /config, /set naam value, /notify naam on|off. Or edit config.json on GitHub.")
    for sec in ("wallet", "schedule", "timing", "risk"):
        if isinstance(CFG.get(sec), dict): st.markdown(f"**{sec}**"); st.table(pd.DataFrame([CFG[sec]]))
    st.markdown("**alerts**"); st.table(pd.DataFrame([{k: "on" if v else "off" for k, v in CFG["alerts"].items()}]))
    for s_, v in CFG["strategies"].items(): st.markdown(f"**strategy: {s_}**"); st.table(pd.DataFrame([v]))
    st.info("Backtested rule: trend_pullback stop 3×ATR, target 4R, expiry 120h. Changing these makes new trades differ from what was tested.")

with tO:
    st.warning("Early-signal engine (experimental). Its backtest was negative, so this is for learning. The paper wallet trades it separately as 'Early Signal'.")
    Tr = S.get("trades", {})
    if Tr:
        df = pd.DataFrame(Tr.values()); st.dataframe(df[["id", "signal", "score", "entry", "sl", "t1", "t2", "t3", "status", "outcome"]].round(0))
        pick = st.query_params.get("trade"); ids = list(Tr); tid = st.selectbox("Review a trade", ids, index=ids.index(pick) if pick in ids else len(ids) - 1); t = Tr[tid]
        a, b = st.columns(2); a.markdown(f"**Why:** {', '.join(t['pro'])}"); b.markdown(f"**Against:** {', '.join(t['con']) or '-'}")
        st.table(pd.DataFrame([{"Zone": f"{t['zone'][0]:,.0f}-{t['zone'][1]:,.0f}", "Stop": round(t["sl0"]), "T1": round(t["t1"]), "T2": round(t["t2"]), "T3": round(t["t3"]), "Extended": round(t["ext"]), "Confirm": round(t["confirm"]), "Best move pts": round(t["mfe"]), "Worst dip pts": round(t["mae"])}]))
        st.caption(f"System outcome: {t['outcome'] or 'open'} | Your input: {t['user'] or 'none'}"); st.dataframe(pd.DataFrame(t["events"])[["ts", "type", "price", "note"]])
    else: st.write("No old-style signals yet.")

with tB:
    st.caption("What was tested on past data, in plain words.")
    v1, v3, v4, v5, v6, ms = (load(f) for f in ("backtest_results.json", "backtest_v3_results.json", "backtest_v4_results.json", "backtest_v5_results.json", "backtest_v6_results.json", "move_stats.json")); rows = []
    def add_row(name, fn):          # one odd or older results file must never break the whole page
        try: rows.append([name, *fn()])
        except Exception: rows.append([name, "result file is in an older format (run the research workflow again)", "-"])
    def _m(d): return d.get("mean_R", d.get("exp_R")) if isinstance(d, dict) else None
    if v1: add_row("V1: early signals", lambda: (f"{v1['all']['n']} signals, target 1 before stop {v1['all']['t1_before_stop_%']}% (random ~40%)", "No edge"))
    if v3: add_row("V3: tuned stops and targets", lambda: (f"unseen test {_m((v3.get('best') or {}).get('test') or v3.get('test'))}R per trade (original {_m((v3.get('original_rules') or {}).get('test') or v3.get('old_config_test'))}R)", v3["verdict"]))
    if v4: add_row("V4: 4 other strategies", lambda: ("trend_pullback looked best, others failed", v4["verdict"]))
    if v5: add_row("V5: 5-year check of trend_pullback", lambda: (f"older unseen trades: {v5['central_fresh_oos'].get('mean_R')}R per trade (n={v5['central_fresh_oos'].get('n')}, error ±{v5['central_fresh_oos'].get('se')})", v5["verdict"]))
    if v6: add_row("V6: exit styles", lambda: (f"{v6['trades']} trades, 7 styles", v6["verdict"]))
    if rows: st.table(pd.DataFrame(rows, columns=["Test", "Result", "Verdict"]))
    if v6: st.subheader("Exit styles (older unseen trades, after fees)"); st.table(pd.DataFrame([{"Style": k, "Avg R": v["fresh_oos"].get("mean_R"), "Win %": v["fresh_oos"].get("win_%"), "Max drawdown R": v["fresh_oos"].get("max_drawdown_R"), "vs live rule": v["vs_current_fresh"]["diff_R"]} for k, v in v6["policies"].items()]))
    if v1:
        a_ = v1["all"]; st.subheader("Historical odds of point moves (early-signal setups, 1 year)")
        st.table(pd.DataFrame([{"Move reached before the stop": f"+{x:,} points", "Share of setups": f"{a_[f'p{x}_before_stop_%']}%"} for x in (500, 1000, 2000, 5000)]))
    if ms: q = ms["Q"]["24"]; st.subheader("Typical 24h move by volatility (history)"); st.table(pd.DataFrame([{"Volatility": n, "Median up %": q[k]["up"][0], "Median down %": q[k]["dn"][0], "90th pct up %": q[k]["up"][2], "90th pct down %": q[k]["dn"][2]} for k, n in (("0", "calm"), ("1", "normal"), ("2", "wild"))]))
    st.info("R = result in units of risk. +0.10R means earning 10% of the amount risked per trade on average. Errors this large mean it cannot be told apart from zero yet.")

    V7_ = load("backtest_v7_results.json")
    if V7_ and not V7_.get("error"):
        st.subheader("🧪 V7 full scorecard (live strategy, spec section 33)"); st.caption(V7_["note"]); st.info(f"{V7_['trades']} past entries | verdict: {V7_['verdict']}")
        o_, f_ = V7_["overall"], V7_["fresh_oos"]; q_ = st.columns(6); q_[0].metric("Win rate", f"{o_['win_pct']}%"); q_[1].metric("Avg R", o_["avg_R"]); q_[2].metric("Profit factor", o_["profit_factor"]); q_[3].metric("Max drawdown", f"{o_['max_drawdown_R']}R"); q_[4].metric("Unseen-trade avg R", f_.get("avg_R", "n/a"), f"± {f_.get('se', '')}"); q_[5].metric("False-signal rate", f"{V7_['stops']['false_signal_rate_pct']}%")
        st.markdown("**Target hit rates (reached BEFORE the stop) and time taken**"); st.table(pd.DataFrame([{"Target": v["label"], "Hit before stop %": v["hit_before_stop_pct"], "Unseen trades %": v["hit_fresh_pct"], "Median hours": v["median_hours"]} for v in V7_["targets"].values()]))
        s_ = V7_["stops"]; e_ = V7_["excursions"]; st.write(f"Stopped before +1R: **{s_['stop_before_1R_pct']}%** | stop touched at all: {s_['stop_touched_pct']}% (median {s_['median_hours_to_stop']} h) | no result in 120 h: {s_['expired_no_result_pct']}% | best excursion (50/75/90th pct): {e_['mfe_R_p50_p75_p90']} R | worst: {e_['mae_R_p50_p75_p90']} R | typical risk {e_['median_risk_points']:,} pts")
        st.markdown("**How often price travelled N points after entry**"); st.table(pd.DataFrame([{"Move": f"{k} pts", "Before stop %": v["reached_before_stop_pct"], "At any time %": v["reached_any_time_pct"]} for k, v in e_["points"].items()]))
        st.markdown("**Four ways to trade the same entries**"); st.table(pd.DataFrame([{"Method": k, "Avg R (all)": v["all"].get("avg_R"), "Win %": v["all"].get("win_pct"), "Max DD R": v["all"].get("max_drawdown_R"), "Unseen avg R": v["fresh"].get("avg_R")} for k, v in V7_["four_ways"].items()]))
        st.markdown("**Early vs late entry (fixed 4R)**"); st.table(pd.DataFrame([{"Entry": k, "Avg R": v.get("avg_R"), "Win %": v.get("win_pct"), "Profit factor": v.get("profit_factor")} for k, v in V7_["entry_delay"].items()]))
        for ttl, key in (("By side", "by_side"), ("By volatility", "by_volatility"), ("By trend strength", "by_trend_strength"), ("By year", "by_year")):
            st.markdown(f"**{ttl}**"); st.table(pd.DataFrame(V7_[key]).T[["n", "avg_R", "win_pct", "profit_factor", "max_drawdown_R"]])
    else: st.info("Run the 'research' workflow once to build the V7 scorecard (it also builds the move statistics).")

    V10 = load("backtest_v10_results.json")
    if V10:
        st.markdown(f"**Move radar (V10): {V10['verdict']}** (agle {V10['forward_hours']} ghante mein {V10['big_move_atr']}x ATR se badi move)")
        _u = V10["buckets"]["unseen_second_half"]; st.dataframe(pd.DataFrame({k: {"signals": v.get("n"), "badi move %": v.get("big_rate"), "avg move pts": v.get("avg_move_pts"), "lean sahi %": v.get("lean_right_pct")} for k, v in _u.items()}).T)
    else: st.caption("Move radar (V10) ka backtest abhi nahi chala: GitHub Actions > research > Run workflow.")
    V9 = load("backtest_v9_results.json")
    if V9:
        st.markdown(f"**Multi-method Confluence (V9): {V9['verdict']}** (koi parameter fit nahi kiya; 3 fixed strictness levels)")
        st.dataframe(pd.DataFrame({k: {"trades": v["all"].get("n"), "win %": v["all"].get("win_pct"), "avg R": v["all"].get("mean_R"), "lower 95%": v["all"].get("lo95"), "1st half R": v["first_half"].get("mean_R"), "2nd half R": v["second_half"].get("mean_R"), "long R": v["long"].get("mean_R"), "short R": v["short"].get("mean_R")} for k, v in V9["variants"].items()}).T)
    else: st.caption("Confluence (V9) ka backtest abhi nahi chala: GitHub Actions > research > Run workflow.")
    V8 = load("backtest_v8_results.json")
    if V8:
        st.markdown(f"**Session Breakout (V8): {V8['verdict']}** (time classes pehle aadhe data se seekhe, test baaki aadhe par)")
        st.dataframe(pd.DataFrame({k: {"trades": v["test"].get("n"), "win %": v["test"].get("win_pct"), "avg R": v["test"].get("mean_R"), "lower 95%": v["test"].get("lo95"), "long avg R": v["long"].get("mean_R"), "short avg R": v["short"].get("mean_R")} for k, v in V8["variants"].items()}).T)
    else: st.caption("Session Breakout (V8) ka backtest abhi nahi chala: GitHub Actions > research > Run workflow.")

with tAsk:
    import ask as ASK, askstats as ASS
    st.subheader("💬 Kuch bhi poochho (bina API key, tool ke apne data se)")
    st.caption("Market, trade, wallet, points ya trading ke sawaal likho. Jawab tool ke live data aur lambi history se aata hai. Jahan edge nahi hota wahan seedha '50-50' likhta hai.")
    D_ = S.get("daily")
    st.markdown("##### 📆 Kal aur pichhle dinon mein BTC kitna gaya (stop-loss ka andaaza lene ke liye)")
    if D_ and D_.get("rows"):
        full_ = [r for r in D_["rows"] if not r["today"]]; tod_ = [r for r in D_["rows"] if r["today"]]
        if full_:
            y_ = full_[-1]; c1, c2, c3, c4 = st.columns(4)
            c1.metric("Kal upar tak", f"+{y_['up']:,.0f} pts", f"+{y_['up_pct']:.2f}%"); c2.metric("Kal neeche tak", f"-{y_['dn']:,.0f} pts", f"-{y_['dn_pct']:.2f}%", delta_color="inverse")
            c3.metric("Kal ka poora range", f"{y_['rng']:,.0f} pts", f"{y_['rng_pct']:.2f}%", delta_color="off"); c4.metric("Kal ka close (open se)", f"{y_['chg']:+,.0f} pts", f"{y_['chg_pct']:+.2f}%")
        if tod_: t_ = tod_[-1]; st.caption(f"Aaj abhi tak: upar +{t_['up']:,.0f} pts ({t_['up_pct']:.2f}%), neeche -{t_['dn']:,.0f} pts ({t_['dn_pct']:.2f}%), range {t_['rng']:,.0f} pts")
        a_ = D_.get("avg7")
        if a_: st.info(f"Pichhle {a_['n']} din ka average: upar +{a_['up']:,.0f} pts, neeche -{a_['dn']:,.0f} pts, range {a_['rng']:,.0f} pts ({a_['rng_pct']:.1f}%). Sabse chhota din {a_['min_rng']:,.0f}, sabse bada {a_['max_rng']:,.0f} pts. Stop-loss is range se bahut chhota rakhoge to normal halchal mein kat sakta hai; stop apne setup ke swing/ATR se tay karo.")
        df_ = pd.DataFrame([dict(Din=r["day"] + (" (aaj)" if r["today"] else ""), **{"Upar pts": r["up"], "Upar %": r["up_pct"], "Neeche pts": r["dn"], "Neeche %": r["dn_pct"], "Range pts": r["rng"], "Range %": r["rng_pct"], "Close-Open pts": r["chg"], "Close-Open %": r["chg_pct"]}) for r in D_["rows"][::-1]])
        st.dataframe(df_, hide_index=True, use_container_width=True)
        st.caption("Din = IST ke hisaab se raat 12 se raat 12. 'Upar' = us din ke open se sabse upar tak, 'Neeche' = open se sabse neeche tak.")
    else: st.info("Daily move data agle scan ke baad aa jayega.")
    st.markdown("##### 🗂 Poori daily history (hamesha ke liye saved)")
    ARC_ = load("daily_history.json"); import dailylog as DLG
    if ARC_ and ARC_.get("days"):
        rows_ = [ARC_["days"][k] for k in sorted(ARC_["days"])]; fin_ = [r for r in rows_ if r.get("final")]
        st.caption(f"{len(fin_)} poore din saved (sabse purana {fin_[0]['day'] if fin_ else '-'}). Poora din khatam hote hi row freeze ho jati hai, kabhi delete ya badalti nahi.")
        st.text(DLG.text_stats(ARC_))
        T_ = pd.DataFrame(rows_[::-1]); T_["weekday"] = T_["weekday"].map(lambda i: DLG.WD[int(i)])
        show_ = T_[["day", "weekday", "open", "high", "low", "close", "up", "dn", "rng", "rng_pct", "chg", "chg_pct", "direction", "high_hr_ist", "low_hr_ist", "rng_asia", "rng_europe", "rng_us", "rng_late", "paper_trades", "paper_pnl_inr", "final"]]
        st.dataframe(show_, hide_index=True, use_container_width=True, height=320)
        fn_ = [r for r in rows_ if r.get("final")][-120:]
        if fn_: st.caption("Roz ka range (points), pichhle 120 din"); st.bar_chart(pd.DataFrame({"range pts": [r["rng"] for r in fn_]}, index=[r["day"] for r in fn_]))
        csv_ = load("daily_history.csv", "text")
        if csv_: st.download_button("⬇️ Poori daily history CSV download", csv_, "daily_history.csv", "text/csv")
    else: st.info("Daily archive pehle scan ke baad bharna shuru hoga (pehli baar ek saal ka data khud laata hai).")
    st.markdown("##### ❓ Sawaal")
    QS_ = [("⏱ 5 min", "5 min me kya hoga?"), ("⏱ 1 ghanta", "1 ghante me upar ya neeche?"), ("⏱ 4 ghante", "4 ghante me upar ya neeche?"), ("📊 Market kaisa", "market kaisa hai?"), ("🎯 Trade lu?", "abhi trade lena chahiye?"), ("📆 Kal ka move", "kal kitna move hua?"), ("🧭 Levels", "support resistance kahan hai?")]
    cols_ = st.columns(len(QS_)); picked_ = None
    for col_, (lab_, q_) in zip(cols_, QS_):
        if col_.button(lab_, use_container_width=True, key="askq_" + lab_): picked_ = q_
    with st.form("askform", clear_on_submit=False):
        typed_ = st.text_input("Apna sawaal likho", placeholder="jaise: kya 90000 tak jayega aaj? / 1 ghante me upar ya neeche? / RSI kya hai?")
        go_ = st.form_submit_button("Poochho")
    q_final = picked_ or (typed_ if go_ else "")
    if q_final:
        ans_ = ASK.answer(q_final, S, CFG, load("ask_stats.json"), log=False, arc=load("daily_history.json"))
        st.markdown("**Sawaal:** " + q_final.replace("$", "\\$")); st.markdown(ans_.replace("$", "\\$").replace("*", "\\*").replace("_", "\\_").replace("\n", "  \n"))
    with st.expander("Kya kya poochh sakte ho"): st.text(ASK.EXAMPLES)

with tG:
    with st.expander("🧭 How to read this tool and take a decision (start here)", expanded=True):
        st.markdown("""
**Daily routine (2 minutes)**
1. **Home**: price, regime, and any open position. An open position shows a status (🟢 hold, 🟡 protect profit, 🟠 book profit, 🔴 reversal risk) and the reasons.
2. **🧭 Decision Desk**, questions 1 to 3: what is the market doing, is there an opportunity, long or short or NO TRADE. If the answer is **NO TRADE, stop here**. Doing nothing is a valid decision.
3. If there is a setup, read questions 4 to 16: is it early or already late, what supports it, what contradicts it, entry zone, stop, targets, risk/reward, and how often similar moves happened.

**Take the trade only if most of these are true**
- Setup is **early** (not "late: avoid chasing") and price is inside or near the early entry zone.
- Evidence **for** clearly outweighs evidence **against**, and false-signal risk is not High.
- Risk/reward to Target 1 is **1.5 or better**, and the stop is at a level that really means the idea failed.
- Timeframes mostly agree (Multi-timeframe table), and no strong **reversal evidence** against you.
- You can afford the loss: the Wallet tab's size calculator shows quantity for 1% risk. Never risk more than you planned.

**After entry (questions 17 to 27)**: follow the status, not your feelings. Protect profit when the status turns yellow, consider booking when it turns orange, think about exiting when it turns red. Never move the stop **away** from price.

**Review weekly (Trade History tab)**: win rate, average R, drawdown. With fewer than 30 closed trades it is noise: do not change rules because of a few trades.

**Honest limits**: backtests show **no proven edge** yet. Treat everything as practice with virtual money until months of paper results say otherwise. These are probabilities, not predictions.
""")
    st.markdown("""
**How the wallet works (every ~5 minutes)**
1. The scanner reads the market and checks two strategies: *Trend Pullback* (backtested, weak edge) and *Early Signal* (experimental).
2. If a signal appears, a **virtual** order opens: quantity from risking a % of equity, margin locked, fee charged. Telegram tells you why (Kyun liya).
3. Each scan checks stops, targets and expiry. Early Signal books half at T1 and moves the stop to entry.
4. When a trade closes, margin returns with profit/loss, fees are charged, and you get a short lesson and a 👍/👎 rating button.
5. The advisor panel shows a live status (hold, protect profit, book profit, reversal risk). It is advice only; the paper rule never changes.

**Telegram commands:** `/ping` `/status` `/wallet` `/ledger` `/trades` `/analysis` `/lessons` `/approve N` `/revert N` `/config` `/set name value` `/notify name on|off` `/note ID text` `/myexit ID price` `/weekly` `/demo` `/resetwallet confirm`

**Words:** *Regime* market mode. *Stage* how far a setup developed. *Score* evidence points (0-100). *R* one unit of risk. *Funding / OI* crowd positioning.

**Honest status:** the machine (scanner, alerts, wallet, advisor, dashboard) works. A reliably profitable signal is **not proven**. Treat everything as practice.
""")
    with st.expander("📐 Design document: architecture, data sources, methodology (spec section 38, A to V)"): st.markdown(load("DESIGN.md", "text") or "DESIGN.md not found in the repo yet.")
