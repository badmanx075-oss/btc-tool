"""Continuous-testing support: entry-context snapshot, near-miss shadow trades, calibration tables, readiness meter,
and the REVIEW PACK (one file you send to Claude so the rules can be tuned on real evidence).
Nothing here changes a trade. Read-only analysis + extra data collection."""
import json, datetime as dt
import stats, history, config, lifecycle

TARGET_FIRST, TARGET_STRONG = 30, 100        # trades before a first honest look / before a confident one
MILESTONES = (10, 20, 30, 50, 75, 100, 150, 200)


def _small(x, n=2500):
    try:
        s = json.dumps(x, default=str)
        return x if len(s) <= n else s[:n] + "…"
    except Exception: return None


def session(hour_utc):
    return "Asia (00-08 UTC)" if hour_utc < 8 else "Europe (08-13 UTC)" if hour_utc < 13 else "US (13-21 UTC)" if hour_utc < 21 else "Late (21-24 UTC)"


def grade(strategy, ctx):
    """A = strongest, B = good, C = weak. Only a label for later analysis."""
    if strategy == "trend_pullback": return "A" if (ctx or {}).get("er4", 0) >= 0.45 else "B"
    s = (ctx or {}).get("score", 0)
    return "A" if s >= 80 else "B" if s >= 65 else "C"


def entry_ctx(S, now):
    """Everything the tool knew at the moment of entry (kept with the trade forever)."""
    A, D = S.get("analysis") or {}, S.get("desk") or {}; M = S.get("market") or {}; P = S.get("paper") or {}
    rad = (P.get("radar") or {}); d = D.get("derivs") or {}
    return dict(time_utc=now.isoformat(timespec="seconds"), session=session(now.hour), weekday=now.strftime("%a"),
                regime=M.get("regime") or A.get("regime"), stage=A.get("stage"), stage_status=A.get("status"), direction=A.get("direction"),
                scores={k: round(float(v), 1) for k, v in (A.get("scores") or {}).items() if isinstance(v, (int, float))}, false_signal_risk=A.get("false_signal_risk"),
                range=A.get("range"), expected_move=_small((A.get("expected_move") or {}).get("expected")), mtf=_small([(r["tf"], r["direction"], r["strength"]) for r in (D.get("mtf") or {}).get("rows", [])]),
                crowding=d.get("crowding"), oi_quadrant=d.get("quadrant"), taker_delta=d.get("taker_delta"), liquidations=d.get("liquidations"), funding=M.get("funding"),
                radar={s: sum(c[1] for c in rad.get(s, [])) for s in ("LONG", "SHORT")} if rad else None, reversal=M.get("reversal"))


# ------------------------------------------------------------ near-miss shadows (more samples without risking anything)
def near_miss_step(S, P, scan, sc, h15, now, fee):
    """When the early signal fires but score is just under the entry bar (50..min_score), simulate it as a shadow trade.
    Later we can tell whether the bar is too strict or too loose."""
    from paper import shadow_step
    NM = P.setdefault("nearmiss", [])
    for sh in NM:
        if "R" not in sh: shadow_step(sh, h15, now, fee)
    del NM[:-150]
    if not scan or not scan["signal"].startswith("EARLY") or sc.get("min_score") is None: return
    if not (50 <= scan["score"] < sc["min_score"]): return
    if any((now - dt.datetime.fromisoformat(x["created"])).total_seconds() < 6 * 3600 for x in NM): return
    k = 1 if scan["side"] == "LONG" else -1; e = float(scan["entry"]); risk = abs(e - float(scan["sl"]))
    if risk <= 0: return
    sh = lifecycle.new_state(k, e, float(scan["sl"]), "staged", None, float(scan["t1"]), float(scan["t2"]), sc.get("partial_pct", 50) / 100)
    sh.update(min_score=sc["min_score"], id=f"NEARMISS-{now.strftime('%Y%m%d%H%M')}", strategy="early_signal", side_name=scan["side"], score=scan["score"], created=now.isoformat(timespec="seconds"), exits=[],
              last_ts=float(h15.ts.iloc[-1]), expiry_h=sc["expiry_hours"], ctx=dict(score=scan["score"], regime=scan["regime"], hour=now.hour), entry_ctx=entry_ctx(S, now))
    NM.append(sh)


