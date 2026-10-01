import json, os, io, datetime as dt, requests, pandas as pd, streamlit as st

st.set_page_config(page_title="BTC Tool", page_icon="📈", layout="wide")
RAW = "https://raw.githubusercontent.com/badmanx075-oss/btc-tool/main/"   # live data written by the 5-minute scanner

@st.cache_data(ttl=60)
def load(name, kind="json"):
    txt = None
    if not os.environ.get("DASH_LOCAL"):
        try: r = requests.get(RAW + name, timeout=10); r.raise_for_status(); txt = r.text
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

head, btn = st.columns([6, 1]); head.title("📈 BTC Perpetual Tool")
if btn.button("🔄 Refresh"): st.cache_data.clear(); st.rerun()
if M:
    age = (now - dt.datetime.fromisoformat(M["ts"])).total_seconds() / 60
    head.caption(f"Last scan {age:.0f} min ago | BTC ${M['price']:,.0f} | Funding {M['funding'] * 100:.4f}% | OI ${M['oi'] / 1e9:.2f}B")
    if age > 30: st.warning("Scanner looks delayed (more than 30 min). Check GitHub Actions.")
st.caption("⚠️ Informational and statistical only. Virtual money. Backtests show NO proven edge yet.")

t1, t2, t3, t4, t5 = st.tabs(["🏠 Home", "💰 Wallet", "📡 Old signals (experimental)", "📊 Backtests", "📘 Guide"])

with t1:
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
        title, why = pos_status(ur, 120 - hrs); st.markdown(f"### {title}"); st.caption(why)
        st.progress(float(min(max((lp - o["sl"]) / (o["tp"] - o["sl"]), 0), 1)), text=f"Stop ${o['sl']:,.0f}  ←  now ${lp:,.0f}  →  Target ${o['tp']:,.0f}")
        st.table(pd.DataFrame([{"Order": o["id"], "Action": "BUY (LONG)" if k == 1 else "SELL (SHORT)", "Qty BTC": q, "Entry": round(o["entry"]), "Now": round(lp),
                                "Stop": round(o["sl"]), "Target": round(o["tp"]), "Open P/L": inr(usd * o.get("fx", 88)), "Time left": f"{max(120 - hrs, 0):.0f} h"}]))
    else: st.write("No open position.")
    st.subheader("Market now")
    if M:
        a, b = st.columns(2); a.markdown(f"**Signal:** {M['signal']} (score {M['score']}/100)"); a.markdown("**For:** " + (", ".join(M["pro"]) or "-")); b.markdown("**Against:** " + (", ".join(M["con"]) or "-"))
        st.caption(stage(M["score"], bool(o)))
    lg = load("market_log.csv", "csv")
    if lg is not None and len(lg) > 5:
        lg = lg.tail(288).set_index("ts"); x, y = st.columns(2); x.caption("BTC price (last ~24h)"); x.line_chart(lg["price"]); y.caption("Open interest USD (last ~24h)"); y.line_chart(lg["oi_usd"])

with t2:
    c = st.columns(4); c[0].metric("Wallet", inr(bal), f"{(bal / start - 1) * 100:+.1f}%"); c[1].metric("Start", inr(start)); c[2].metric("Trades closed", len(P.get("closed", []))); c[3].metric("Max drawdown", f"{P.get('max_dd_pct', 0)}%")
    st.caption("Rules: strategy trend_pullback | risk 1% of wallet per trade | stop 3×ATR(1H) | target 4R | exit after 5 days | fees 0.10% | no real orders.")
    cl = P.get("closed", [])
    if cl:
        d = pd.DataFrame(cl); d["wallet"] = start + d["pnl_inr"].fillna(0).cumsum(); st.line_chart(d.set_index("closed")["wallet"])
        st.subheader("Trade book"); st.dataframe(d.reindex(columns=["closed", "id", "qty_btc", "entry", "exit", "outcome", "gross_usd", "fees_usd", "pnl_inr", "R"]).rename(
            columns={"closed": "Closed", "id": "Order", "qty_btc": "Qty BTC", "entry": "Entry", "exit": "Exit", "outcome": "Result", "gross_usd": "Gross $", "fees_usd": "Fees $", "pnl_inr": "Net ₹"}))
        w = int((d.pnl_inr > 0).sum()); st.caption(f"Wins {w} | Losses {len(d) - w} | Total {d.R.sum():+.2f}R")
    else: st.info("No closed trades yet. A signal needs several conditions together, so 1-2 trades per week is normal.")
    if P.get("orders"): st.subheader("Order log (newest first)"); st.dataframe(pd.DataFrame(P["orders"]).iloc[::-1])

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

**Honest status**: the machine (scanner, alerts, wallet, dashboard) works. A reliably profitable signal is **not proven**. Treat everything as practice.
""")
