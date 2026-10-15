"""Order flow by PRICE: where is aggressive buying / selling happening?
Reads recent public trades (taker side = the aggressor), keeps a rolling 36h profile in 30-minute slices x $50 price buckets
(orderflow_profile.json), and classifies the market now as AGGRESSIVE BUYING / SELLING, mild, or NORMAL.
'Big' = single taker trade >= 2 BTC. Coverage is best-effort: if the bot could not read every trade between two scans, coverage < 100% is shown."""
import os, json, time, datetime as dt
import engine as E

FILE = "orderflow_profile.json"; CT = 0.01; BUCKET = 50; SLICE = 1800; KEEP_H = 36; BIG_BTC = 2.0


def load(path=FILE):
    try: return json.load(open(path))
    except Exception: return dict(last_id=None, slices={}, coverage=[], updated=None)


def save(P, path=FILE):
    tmp = path + ".tmp"; json.dump(P, open(tmp, "w"), separators=(",", ":")); os.replace(tmp, path)


def fetch_new(last_id, max_pages=25):
    t = E._get("market/trades", instId=E.INST, limit=500); trades = list(t); full = True
    if last_id and t and int(t[-1]["tradeId"]) > int(last_id):           # more trades happened than one page holds: page back to the last one we saw
        after = t[-1]["tradeId"]; full = False
        try:
            for _ in range(max_pages):
                d = E._get("market/history-trades", instId=E.INST, type=1, after=after, limit=100)
                if not d: break
                trades += d; after = d[-1]["tradeId"]
                if int(after) <= int(last_id): full = True; break
                time.sleep(0.08)
        except Exception as e: print("orderflow paging stopped:", type(e).__name__)
    seen, out = set(), []
    for x in trades:
        i = int(x["tradeId"])
        if i in seen or (last_id and i <= int(last_id)): continue
        seen.add(i); out.append(x)
    return out, full


def add_trades(P, trades):
    S_ = P.setdefault("slices", {}); mx = int(P["last_id"]) if P.get("last_id") else 0
    for x in trades:
        ts = int(x["ts"]) // 1000; key = str(ts // SLICE * SLICE); px = float(x["px"]); b = str(int(px // BUCKET * BUCKET)); q = float(x["sz"]) * CT; big = q >= BIG_BTC
        cell = S_.setdefault(key, {}).setdefault(b, [0.0, 0.0, 0.0, 0.0]); k = 0 if x["side"] == "buy" else 1
        cell[k] += q; cell[k + 2] += q if big else 0.0; mx = max(mx, int(x["tradeId"]))
    P["last_id"] = str(mx) if mx else P.get("last_id")


def prune(P, now):
    cut = now.timestamp() - KEEP_H * 3600
    for k in [k for k in P["slices"] if int(k) < cut]: del P["slices"][k]
    for v in P["slices"].values():
        for b, c in v.items(): v[b] = [round(x, 3) for x in c]


def window(P, now, minutes):
    """Aggregate buckets over the last `minutes`: {bucket_price: [buy, sell, big_buy, big_sell]}."""
    cut = now.timestamp() - minutes * 60; agg = {}
    for k, v in P["slices"].items():
        if int(k) + SLICE < cut: continue
        for b, c in v.items():
            a = agg.setdefault(int(b), [0.0] * 4)
            for i in range(4): a[i] += c[i]
    return agg


def _tot(agg):
    t = [sum(c[i] for c in agg.values()) for i in range(4)]; vol = t[0] + t[1]
    return dict(buy=round(t[0], 1), sell=round(t[1], 1), big_buy=round(t[2], 1), big_sell=round(t[3], 1), vol=round(vol, 1), delta=round(t[0] - t[1], 1), ratio=round((t[0] - t[1]) / vol, 3) if vol else 0.0,
                big_share=round((t[2] + t[3]) / vol, 3) if vol else 0.0)


def state_of(w, base_per_min, minutes):
    if w["vol"] <= 0: return "NO DATA"
    inten = (w["vol"] / minutes) / base_per_min if base_per_min else 1.0; r = w["ratio"]
    if r >= 0.25 and (w["big_buy"] >= 1.5 * max(w["big_sell"], 0.1) or inten >= 1.5): return "AGGRESSIVE BUYING"
    if r <= -0.25 and (w["big_sell"] >= 1.5 * max(w["big_buy"], 0.1) or inten >= 1.5): return "AGGRESSIVE SELLING"
    if r >= 0.1: return "MILD BUYING"
    if r <= -0.1: return "MILD SELLING"
    return "NORMAL / BALANCED"