# ------------------------------------------------------------ calibration
def _bucket_score(v):
    if v is None: return "n/a"
    return "80+" if v >= 80 else "70-79" if v >= 70 else "65-69" if v >= 65 else "50-64"


def _groups(rows, keyf):
    g = {}
    for r in rows:
        try: g.setdefault(str(keyf(r)), []).append(r)
        except Exception: g.setdefault("n/a", []).append(r)
    out = {}
    for k, v in sorted(g.items()):
        b = stats._block(v); b["small_sample"] = b["n"] < 5; out[k] = b
    return out


def calibration(rows):
    ctxof = lambda r: (r.get("raw") or {}).get("entry_ctx") or r.get("context") or {}
    sc = lambda r: ((r.get("raw") or {}).get("ctx") or {}).get("score")
    return dict(
        by_strategy=_groups(rows, lambda r: r.get("strategy")), by_side=_groups(rows, lambda r: r.get("side")),
        by_grade=_groups(rows, lambda r: grade(r.get("strategy"), (r.get("raw") or {}).get("ctx"))),
        by_score_bucket=_groups([r for r in rows if sc(r) is not None], lambda r: _bucket_score(sc(r))),
        by_session=_groups(rows, lambda r: ctxof(r).get("session") or (session(r["raw"]["ctx"]["hour"]) if ((r.get("raw") or {}).get("ctx") or {}).get("hour") is not None else "n/a")), by_regime=_groups(rows, lambda r: ((r.get("raw") or {}).get("ctx") or {}).get("regime") or ctxof(r).get("regime") or "n/a"),
        by_outcome=_groups(rows, lambda r: r.get("outcome")), by_hold=_groups(rows, lambda r: "<6h" if (r.get("hold_h") or 0) < 6 else "6-24h" if r["hold_h"] < 24 else "1-3d" if r["hold_h"] < 72 else "3d+"))


def shadow_summary(P):
    def blk(lst):
        done = [s for s in lst if "R" in s]; R = [s["R"] for s in done]
        return dict(tracked=len(lst), finished=len(done), mean_R=round(sum(R) / len(R), 3) if R else None, win_pct=round(sum(r > 0 for r in R) / len(R) * 100, 1) if R else None)
    return dict(near_miss=blk(P.get("nearmiss") or []), filter_blocked=blk([s for s in (P.get("shadow") or []) if "mode" in s]))


# ------------------------------------------------------------ readiness
def readiness(S, rows=None):
    rows = rows if rows is not None else stats.closed_paper(history.load()["records"].values()); n = len(rows)
    P = S.get("paper") or {}; sh = shadow_summary(P); extra = sh["near_miss"]["finished"] + sh["filter_blocked"]["finished"]
    pct = min(n / TARGET_FIRST * 100, 100)
    if n >= TARGET_STRONG: msg = f"🟢 {n} trades: kaafi data hai. Review pack bhejo, rules tune karenge."
    elif n >= TARGET_FIRST: msg = f"🟢 {n} trades: pehla honest review ho sakta hai. /export bhejo."
    elif n >= 15: msg = f"🟡 {n}/{TARGET_FIRST} trades: aadha raasta. Abhi bhi kaam ka review mil sakta hai par conclusions kamzor honge."
    else: msg = f"🔴 {n}/{TARGET_FIRST} trades: abhi bahut kam. Tool ko chalne do."
    return dict(closed=n, target=TARGET_FIRST, strong_target=TARGET_STRONG, pct=round(pct), message=msg, shadow_finished=extra, ready=n >= TARGET_FIRST)


