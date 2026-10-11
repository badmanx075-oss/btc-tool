"""Direction-agnostic history of price moves by volatility regime -> expected-move zones and point-move odds (spec 12, 13, 25).
For every past hour: how far did price travel UP and DOWN within the next 24h / 72h, given the volatility bucket at that time."""
import os, sys, json, requests, numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import engine as E, backtest_v5 as X
GRID = [round(0.25 * i, 2) for i in range(1, 81)]          # 0.25% .. 20%

def build(df):
    h, l, c = df.h.values, df.l.values, df.c.values; N = len(df); pct = (E.atr_series(df) / df.c * 100).values; ok = ~np.isnan(pct)
    e1, e2 = np.percentile(pct[ok], [33.3, 66.7]); b = (pct > e1).astype(int) + (pct > e2).astype(int)
    out = dict(grid=GRID, edges=[round(float(e1), 4), round(float(e2), 4)], rows=N, H={}, Q={}, n_bucket={})
    for H in (24, 72):
        up = (sliding_window_view(h, H)[1:].max(axis=1) - c[:N - H]) / c[:N - H] * 100; dn = (c[:N - H] - sliding_window_view(l, H)[1:].min(axis=1)) / c[:N - H] * 100
        out["H"][str(H)], out["Q"][str(H)] = {}, {}
        for k in range(3):
            m = (b[:N - H] == k) & ok[:N - H]; out["n_bucket"][str(k)] = int(m.sum())
            out["H"][str(H)][str(k)] = {s: [round(float((x[m] >= g).mean()), 4) for g in GRID] for s, x in (("up", up), ("dn", dn))}
            out["Q"][str(H)][str(k)] = {s: [round(float(q), 3) for q in np.percentile(x[m], [50, 75, 90, 95])] for s, x in (("up", up), ("dn", dn))}
    return out

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    res = build(X.hist1h(days)); json.dump(res, open("move_stats.json", "w")); q = res["Q"]["24"]
    print("rows", res["rows"], "| 24h median up/down % by volatility bucket:", {k: (v["up"][0], v["dn"][0]) for k, v in q.items()})
    if os.environ.get("TG_TOKEN"):
        msg = "Move statistics built ({} hourly rows).\n24h typical (median) move by volatility: ".format(res["rows"]) + " | ".join(f"{n}: up {q[k]['up'][0]}% / down {q[k]['dn'][0]}%" for k, n in (("0", "calm"), ("1", "normal"), ("2", "wild")))
        requests.post(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage", json=dict(chat_id=os.environ["TG_CHAT_ID"], text=msg), timeout=20)
