"""Learning layer. Records context for every paper trade, writes a post-mortem, mines patterns across many trades,
and proposes filters. It never rewrites rules after a single loss (overfitting). A filter only runs after the user approves it (/approve N),
and it is switched off automatically if the trades it blocks (shadow trades) do as well as the trades it allows."""
import numpy as np, datetime as dt
MIN_TOTAL, MIN_BUCKET, Z_PROPOSE = 40, 15, 2.5
STRATS = ("trend_pullback", "early_signal")

def postmortem(t):
    o, m, h, R = t.get("outcome", ""), t.get("mfe_R", 0), t.get("hold_h", 0), t.get("R", 0)
    if o in ("TARGET", "T2 REACHED"): return f"Jeet: plan jaisa socha tha waisa hi chala ({R:+.1f}R)."
    if o.startswith("T1 BOOKED"): return f"Aadha profit T1 par book hua, phir bhaav palta aur baaki hissa entry par band hua ({R:+.1f}R). Partial booking ne nuksaan bachaya."
    if o == "STOP-LOSS":
        if m >= 2: return f"Haar, par pehle +{m:.1f}R tak ja chuka tha: disha sahi thi par bhaav palat gaya. Chhota target ya trailing stop shayad profit bacha leta (sirf andaza, test karna hoga)."
        if h <= 6: return f"Jaldi haar ({h:.0f} ghante, best +{m:.1f}R): entry ka timing theek nahi tha ya achanak volatility ne stop tod diya."
        return f"Dheere-dheere haar ({h:.0f} ghante, best +{m:.1f}R): trend kamzor pad gaya aur bhaav kabhi hamare favour mein nahi gaya."
    return f"Time poora hone par band, {R:+.1f}R: koi saaf move nahi aaya."

def feedback(t):  # the tool's own review of the trade (process vs outcome)
    R, m = t.get("R", 0), t.get("mfe_R", 0); cls = "WIN" if R > 0.2 else "LOSS" if R < -0.2 else "FLAT"
    if cls == "WIN": v = f"✅ Achha trade: plan ke mutabik {R:+.1f}R. Best move +{m:.1f}R tak gayi, uska {(R / m * 100 if m > 0 else 0):.0f}% pakda."
    elif cls == "LOSS": v = (f"⚠️ Haar, par +{m:.1f}R tak ja chuka tha. Exit rule par sochne layak hai (badlav test ke baad hi hoga)." if m >= 2 else f"🟡 Normal haar: sirf tay risk ({R:+.1f}R) gaya. Is tarah ki strategy mein aksar 3 mein 2 trade harte hain.")
    else: v = "⚪ Lagbhag barabari: fees ke baad profit/loss ~0."
    return dict(result=cls, verdict=v, plan_followed=True, best_R=round(m, 2), worst_R=round(t.get("mae_R", 0), 2))

def user_feedback(P, tid, good=None, note=None):
    t = next((x for x in P.get("closed", []) if x["id"] == tid), None)
    if not t: return False
    fb = t.setdefault("feedback", {}); u = fb.get("user") or {}
    if good is not None: u["rating"] = "good" if good else "bad"
    if note: u["note"] = note
    u["ts"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"); fb["user"] = u; return True

def defs(T):
    out = []
    for key, name in (("er4", "4H trend strength"), ("atr_pct", "volatility (ATR%)"), ("depth", "pullback depth"), ("score", "setup score")):
        if all(key in t["ctx"] for t in T):
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
    P["lessons"] = {}; have = {f["text"] for f in P["filters"]} | {p["text"] for p in P["proposals"]}; nid = max([p["id"] for p in P["proposals"]] + [f["id"] for f in P["filters"]] + [0])
    for s in STRATS:
        L = P["lessons"][s] = analyze([t for t in P["closed"] if t.get("strategy", "trend_pullback") == s])
        for p in L["patterns"]:
            text = f"[{s}] Skip trades when {p['feature']} is {p['bucket']}"
            if p["z"] <= -Z_PROPOSE and p["mean_R"] < 0 and text not in have and len(P["proposals"]) < 3:
                nid += 1; P["proposals"].append(dict(id=nid, strategy=s, text=text, key=p["key"], lo=p["lo"], hi=p["hi"], n=p["n"], mean_R=p["mean_R"], rest_R=p["rest_R"], z=p["z"]))

def blocked_by(P, ctx, strategy="trend_pullback"):
    for f in P["filters"]:
        v = ctx.get(f["key"])
        if f.get("strategy", "trend_pullback") == strategy and f.get("active", True) and v is not None and f["lo"] <= v < f["hi"]: return f

def approve(P, arg):
    p = next((x for x in P["proposals"] if str(x["id"]) == arg), None)
    if not p: return "No such proposal. Send /lessons to see ideas."
    P["proposals"].remove(p); P["filters"].append(dict(id=p["id"], strategy=p.get("strategy", "trend_pullback"), text=p["text"], key=p["key"], lo=p["lo"], hi=p["hi"], active=True))
    return f"Filter #{p['id']} approved: {p['text']}.\nMatching signals will be skipped but tracked as shadow trades. It switches off automatically if blocked trades do as well as allowed ones."

def revert(P, arg):
    f = next((x for x in P["filters"] if str(x["id"]) == arg), None)
    if not f: return "No such filter."
    f["active"] = False; return f"Filter #{f['id']} switched off."

def check_filters(P):
    msgs = []
    for f in P["filters"]:
        taken = [t["R"] for t in P["closed"] if "R" in t and t.get("strategy", "trend_pullback") == f.get("strategy", "trend_pullback")]
        b = [s["R"] for s in P["shadow"] if s.get("filter") == f["text"] and "R" in s]
        if f.get("active", True) and len(b) >= 10 and taken and np.mean(b) >= np.mean(taken):
            f["active"] = False; msgs.append(f"🧠 Filter #{f['id']} switched OFF: the {len(b)} trades it blocked averaged {np.mean(b):+.2f}R vs {np.mean(taken):+.2f}R taken. It was not helping.")
    return msgs

def lessons_text(P):
    lines = ["🧠 Learning"]
    for s in STRATS:
        L = (P.get("lessons") or {}).get(s) or {}; cl = [t for t in P.get("closed", []) if t.get("lesson") and t.get("strategy", "trend_pullback") == s][-2:]
        lines.append(f"[{s}] {L.get('n', 0)} trades studied"); lines += [f"• {t['id']}: {t['lesson']}" for t in cl]
        if L.get("note"): lines.append(L["note"])
    for p in P.get("proposals", []): lines.append(f"💡 #{p['id']} {p['text']} (n={p['n']}, {p['mean_R']:+.2f}R vs {p['rest_R']:+.2f}R, z={p['z']}). Send /approve {p['id']} to use it.")
    for f in P.get("filters", []): lines.append(f"{'✅' if f.get('active', True) else '⏸'} Filter #{f['id']}: {f['text']}")
    return "\n".join(lines)
