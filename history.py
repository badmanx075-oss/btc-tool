"""Permanent trade history (append-only archive).

Every trade the tool ever takes (early-signal alerts and paper-wallet trades) is copied into
`trade_history.json`. That file is separate from state.json, so it survives wallet resets, state
migrations, code upgrades and dashboard refreshes. Rules:
  * records are only ADDED or UPDATED, never removed;
  * an update only overwrites a field when the new value is not empty (so a field that later
    disappears from state.json is still kept here);
  * the full original trade is kept under "raw", so future versions can read any field;
  * the file is written atomically (temp file + rename) and a corrupt file is moved aside, not erased.
Schema changes: bump SCHEMA and add a step in _upgrade(); old records stay readable.
"""
import os, json, glob, datetime as dt

FILE = "trade_history.json"
SCHEMA = 1
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def ist(ts):
    """ISO / epoch-ms timestamp -> '11 Oct 2026, 06:15 PM IST' (empty string if unknown)."""
    if ts in (None, "", 0): return ""
    try:
        d = dt.datetime.fromtimestamp(float(ts) / 1000, dt.timezone.utc) if isinstance(ts, (int, float)) else dt.datetime.fromisoformat(str(ts))
        if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    except Exception: return str(ts)


def _empty(): return dict(schema=SCHEMA, created=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), records={})


def load(path=FILE):
    if not os.path.exists(path): return _empty()
    try:
        H = json.load(open(path))
        if not isinstance(H.get("records"), dict): raise ValueError("no records")
        return _upgrade(H)
    except Exception as e:                                       # never overwrite a damaged file: keep it for recovery
        bad = path + ".damaged-" + dt.datetime.now().strftime("%Y%m%d%H%M%S")
        try: os.replace(path, bad); print("history file unreadable, moved to", bad, e)
        except OSError: pass
        return _empty()


def _upgrade(H):
    H.setdefault("schema", 1)          # future: if H["schema"] < 2: migrate records here, then set H["schema"] = 2
    return H


def save(H, path=FILE):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(H, f, indent=1, default=str)
    os.replace(tmp, path)


def _side(v): return "LONG" if v in (1, "LONG") else "SHORT" if v in (-1, "SHORT") else str(v)


def _timeline(events):
    return [dict(time_ist=ist(e.get("ts")), type=e.get("type"), price=e.get("price"), note=e.get("note", "")) for e in (events or [])]


def from_paper(t, closed):
    fb = t.get("feedback") or {}; u = fb.get("user") or {}; a = fb.get("auto") or {}
    tgt = [x for x in (t.get("tp"), t.get("t1"), t.get("t2"), t.get("t3")) if x]
    return dict(
        id=t["id"], source="PAPER", strategy=t.get("strategy", ""), label=t.get("label", ""), side=_side(t.get("side")),
        opened=t.get("created"), opened_ist=ist(t.get("created")), entry=t.get("entry"), stop=t.get("sl0") or t.get("sl"), targets=tgt,
        qty_btc=t.get("qty"), margin_inr=t.get("margin_inr"), leverage=t.get("leverage"), risk_inr=t.get("risk_inr"),
        why=t.get("why", ""), context=t.get("ctx", {}), status="CLOSED" if closed else "OPEN",
        outcome=t.get("outcome", ""), closed=t.get("closed"), closed_ist=ist(t.get("closed")), exit=t.get("exit"), R=t.get("R"),
        pnl_inr=t.get("pnl_inr"), fees_usd=t.get("fees_usd"), hold_h=t.get("hold_h"), best_R=t.get("mfe_R"), worst_R=t.get("mae_R"),
        exits=t.get("exits", []), lesson=t.get("lesson", ""), auto_feedback=a.get("verdict", ""),
        user_rating=u.get("rating", ""), user_note=u.get("note", ""), user_feedback_ist=ist(u.get("ts")), user_exit=t.get("user_exit"),
        timeline=_timeline(t.get("events")), raw=t)


def from_signal(t):
    u = t.get("user") or {}; closed = t.get("status") == "CLOSED"
    last = next((e for e in reversed(t.get("events") or []) if e.get("type") not in ("USER TRADE TAKEN", "USER IGNORED") and not str(e.get("type", "")).startswith("USER FEEDBACK")), None)
    parts = []
    if u.get("taken") is True: parts.append("you took this trade")
    elif u.get("taken") is False: parts.append("you ignored it")
    if u.get("result"): parts.append("your result: " + str(u["result"]))
    return dict(
        id=t["id"], source="SIGNAL", strategy="early_signal_alert", label=t.get("signal", ""), side=_side(t.get("side")),
        opened=t.get("created"), opened_ist=ist(t.get("created")), entry=t.get("entry"), stop=t.get("sl0") or t.get("sl"),
        targets=[x for x in (t.get("t1"), t.get("t2"), t.get("t3")) if x], score=t.get("score"), regime=t.get("regime"),
        why="For: " + ", ".join(t.get("pro", [])) + (" | Against: " + ", ".join(t["con"]) if t.get("con") else ""),
        status="CLOSED" if closed else "OPEN", outcome=t.get("outcome", ""), closed=(last or {}).get("ts") if closed else None,
        closed_ist=ist((last or {}).get("ts")) if closed else "", best_move_pts=t.get("mfe"), worst_dip_pts=t.get("mae"),
        user_rating={"WIN": "good", "PROFIT": "good", "LOSS": "bad"}.get(str(u.get("result", "")).upper(), ""),
        user_note="; ".join(parts), timeline=_timeline(t.get("events")), raw=t)


def _merge(old, new):
    if not old: return new
    out = dict(old)
    for k, v in new.items():
        if v in (None, "", [], {}): continue                       # an empty new value never erases a stored one
        out[k] = v
    return out


def _all_trades(S):
    P = S.get("paper") or {}
    for t in (S.get("trades") or {}).values():
        if t.get("id"): yield from_signal(t)
    for t in P.get("closed", []) or []:
        if t.get("id"): yield from_paper(t, True)
    for t in (P.get("pos") or {}).values():
        if t and t.get("id"): yield from_paper(t, False)
    for a in S.get("archive", []) or []:                           # wallets that were reset earlier
        for t in a.get("closed", []) or []:
            if t.get("id"): yield from_paper(t, True)


def sync(S, path=FILE):
    """Copy every trade in the live state into the permanent file. Returns (total, added, updated)."""
    H = load(path); R = H["records"]; add = upd = 0
    for rec in _all_trades(S):
        old = R.get(rec["id"]); new = _merge(old, rec)
        if old is None: add += 1
        elif new != old: upd += 1
        R[rec["id"]] = new
    if add or upd or not os.path.exists(path):
        H["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"); save(H, path)
    return len(R), add, upd


def seed_from_backups(path=FILE, pattern="backup_before_upgrade/state_*.json"):
    """One-time: when the history file is new, also import trades found in older state backups."""
    if os.path.exists(path): return 0
    n = 0
    for f in sorted(glob.glob(pattern)):
        try: n = sync(json.load(open(f)), path)[1] + n
        except Exception as e: print("seed error", f, e)
    return n
