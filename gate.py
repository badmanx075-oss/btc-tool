"""Auto-gate: every (strategy, side) bucket is judged by its OWN recent live results, so the bot adapts to the market without guessing the market's nature.
CLOSE  : last `window` live trades of the bucket (only those after the last re-open) have mean R <= max_mean_R AND z <= max_z, with at least `min_trades` of them.
         From then on new signals of that bucket are NOT traded; they are simulated as shadows (same entry/stop/target) so the data keeps coming.
RE-OPEN: the last `reopen_shadows` finished shadows of the bucket have mean R >= reopen_mean_R. The bucket then restarts with a clean slate (probation).
Honest limits: shadows use the plain stop/target rule (no smart exit), so they are a rough proxy; thresholds are deliberately strict to avoid flip-flopping on noise. Nothing here deletes data."""
import math, statistics as st, datetime as dt

SIDE = {1: "LONG", -1: "SHORT"}


def bucket(name, k): return f"{name}:{SIDE.get(k, k)}"


def closed(P, C, name, k):
    g = (C.get("auto_gate") or {})
    return bool(g.get("enabled")) and (P.get("gate", {}).get(bucket(name, k), {}).get("open", True) is False)


def _stats(x):
    n = len(x); m = sum(x) / n if n else 0.0
    se = st.stdev(x) / math.sqrt(n) if n > 1 else 0.0
    return n, m, (m / se if se > 1e-9 else 0.0)


def update(P, C, now, send):
    cfg = C.get("auto_gate") or {}
    if not cfg.get("enabled"): return
    G = P.setdefault("gate", {}); iso = now.replace(microsecond=0).isoformat()
    names = {t.get("strategy") for t in P.get("closed", [])} | {s.get("strategy") for s in P.get("shadow", []) if s.get("gate")}
    for name in sorted(n for n in names if n):
        for k in (1, -1):
            b = bucket(name, k); g = G.setdefault(b, dict(open=True, since="", recent=[], history=[]))
            # shadows of this bucket that finished (only exist while it was closed)
            seen = {r[0] for r in g["recent"]}
            for s in P.get("shadow", []):
                if s.get("gate") == b and "R" in s and s.get("id") not in seen: g["recent"].append([s["id"], float(s["R"])]); seen.add(s["id"])
            g["recent"] = g["recent"][-30:]
            if g["open"]:
                live = [t["R"] for t in P.get("closed", []) if t.get("strategy") == name and t.get("side") == k and t.get("R") is not None and (t.get("closed") or "") > g["since"]]
                live = live[-int(cfg.get("window", 20)):]; n, m, z = _stats(live)
                if n >= int(cfg.get("min_trades", 20)) and m <= cfg.get("max_mean_R", -0.2) and z <= cfg.get("max_z", -1.5):
                    g.update(open=False, closed_at=iso, recent=[], why=f"last {n} trades: avg {m:+.2f}R (z {z:+.1f})"); g["history"].append(f"{iso} CLOSED {g['why']}")
                    send(f"🚦 AUTO-GATE: {name} {SIDE[k]} BAND\nPichhle {n} trades: avg {m:+.2f}R (z {z:+.1f}), ye bucket lagataar haar raha hai.\nAb is bucket ke naye signals trade nahi honge; shadow me chalte rahenge. Shadow ke last {cfg.get('reopen_shadows', 10)} result avg ≥ {cfg.get('reopen_mean_R', 0.15):+.2f}R hone par khud chalu ho jayega.\nKhud chalu/band karne ke liye config.json me auto_gate.enabled false.", cat="learning")
            else:
                last = [r[1] for r in g["recent"]][-int(cfg.get("reopen_shadows", 10)):]; n, m, z = _stats(last)
                if n >= int(cfg.get("reopen_shadows", 10)) and m >= cfg.get("reopen_mean_R", 0.15):
                    g.update(open=True, since=iso, recent=[], why=f"shadow {n} signals: avg {m:+.2f}R"); g["history"].append(f"{iso} REOPENED {g['why']}")
                    send(f"🚦 AUTO-GATE: {name} {SIDE[k]} dobara CHALU\nBand ke dauran {n} shadow signals ka avg {m:+.2f}R raha. Ab se naye trades lagenge (probation: agle {cfg.get('min_trades', 20)} trades ke baad phir se judge hoga).", cat="learning")
            g["history"] = g["history"][-20:]
