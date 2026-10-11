"""Trade lifecycle rules: ONE source of truth used by live paper trading AND the backtests, so tests mean what live does."""
def new_state(k, entry, sl, mode, tp=None, t1=None, t2=None, partial=0.5):
    return dict(side=k, entry=entry, sl=sl, risk=abs(entry - sl), mode=mode, tp=tp, t1=t1, t2=t2, partial=partial, stage=0, remaining=1.0, mfe_R=0.0, mae_R=0.0)

def advance(t, c):
    """Apply one candle (needs .h and .l). Returns [(kind, price, fraction_of_original_qty)]. Inside one candle the stop is checked first (conservative)."""
    k, out = t["side"], []
    up = lambda lv: (c.h >= lv) if k == 1 else (c.l <= lv)      # price touched a level in our favour
    dn = lambda lv: (c.l <= lv) if k == 1 else (c.h >= lv)      # price touched a level against us
    t["mfe_R"] = max(t["mfe_R"], ((c.h if k == 1 else c.l) - t["entry"]) * k / t["risk"]); t["mae_R"] = max(t["mae_R"], (t["entry"] - (c.l if k == 1 else c.h)) * k / t["risk"])
    if t["remaining"] <= 1e-9: return out
    if dn(t["sl"]):
        out.append(("STOP-LOSS" if t["stage"] == 0 else "BREAKEVEN STOP", t["sl"], t["remaining"])); t["remaining"] = 0; return out
    if t["mode"] == "fixed":
        if up(t["tp"]): out.append(("TARGET", t["tp"], t["remaining"])); t["remaining"] = 0
        return out
    if t["stage"] == 0 and up(t["t1"]):
        f = t["partial"]; out.append(("T1 PARTIAL", t["t1"], f)); t["remaining"] -= f; t["stage"] = 1; t["sl"] = t["entry"]
        if dn(t["sl"]): out.append(("BREAKEVEN STOP", t["sl"], t["remaining"])); t["remaining"] = 0; return out    # same candle also touched entry: assume the worst
    if t["stage"] == 1 and t["remaining"] > 1e-9 and up(t["t2"]): out.append(("T2 TARGET", t["t2"], t["remaining"])); t["remaining"] = 0
    return out

def trade_R(exits, entry, k, risk, fee):
    """Net result in R after fees (fee = rate per side). exits = [(kind, price, fraction)] adding up to 1."""
    return (sum(f * (p - entry) * k for _, p, f in exits) - fee * (entry + sum(f * p for _, p, f in exits))) / risk
