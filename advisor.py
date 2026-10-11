"""Position management for an open trade (spec 17-24, 32): live stage, hold/protect/book status, exhaustion + reversal watch,
trailing-stop advice, hold-vs-book comparison. ADVISORY only: the paper rule (fixed stop/target/5-day expiry) is what was backtested and stays unchanged."""
import datetime as dt
import numpy as np
import engine as E

def assess(t, h, px):
    k, e, risk, sl = t["side"], t["entry"], t["risk"], t["sl"]; tp = t.get("tp") or t.get("t2") or e + k * 4 * risk; tpR = abs(tp - e) / risk
    d = h.iloc[:-1].reset_index(drop=True); a = float(E.atr_series(d).iloc[-1]); uR = (px - e) * k / risk       # d = completed 1H bars
    c, o = d.c.values * k, d.o.values * k; hi, lo = (d.h.values, d.l.values) if k == 1 else (-d.l.values, -d.h.values); v = d.v.values
    since = d.ts.values > dt.datetime.fromisoformat(t["created"]).timestamp() * 1000; mfe = max(uR, 0.0, float(((hi[since].max() if since.any() else k * e) - k * e) / risk))
    mom = (c[-1] - c[-4]) / a; vr = float(v[-3:].mean() / max(v[-24:].mean(), 1e-9)); wick = (hi[-1] - max(c[-1], o[-1])) / max(hi[-1] - lo[-1], 1e-9)
    ext = (c[-1] - c[-24:].mean()) / a; flags = dict(structure_break=bool(c[-1] < lo[-7:-1].min()), momentum_negative=bool(mom < -0.5), gave_back=bool(mfe - uR >= 1.0))
    exh = int(30 * (mom < 0.3 and uR > 1.5) + 25 * (vr < 0.7) + 20 * (wick > 0.5) + 15 * (uR >= 3) + 10 * (ext > 3)); nflag = sum(flags.values()); near_tp = uR >= 0.875 * tpR
    if nflag == 3: status, stage = "🔴 REVERSAL RISK: CONSIDER EXIT", "REVERSAL DETECTED"
    elif exh >= 70 or near_tp: status, stage = "🟠 PROFIT-BOOKING ZONE", "PROFIT BOOKING"
    elif exh >= 50 and uR >= 1: status, stage = "🟡 PARTIAL PROFIT BOOKING ADVISED", "EXHAUSTION WATCH"
    elif nflag >= 2: status, stage = "🟡 REVERSAL WATCH", "ENTRY" if uR < 0.3 else "PROFIT DEVELOPING"
    elif uR <= -0.85: status, stage = "🟡 CAUTION: NEAR STOP-LOSS", "SETUP FAILING"
    elif uR >= 1.5: status, stage = "🟡 HOLD BUT PROTECT PROFIT", "TARGET APPROACHING" if uR >= 0.75 * tpR else "MOMENTUM STRONG"
    elif mom > 0.5 and vr >= 0.9 and uR > 0.3: status, stage = "🟢 HOLD: MOMENTUM STRONG", "MOMENTUM STRONG" if uR >= 1 else "PROFIT DEVELOPING"
    elif uR >= 0: status, stage = "🟢 HOLD: MORE UPSIDE POSSIBLE", "PROFIT DEVELOPING" if uR >= 0.3 else "ENTRY"
    else: status, stage = "🟢 HOLD: THESIS INTACT", "ENTRY"
    R = []
    R.append("Momentum " + ("dheema pad raha hai" if mom < 0.3 else "trend ke saath chal raha hai") + f" (pichle 3 ghante {mom:+.1f} ATR)")
    R.append("Volume " + ("kam ho raha hai" if vr < 0.7 else "theek hai") + f" (normal ka {vr:.1f} guna)")
    if wick > 0.5: R.append("Pichli candle mein upar (trend ki taraf) se rejection wick hai: bhaav wahan tik nahi paya")
    if flags["structure_break"]: R.append("Bhaav ne pichla chhota swing trend ke khilaaf tod diya")
    if flags["gave_back"]: R.append(f"Trade +{mfe:.1f}R tak gaya tha, ab {mfe - uR:.1f}R wapas de diya")
    if near_tp: R.append("Target bahut paas hai")
    cs = c[since]; hc = float(cs.max()) if len(cs) else float(c[-1]); be, atr_t, st_t = k * e, hc - 3 * a, float(lo[-12:].min()) - 0.2 * a
    better = lambda x: (x - sl * k) > 0                      # in direction-space: is x a tighter stop than the current one?
    if exh >= 50 and better(atr_t): adv, newsl = f"Stop tight karo: ATR trail ${atr_t * k:,.0f}", atr_t * k
    elif uR >= 1.5 and better(st_t): adv, newsl = f"Stop structure ke neeche ${st_t * k:,.0f} tak le ja sakte ho", st_t * k
    elif uR >= 1 and better(be): adv, newsl = f"Stop breakeven (${e:,.0f}) par le jaana soch sakte ho", float(e)
    else: adv, newsl = "Stop jaisa hai waisa rakho", float(sl)
    left, riskleft = (tp - px) * k / risk, max((px - newsl) * k / risk, 0.05)
    hvb = f"Hold: target {left:.1f}R door, stop tak {riskleft:.1f}R (R/R {left / riskleft:.1f}). Abhi book karo to +{uR:.1f}R pakka."
    return dict(status=status, stage=stage, uR=round(float(uR), 2), mfe_R=round(float(mfe), 2), exhaustion=exh, reversal_flags=flags, reasons=R, stop_advice=adv, suggested_sl=round(float(newsl), 1),
                hold_vs_book=hvb, next_zone=round(float(e + k * 0.75 * tpR * risk), 1), momentum_atr=round(float(mom), 2), volume_ratio=round(vr, 2))

def message(t, m, px):
    return (f"📊 POSITION UPDATE\n{t['id']}\nStage: {m['stage']}\nStatus: {m['status']}\nNow ${px:,.0f} | Open P/L {m['uR']:+.2f}R | Exhaustion {m['exhaustion']}/100\n"
            + "\n".join("• " + r for r in m["reasons"]) + f"\n{m['hold_vs_book']}\n{m['stop_advice']}\nAgla decision zone: ${m['next_zone']:,.0f}\n"
            "(Salah hai. Paper rule sirf stop/target/5 din par band karta hai. Probabilistic, guarantee nahi.)")
