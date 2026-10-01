import json, os, streamlit as st, pandas as pd
st.set_page_config(page_title="BTC Perp Analyzer", layout="wide")
S = json.load(open("state.json")) if os.path.exists("state.json") else {"trades": {}}
m = S.get("market")
st.title("BTC Perpetual – Early Opportunity Tool")
if m:
    c = st.columns(4); c[0].metric("Price", f"${m['price']:,.0f}"); c[1].metric("Regime", m["regime"])
    c[2].metric("Signal", m["signal"]); c[3].metric("Score", f"{m['score']}/100")
    st.caption(f"Funding {m['funding']*100:.4f}% | OI ${m['oi']:,.0f} | updated {m['ts']}")
    a, b = st.columns(2); a.write("**Evidence for**"); a.write(m["pro"] or "-"); b.write("**Evidence against**"); b.write(m["con"] or "-")
else: st.info("No scan yet. Run the GitHub Action once.")
T = S["trades"]
sel = st.query_params.get("trade")
st.subheader("Trades")
if T:
    df = pd.DataFrame(T.values())[["id", "signal", "regime", "score", "entry", "sl", "t1", "t2", "t3", "status", "outcome", "mfe", "mae"]]
    st.dataframe(df, use_container_width=True)
    tid = st.selectbox("Review trade", list(T), index=list(T).index(sel) if sel in T else len(T) - 1)
    t = T[tid]; st.json({k: t[k] for k in ("side", "entry", "zone", "sl0", "sl", "t1", "t2", "t3", "ext", "confirm", "move_class", "risk", "pro", "con", "user")})
    st.write("**Timeline**"); st.table(pd.DataFrame(t["events"])[["ts", "type", "price", "note"]])
    sysw = [x for x in T.values() if x["outcome"] and x["outcome"] != "SL HIT" and x["outcome"] != "EXPIRED"]
    st.write(f"System: {len(T)} signals, {len(sysw)} reached ≥T1. User-marked: " + str({r: sum(x['user'].get('result') == r for x in T.values()) for r in ('WIN', 'LOSS')}))
else: st.write("No trades yet.")

if os.path.exists("backtest_results.json"):
    st.subheader("Backtest (historical, not a guarantee)"); st.json(json.load(open("backtest_results.json")))

if os.path.exists("backtest_v3_results.json"):
    st.subheader("Backtest V3 (out-of-sample test)"); st.json(json.load(open("backtest_v3_results.json")))

P = S.get("paper")
if P:
    st.subheader("Paper trading wallet (virtual money, no real orders): trend_pullback, edge unproven")
    bal, start = P.get("balance", 20000), P.get("start", 20000)
    c = st.columns(4); c[0].metric("Wallet", f"₹{bal:,.0f}", f"{(bal / start - 1) * 100:+.1f}%"); c[1].metric("Start", f"₹{start:,.0f}")
    c[2].metric("Trades closed", len(P["closed"])); c[3].metric("Max drawdown", f"{P.get('max_dd_pct', 0)}%")
    st.markdown("**Open position**"); o, lp = P.get("open"), S.get("last_price")
    if o:
        q, k, fxr = o.get("qty_btc", 0), o["side"], o.get("fx", 88); u = ((lp - o["entry"]) * k * q) if lp else 0
        st.table(pd.DataFrame([{"Order ID": o["id"], "Action": "BUY (LONG)" if k == 1 else "SELL (SHORT)", "Qty (BTC)": q, "Entry rate": round(o["entry"]),
                                "Current rate": round(lp) if lp else None, "Stop-loss": round(o["sl"]), "Target": round(o["tp"]),
                                "Unrealized $": round(u, 2), "Unrealized ₹": round(u * fxr)}]))
    else: st.write("No open position")
    if P["closed"]:
        d = pd.DataFrame(P["closed"]); d["wallet_after"] = start + d["pnl_inr"].fillna(0).cumsum()
        st.markdown("**Wallet curve**"); st.line_chart(d.set_index("closed")["wallet_after"])
        st.markdown("**Trade book**")
        st.dataframe(d.reindex(columns=["closed", "id", "qty_btc", "entry", "exit", "outcome", "gross_usd", "fees_usd", "pnl_inr", "R"]), use_container_width=True)
    if P.get("orders"):
        st.markdown("**Order log (newest first)**"); st.dataframe(pd.DataFrame(P["orders"]).iloc[::-1], use_container_width=True)
