"""Learning layer. Records context for every paper trade, writes a post-mortem, mines patterns across many trades,
and proposes filters. It never rewrites rules after a single loss (overfitting). A filter only runs after the user approves it (/approve N),
and it is switched off automatically if the trades it blocks (shadow trades) do as well as the trades it allows."""
import numpy as np
MIN_TOTAL, MIN_BUCKET, Z_PROPOSE = 40, 15, 2.5

def postmortem(t):
    m, h, R = t.get("mfe_R", 0), t.get("hold_h", 0), t.get("R", 0)
    if t["outcome"] == "TARGET": return "Win: the plan worked as designed."
    if t["outcome"] == "STOP-LOSS":
        if m >= 2: return f"Loss after reaching +{m:.1f}R first: direction was right but it reversed. A closer target or trailing stop might have kept profit (hypothesis, needs testing)."
        if h <= 6: return f"Fast loss ({h:.0f}h, best +{m:.1f}R): entry timing was poor or a volatility spike hit the stop."
        return f"Slow loss ({h:.0f}h, best +{m:.1f}R): the trend faded and price never moved in favour."
    return f"Expired after 5 days at {R:+.1f}R: no decisive move."

def defs(T):
    out = []
    for key, name in (("er4", "4H trend strength"), ("atr_pct", "volatility (ATR%)"), ("depth", "pullback depth")):
        a, b = np.percentile([t["ctx"][key] for t in T], [33.3, 66.7]); out.append((name, key, [("low", -1e9, a), ("mid", a, b), ("high", b, 1e9)]))
    out += [("session (UTC)", "hour", [("00-08", 0, 8), ("08-16", 8, 16), ("16-24", 16, 24)]), ("day type", "wd", [("weekday", 0, 5), ("weekend", 5, 7)]),
            ("funding", "funding", [("negative/zero", -1e9, 1e-12), ("positive", 1e-12, 1e9)]), ("direction", "side_n", [("SHORT", -2, 0), ("LONG", 0, 2)])]
    return out

def analyze(closed):
    T = [t for t in closed if t.get("ctx") and "R" in t]; out = dict(n=len(T), patterns=[], note="")
    if len(T) < MIN_TOTAL:
        out["note"] = f"Need {MIN_TOTAL} closed trades with context before patterns are reported (have {len(T)}). Earlier 'patterns' are mostly luck."; return out
    R = np.array([t["R"] for t in T])
    for name, key, bins in defs(T):
        for lab, lo, hi in bins:
            idx = [i for i, t in enumerate(T) if lo <= t["ctx"][key] < hi]; rest = np.delete(R, idx)
            if len(idx) < MIN_BUCKET or len(rest) < 5: continue
            r = R[idx]; se = np.sqrt(r.var(ddof=1) / len(r) + rest.var(ddof=1) / len(rest)); z = (r.mean() - rest.mean()) / se if se > 0 else 0.0
            out["patterns"].append(dict(feature=name, bucket=lab, key=key, lo=float(lo), hi=float(hi), n=len(idx), mean_R=round(float(r.mean()), 2), rest_R=round(float(rest.mean()), 2), z=round(float(z), 2)))
    out["patterns"].sort(key=lambda p: -abs(p["z"])); out["note"] = "z beyond +-2.5 is only a hint: about 20 buckets are tested, so a few false alarms are expected."
    return out

def update(P):
    P["lessons"] = L = analyze(P["closed"]); have = {f["text"] for f in P["filters"]} | {p["text"] for p in P["proposals"]}; nid = max([p["id"] for p in P["proposals"]] + [f["id"] for f in P["filters"]] + [0])
    for p in L["patterns"]:
        text = f"Skip trades when {p['feature']} is {p['bucket']}"
        if p["z"] <= -Z_PROPOSE and p["mean_R"] < 0 and text not in have and len(P["proposals"]) < 3:
            nid += 1; P["proposals"].append(dict(id=nid, text=text, key=p["key"], lo=p["lo"], hi=p["hi"], n=p["n"], mean_R=p["mean_R"], rest_R=p["rest_R"], z=p["z"]))

def blocked_by(P, ctx):
    for f in P["filters"]:
        v = ctx.get(f["key"])
        if f.get("active", True) and v is not None and f["lo"] <= v < f["hi"]: return f

def approve(P, arg):
    p = next((x for x in P["proposals"] if str(x["id"]) == arg), None)
    if not p: return "No such proposal. Send /lessons to see ideas."
    P["proposals"].remove(p); P["filters"].append(dict(id=p["id"], text=p["text"], key=p["key"], lo=p["lo"], hi=p["hi"], active=True))
    return f"Filter #{p['id']} approved: {p['text']}.\nMatching signals will be skipped but tracked as shadow trades. It switches off automatically if blocked trades do as well as allowed ones."

def revert(P, arg):
    f = next((x for x in P["filters"] if str(x["id"]) == arg), None)
    if not f: return "No such filter."
    f["active"] = False; return f"Filter #{f['id']} switched off."

def check_filters(P):
    msgs = []; taken = [t["R"] for t in P["closed"] if "R" in t]
    for f in P["filters"]:
        b = [s["R"] for s in P["shadow"] if s.get("filter") == f["text"] and "R" in s]
        if f.get("active", True) and len(b) >= 10 and taken and np.mean(b) >= np.mean(taken):
            f["active"] = False; msgs.append(f"🧠 Filter #{f['id']} switched OFF: the {len(b)} trades it blocked averaged {np.mean(b):+.2f}R vs {np.mean(taken):+.2f}R taken. It was not helping.")
    return msgs

def lessons_text(P):
    L = P.get("lessons") or {}; cl = [t for t in P.get("closed", []) if t.get("lesson")][-3:]; lines = [f"🧠 Learning: {L.get('n', 0)} trades with context"]
    lines += [f"• {t['id']}: {t['lesson']}" for t in cl] or ["No closed trades with lessons yet."]
    if L.get("note"): lines.append(L["note"])
    for p in P.get("proposals", []): lines.append(f"💡 #{p['id']} {p['text']} (n={p['n']}, {p['mean_R']:+.2f}R vs {p['rest_R']:+.2f}R, z={p['z']}). Send /approve {p['id']} to use it.")
    for f in P.get("filters", []): lines.append(f"{'✅' if f.get('active', True) else '⏸'} Filter #{f['id']}: {f['text']}")
    return "\n".join(lines)
