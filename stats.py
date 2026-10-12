"""Performance statistics from the permanent trade history (paper-wallet trades that are CLOSED).
Honest by design: shows sample size and standard error, and says 'too few trades' instead of a verdict."""
import math, datetime as dt
from collections import defaultdict

MIN_TRADES = 30          # below this, results are noise and are labelled so


def closed_paper(records):
    rows = [r for r in records if r.get("source") == "PAPER" and r.get("status") == "CLOSED" and r.get("R") is not None]
    return sorted(rows, key=lambda r: r.get("closed") or r.get("opened") or "")


def _block(rows):
    n = len(rows)
    if not n: return dict(n=0)
    R = [float(r["R"]) for r in rows]; pnl = [float(r.get("pnl_inr") or 0) for r in rows]
    w = [x for x in R if x > 0]; l = [x for x in R if x <= 0]; mean = sum(R) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in R) / (n - 1)) if n > 1 else 0.0
    gp, gl = sum(p for p in pnl if p > 0), -sum(p for p in pnl if p < 0)
    return dict(n=n, wins=len(w), losses=len(l), win_pct=round(len(w) / n * 100, 1), mean_R=round(mean, 3), se=round(sd / math.sqrt(n), 3) if n > 1 else None,
                net_inr=round(sum(pnl), 2), profit_factor=round(gp / gl, 2) if gl > 0 else None, avg_win_R=round(sum(w) / len(w), 2) if w else 0, avg_loss_R=round(sum(l) / len(l), 2) if l else 0)


def streaks(rows):
    best_w = best_l = cw = cl = 0
    for r in rows:
        if r["R"] > 0: cw += 1; cl = 0
        else: cl += 1; cw = 0
        best_w, best_l = max(best_w, cw), max(best_l, cl)
    return dict(best_win_streak=best_w, worst_loss_streak=best_l, current=("W" if rows and rows[-1]["R"] > 0 else "L") + str(cw or cl) if rows else "-")


def drawdown(rows, start=20000.0):
    eq = peak = start; mdd = 0.0; curve = []
    for r in rows:
        eq += float(r.get("pnl_inr") or 0); peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak * 100); curve.append(round(eq, 2))
    return round(mdd, 2), curve


def _ist_dt(r):
    try: return dt.datetime.fromisoformat(r["opened"]).astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    except Exception: return None


def breakdown(rows, keyfn):
    g = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k is not None: g[k].append(r)
    return {k: _block(v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def analyse(records, start=20000.0):
    rows = closed_paper(records); mdd, curve = drawdown(rows, start)
    out = dict(overall=_block(rows), streaks=streaks(rows), max_drawdown_pct=mdd, curve=curve, rows=rows,
               by_side=breakdown(rows, lambda r: r.get("side")), by_strategy=breakdown(rows, lambda r: r.get("label") or r.get("strategy")),
               by_outcome=breakdown(rows, lambda r: r.get("outcome")),
               by_weekday=breakdown(rows, lambda r: (_ist_dt(r).strftime("%a") if _ist_dt(r) else None)),
               by_hour_block=breakdown(rows, lambda r: (f"{_ist_dt(r).hour // 6 * 6:02d}-{_ist_dt(r).hour // 6 * 6 + 6:02d}h IST" if _ist_dt(r) else None)))
    n = out["overall"].get("n", 0); o = out["overall"]
    if n == 0: out["verdict"] = "No closed paper trades yet."
    elif n < MIN_TRADES: out["verdict"] = f"Only {n} closed trades. Too few to say anything (need about {MIN_TRADES}+, ideally 100+). Results below are noise."
    else:
        lo, hi = o["mean_R"] - 2 * (o["se"] or 0), o["mean_R"] + 2 * (o["se"] or 0)
        out["verdict"] = (f"Average {o['mean_R']:+.2f}R per trade (95% range {lo:+.2f} to {hi:+.2f}). " + ("Range is above zero: a possible edge, keep watching." if lo > 0 else "Range is below zero: this is losing." if hi < 0 else "Range includes zero: NOT proven, cannot tell luck from skill yet."))
    return out


def text(records, start=20000.0):
    a = analyse(records, start); o = a["overall"]
    if not o.get("n"): return "📊 STATS\n" + a["verdict"]
    s = a["streaks"]
    lines = ["📊 PERFORMANCE (paper wallet, closed trades)", f"Trades {o['n']} | win {o['win_pct']}% ({o['wins']}W/{o['losses']}L) | avg {o['mean_R']:+.2f}R | net ₹{o['net_inr']:,.0f}",
             f"Profit factor {o['profit_factor']} | avg win {o['avg_win_R']:+.2f}R | avg loss {o['avg_loss_R']:+.2f}R | max drawdown {a['max_drawdown_pct']}%",
             f"Streaks: best win {s['best_win_streak']}, worst loss {s['worst_loss_streak']}, now {s['current']}"]
    for k, v in a["by_side"].items(): lines.append(f"{k}: {v['n']} trades, win {v['win_pct']}%, avg {v['mean_R']:+.2f}R")
    lines.append("🧪 " + a["verdict"]); return "\n".join(lines)


def history_text(records, n=5):
    rows = sorted(records, key=lambda r: r.get("opened") or "", reverse=True)[:n]
    if not rows: return "Abhi koi trade record nahi hai."
    out = []
    for r in rows:
        res = f"{r.get('outcome') or r['status']}" + (f" {r['R']:+.2f}R ₹{r['pnl_inr']:,.0f}" if r.get("R") is not None and r.get("pnl_inr") is not None else "")
        out.append(f"{r['id']} | {r.get('side')} | {r.get('opened_ist')}\n   {res}" + (f" | feedback {r['user_rating']}" if r.get("user_rating") else ""))
    return "🗂 LAST TRADES (permanent record)\n" + "\n".join(out) + "\nDetail: /timeline ID"


def timeline_text(rec):
    tl = "\n".join(f"{e['time_ist']}  {e['type']}  ${e['price']:,.0f}  {e.get('note') or ''}".rstrip() for e in rec.get("timeline", []) if e.get("price") is not None) or "-"
    return (f"🧾 {rec['id']} ({rec.get('side')}) {rec.get('status')}\nOpened: {rec.get('opened_ist')} | Closed: {rec.get('closed_ist') or '-'}\n"
            f"Why: {rec.get('why') or '-'}\nResult: {rec.get('outcome') or 'open'}" + (f" {rec['R']:+.2f}R ₹{rec['pnl_inr']:,.0f}" if rec.get("R") is not None and rec.get("pnl_inr") is not None else "")
            + f"\nYour feedback: {rec.get('user_rating') or '-'} {rec.get('user_note') or ''}\n\nTimeline (IST):\n{tl}")
