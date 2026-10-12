"""The 27 real-time questions of spec section 37, answered in plain words from the latest analysis, desk data and open position.
Every answer is informational and probabilistic. Nothing here is a prediction or an order."""


def _p(x): return f"${x:,.0f}"


def _rng(z): return f"{_p(z[0])} - {_p(z[1])}"


def build(A, M=None, desk=None, pos=None, v7=None):
    """A: analysis snapshot, M: market dict (engine scan), desk: desk.build output, pos: open paper position (with 'mgmt') or None, v7: backtest_v7 results."""
    if not A: return []
    L = A.get("levels"); ex = A.get("expected_move"); s = A["scores"]; px = A["price"]; desk = desk or {}; M = M or {}; rev = desk.get("reversal") or {}; mv = desk.get("moves") or {}; der = desk.get("derivs") or {}
    side = A.get("direction"); no_trade = A["status"].startswith("NO TRADE"); m = (pos or {}).get("mgmt") if pos else None; Q = []
    add = lambda q, a: Q.append((len(Q) + 1, q, a))
    add("What is the current market regime?", f"{A['regime']}. Stage: {A['stage']}. Timeframes: {(desk.get('mtf') or {}).get('alignment', 'n/a')}.")
    add("Is there an opportunity?", ("No: evidence is too weak or mixed. NO TRADE is a valid answer." if no_trade else f"{A['status']}. Setup score {s['setup']:.0f}/100, false-signal risk {A['false_signal_risk']}."))
    brk = A.get("breakout", "none"); typ = "NO TRADE"
    if not no_trade:
        typ = (f"BREAKOUT ({brk})" if brk != "none" and "FAILED" not in brk else "REVERSAL (" + rev["direction"] + " " + rev["status"] + ")" if rev.get("status") == "CONFIRMED" else
               "RANGE trade (" + side + " near the range " + ("low" if side == "LONG" else "high") + ")" if "RANGE" in A["regime"] else side)
    add("Is it LONG, SHORT, BREAKOUT, REVERSAL, RANGE or NO TRADE?", typ + (f". Reversal watch: {rev['note']}" if rev.get("status") == "WATCH" else "") + (f". Breakout status: {brk}" if brk != "none" and no_trade else ""))
    add("Is the opportunity early or already late?", (L["entry_state"] if L else "No active setup, so nothing to be early or late for."))
    pro = M.get("pro") or []; con = list(M.get("con") or []) + [x for x, f in A.get("checklist", []) if f]
    add("What evidence supports it?", ("; ".join(pro) if pro else "Nothing strong right now."))
    add("What evidence contradicts it?", ("; ".join(dict.fromkeys(con)) if con else "No contradicting signs found."))
    add("Where is the entry zone?", (f"Early zone {_rng(L['early_zone'])} | confirmation entry beyond {_p(L['confirmation'])} | retest zone {_rng(L['retest_zone'])} | late (avoid chasing) beyond {_p(L['late_above'])}" if L else "No setup: no entry zone."))
    add("Where is the invalidation / stop level?", (f"Hard invalidation {_p(L['hard_invalidation'])}, preferred stop {_p(L['preferred_sl'])}, emergency {_p(L['emergency_sl'])}. WHY: beyond the hard level the swing point that supports the idea has failed, so the setup is no longer what it was. "
                                                    f"The preferred stop adds room of about {abs(px - L['preferred_sl']) / max(desk.get('atr1h', 1), 1):.1f} x hourly ATR so normal noise does not stop it out; the emergency level (3 ATR) is the 'something is clearly wrong' line." if L else "No setup."))
    add("What is the expected move range?", (f"Expected {_rng([px + ex['expected'][0] * (1 if ex['side'] == 'up' else -1), px + ex['expected'][1] * (1 if ex['side'] == 'up' else -1)])}, strong move to {_p(px + ex['strong'][1] * (1 if ex['side'] == 'up' else -1))}, extended beyond {_p(px + ex['extended'][1] * (1 if ex['side'] == 'up' else -1))} (from history of similar volatility, sample {ex['sample']} hours)" if ex else "Run the research workflow to build the move statistics."))
    rows = mv.get("rows") or []
    big = "; ".join(f"{r['points']:,} pts ({r['size_class'].split(' ')[0]}, {r['atr4h_multiple']}x 4H ATR): up {r.get('up_24h', 0) * 100:.0f}% / down {r.get('dn_24h', 0) * 100:.0f}% within 24h" for r in rows if "up_24h" in r)
    add("Could this be a 1,000 / 2,000 / 5,000 / 10,000+ point move?", (f"Large-move potential score {s.get('large_move_potential')}/100. History in {mv.get('bucket_name')} volatility: {big}" if big else f"Large-move potential {s.get('large_move_potential')}. Move statistics not built yet (run the research workflow)."))
    if v7 and v7.get("targets"):
        tg = v7["targets"]; add("What are the historical probabilities for similar setups?", f"Live strategy, {v7['trades']} past entries: reached 1.5R before the stop {tg['1.5']['hit_before_stop_pct']}%, 3R {tg['3']['hit_before_stop_pct']}%, 5R {tg['5']['hit_before_stop_pct']}%, 8R {tg['8']['hit_before_stop_pct']}%; stopped out first {v7['stops']['stop_before_1R_pct']}% of the time. History, not a forecast.")
    else: add("What are the historical probabilities for similar setups?", "Run the research workflow (days 2000) to build them.")
    for n_, key in (("Target 1", "t1"), ("Target 2", "t2"), ("Target 3", "t3"), ("The extended target", "extended")): add(f"What is {n_}?", (_p(L[key]) + (f" ({L['targets_from']})" if key == "t1" else "") if L else "No setup."))
    if L:
        risk = abs(px - L["preferred_sl"]); add("What is the risk/reward?", f"Risk about {risk:,.0f} pts. T1 gives {abs(L['t1'] - px) / risk:.1f}R, T2 {abs(L['t2'] - px) / risk:.1f}R, T3 {abs(L['t3'] - px) / risk:.1f}R, extended {abs(L['extended'] - px) / risk:.1f}R.")
    else: add("What is the risk/reward?", "No setup.")
    flat = "Not in a trade right now. This answers live once a trade is open. "
    if m:
        add("After entry, is the move still healthy?", f"{m['status']} (stage {m['stage']}, open P/L {m['uR']:+.2f}R).")
        add("Should I continue holding?", ("Supportive: " if "HOLD" in m["status"] else "Conditions changed: ") + m["hold_vs_book"])
        add("Should I protect profit?", ("Yes, consider it. " if ("PROTECT" in m["status"] or m["exhaustion"] >= 50) else "Not urgent. ") + m["stop_advice"])
        add("Should I book partial profit?", "Advised by the system now." if "PARTIAL" in m["status"] or "BOOKING ZONE" in m["status"] else "Not advised right now.")
        add("Should I book most / all profit?", "Conditions point to exit or full booking." if ("EXIT" in m["status"] or "REVERSAL RISK" in m["status"]) else "Not advised right now.")
        left = f"{m['hold_vs_book']}"; tg = (v7 or {}).get("targets", {})
        add("Is more upside/downside still statistically supported?", left + (f" Historically 4R was reached before the stop {tg['4']['hit_before_stop_pct']}% of the time from entry." if tg.get("4") else ""))
        add("Is momentum weakening?", f"Momentum last 3h {m['momentum_atr']:+.1f} ATR, volume {m['volume_ratio']:.1f}x normal: " + ("weakening" if m["momentum_atr"] < 0.3 or m["volume_ratio"] < 0.7 else "still supportive"))
        add("Is the move becoming exhausted?", f"Exhaustion {m['exhaustion']}/100 ({'high' if m['exhaustion'] >= 70 else 'medium' if m['exhaustion'] >= 40 else 'low'}).")
        fl = [k for k, v in m["reversal_flags"].items() if v]; add("Is a reversal developing?", (f"Warning signs: {', '.join(fl)}. " if fl else "No reversal signs on the open trade. ") + rev.get("note", ""))
        add("What would invalidate the current thesis?", f"A move through the stop {_p(pos['sl'])}, or a close beyond the last swing point against the trade.")
        add("How should the stop be adjusted as the trade moves in profit?", m["stop_advice"])
    else:
        add("After entry, is the move still healthy?", flat + "Market view meanwhile: continuation strength " + f"{s['continuation']:.0f}/100.")
        add("Should I continue holding?", flat); add("Should I protect profit?", flat + "Rule of thumb in the system: advice appears from +1R (breakeven) and +1.5R (structure trail).")
        add("Should I book partial profit?", flat); add("Should I book most / all profit?", flat)
        add("Is more upside/downside still statistically supported?", flat + "Before entry see the historical probabilities above.")
        add("Is momentum weakening?", f"Market momentum score {s['momentum']:.0f}/100; derivatives: " + (der.get("items") or ["n/a"])[0])
        add("Is the move becoming exhausted?", f"Exhaustion risk {s['exhaustion_risk']:.0f}/100.")
        add("Is a reversal developing?", rev.get("note", "n/a") + ((" Signs: " + "; ".join(rev["signs"])) if rev.get("signs") else ""))
        add("What would invalidate the current thesis?", (f"A close beyond {_p(L['hard_invalidation'])}." if L else "No thesis yet."))
        add("How should the stop be adjusted as the trade moves in profit?", "Breakeven after +1R, structure trail after +1.5R, tighter if exhaustion is above 50. The system tells you live once a trade is open.")
    return Q