# ------------------------------------------------------------ the pack
def _trade_row(r):
    raw = r.get("raw") or {}
    return dict(id=r["id"], strategy=r.get("strategy"), side=r.get("side"), opened_ist=r.get("opened_ist"), closed_ist=r.get("closed_ist"), entry=r.get("entry"), stop=r.get("stop"), targets=r.get("targets"),
                exit=r.get("exit"), outcome=r.get("outcome"), R=r.get("R"), pnl_inr=r.get("pnl_inr"), hold_h=r.get("hold_h"), best_R=r.get("best_R"), worst_R=r.get("worst_R"), grade=grade(r.get("strategy"), raw.get("ctx")),
                setup_ctx=raw.get("ctx"), entry_context=raw.get("entry_ctx"), why=r.get("why"), exits=r.get("exits"), lesson=r.get("lesson"), auto_feedback=r.get("auto_feedback"),
                user_rating=r.get("user_rating"), user_note=r.get("user_note"), user_exit=r.get("user_exit"), config_at_entry=raw.get("cfg"))


def pack(S, now=None, records=None):
    now = now or dt.datetime.now(dt.timezone.utc); recs = list(records) if records is not None else list(history.load()["records"].values()); rows = stats.closed_paper(recs); P = S.get("paper") or {}; W = P.get("wallet") or {}
    ok_ = [r for r in rows]
    return dict(
        about="BTC tool review pack. Paper trades only, no real money. Send this file to Claude for rule tuning. Conclusions need 30+ trades; treat small groups as noise.",
        generated_utc=now.isoformat(timespec="seconds"), readiness=readiness(S, rows), overall=stats._block(ok_) if ok_ else dict(n=0),
        wallet=dict(start=W.get("start"), cash=W.get("cash"), margin=W.get("margin"), balance=P.get("balance"), max_drawdown_pct=P.get("max_dd_pct")),
        calibration=calibration(rows), shadows=shadow_summary(P), settings=config.load(),
        learning=dict(filters=P.get("filters"), proposals=P.get("proposals"), lessons=P.get("lessons")),
        open_trades=[dict(id=t["id"], side=t["side"], entry=t["entry"], sl=t["sl"], mgmt=t.get("mgmt"), why=t.get("why")) for t in (P.get("pos") or {}).values() if t],
        health=dict(telegram={k: v for k, v in (S.get("telegram") or {}).items() if k != "log"}, last_price=S.get("last_price")),
        near_miss_trades=[dict(id=s["id"], score=s.get("score"), R=s.get("R"), created=s.get("created")) for s in (P.get("nearmiss") or [])][-60:],
        trades=[_trade_row(r) for r in rows],
        questions_for_claude=["Which grade / score bucket / session / regime is clearly better or worse (n>=5 only)?", "Are stops too tight or targets too far (look at best_R vs worst_R)?",
                              "Is min_score too strict or loose (see near_miss vs taken)?", "Which learned filters should be approved or reverted?", "Any data-quality problem (duplicates, odd fills)?"])


def pack_md(pk):
    """Short readable version for pasting into a chat."""
    o, rd = pk["overall"], pk["readiness"]; L = [f"# BTC tool review pack ({pk['generated_utc'][:10]})", rd["message"],
        f"Overall: n={o.get('n')} win%={o.get('win_pct')} meanR={o.get('mean_R')} (se {o.get('se')}) net ₹{o.get('net_inr')} PF={o.get('profit_factor')} | max DD {pk['wallet'].get('max_drawdown_pct')}%", "", "## Calibration (n, win%, meanR)"]
    for name, g in pk["calibration"].items():
        L.append(f"**{name}**: " + "; ".join(f"{k}: n={v['n']} win={v.get('win_pct')}% R={v.get('mean_R')}{'*' if v.get('small_sample') else ''}" for k, v in g.items()))
    L.append("(* = fewer than 5 trades)"); s = pk["shadows"]; L += ["", f"Shadow: near-miss {s['near_miss']}, filter-blocked {s['filter_blocked']}", "", "## Trades"]
    for t in pk["trades"]:
        L.append(f"- {t['id']} {t['side']} g{t['grade']} {t['outcome']} R={t['R']} best={t['best_R']} worst={t['worst_R']} hold={t['hold_h']}h sess={((t.get('entry_context') or {}).get('session'))} | {t.get('user_rating') or ''} {t.get('user_note') or ''}")
    return "\n".join(L)


def milestone(S):
    """Returns the milestone number just reached (once), else None."""
    n = readiness(S)["closed"]; done = S.setdefault("milestones", [])
    hit = [m for m in MILESTONES if n >= m and m not in done]
    if hit: done.extend(hit); return max(hit)
    return None