def analyze(P, now, px):
    w60, w240, w1440 = window(P, now, 60), window(P, now, 240), window(P, now, 1440); t60, t240, t1440 = _tot(w60), _tot(w240), _tot(w1440)
    span = max(min((now.timestamp() - min((int(k) for k in P["slices"]), default=now.timestamp())) / 60, 1440), 30); base = t1440["vol"] / span if t1440["vol"] else 0
    zones = []
    for b, c in w240.items():
        v = c[0] + c[1]
        if v <= 0: continue
        zones.append(dict(lo=b, hi=b + BUCKET, buy=round(c[0], 1), sell=round(c[1], 1), vol=round(v, 1), ratio=round((c[0] - c[1]) / v, 2), big_share=round((c[2] + c[3]) / v, 2)))
    mv = max((z["vol"] for z in zones), default=0)
    sig = [z for z in zones if z["vol"] >= 0.15 * mv]
    buys = sorted([z for z in sig if z["ratio"] >= 0.2], key=lambda z: -(z["buy"] - z["sell"]))[:3]; sells = sorted([z for z in sig if z["ratio"] <= -0.2], key=lambda z: -(z["sell"] - z["buy"]))[:3]
    poc = max(zones, key=lambda z: z["vol"], default=None)
    cov = P.get("coverage") or []
    return dict(ts=now.isoformat(timespec="seconds"), px=round(px, 1), now=dict(state=state_of(t60, base, 60), **t60), h4=dict(state=state_of(t240, base, 240), **t240), h24=dict(state=state_of(t1440, base, 1440), **t1440),
                buy_zones=buys, sell_zones=sells, poc=poc, coverage_pct=round(100 * sum(cov) / len(cov)) if cov else None, history_h=round(span / 60, 1))


def profile_rows(P, now, minutes=240):
    return [[b, round(c[0], 2), round(c[1], 2)] for b, c in sorted(window(P, now, minutes).items())]


def update(now, px, path=FILE):
    """Fetch new trades, update the saved profile, return the analysis. Never raises."""
    P = load(path)
    try:
        tr, full = fetch_new(P.get("last_id")); add_trades(P, tr); P.setdefault("coverage", []).append(1 if full else 0); del P["coverage"][:-50]; P["updated"] = now.isoformat(timespec="seconds")
        prune(P, now); save(P, path)
    except Exception as e: print("orderflow error", type(e).__name__, e)
    try: return analyze(P, now, px)
    except Exception as e: print("orderflow analyze error", e); return None


def text(A):
    if not A or not A.get("now"): return "Order-flow data abhi jama ho raha hai (pehle kuch scan chalne do)."
    n, h = A["now"], A["h4"]; ic = {"AGGRESSIVE BUYING": "🟢🔥", "AGGRESSIVE SELLING": "🔴🔥", "MILD BUYING": "🟢", "MILD SELLING": "🔴"}
    L = [f"🌊 ORDER FLOW (BTC ${A['px']:,.0f})", f"Abhi (60 min): {ic.get(n['state'], '⚪')} {n['state']} | buy {n['buy']:,.0f} BTC vs sell {n['sell']:,.0f} BTC (delta {n['ratio'] * 100:+.0f}%, bade orders {n['big_share'] * 100:.0f}%)",
         f"4 ghante: {h['state']} (delta {h['ratio'] * 100:+.0f}%) | 24 ghante: {A['h24']['state']} (delta {A['h24']['ratio'] * 100:+.0f}%)"]
    if A["buy_zones"]: L.append("🟢 Buying ka dabaav (🔥 = aggressive): " + "; ".join(f"{'🔥' if z['ratio'] >= 0.4 else ''}${z['lo']:,.0f}-{z['hi']:,.0f} ({z['vol']:,.0f} BTC, delta {z['ratio'] * 100:+.0f}%)" for z in A["buy_zones"]))
    if A["sell_zones"]: L.append("🔴 Selling ka dabaav (🔥 = aggressive): " + "; ".join(f"{'🔥' if z['ratio'] <= -0.4 else ''}${z['lo']:,.0f}-{z['hi']:,.0f} ({z['vol']:,.0f} BTC, delta {z['ratio'] * 100:+.0f}%)" for z in A["sell_zones"]))
    if A.get("poc"): L.append(f"📍 Sabse zyada trading: ${A['poc']['lo']:,.0f}-{A['poc']['hi']:,.0f} ({A['poc']['vol']:,.0f} BTC)")
    L.append(f"Data: {A['history_h']} ghante jama" + (f", coverage {A['coverage_pct']}%" if A.get('coverage_pct') is not None else "") + ". Aggressive = taker (market order) zyada, bade orders (2+ BTC) ya volume normal se 1.5x.")
    return "\n".join(L)
