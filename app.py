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
