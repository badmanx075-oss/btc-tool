"""Virtual wallet with an auditable ledger. All amounts in INR. Opening a trade LOCKS margin and charges the entry fee; closing releases it with P&L."""
def _add(W, now, typ, tid, amt, note):
    W["cash"] = round(W["cash"] + amt, 2)
    W["ledger"].append(dict(ts=now.isoformat(timespec="seconds"), type=typ, trade_id=tid, amount=round(amt, 2), cash=W["cash"], margin=round(W["margin"], 2), equity=round(W["cash"] + W["margin"], 2), note=note))
    del W["ledger"][:-3000]

def init(P, C, now):
    start = float(C["wallet"]["start_inr"]); W = P.get("wallet")
    if W is None:
        old = P.get("balance") if (P.get("closed") or P.get("open")) else None; base = float(old) if old is not None else start
        W = P["wallet"] = dict(start=float(P.get("start", base)) if old is not None else start, cash=0.0, margin=0.0, touched=old is not None, ledger=[])
        _add(W, now, "DEPOSIT", "", base, "Virtual wallet created")
    elif not W["touched"] and abs(W["start"] - start) > 1e-9:   # start amount changed in config before any trade
        W.update(start=start, cash=0.0, margin=0.0, ledger=[]); _add(W, now, "DEPOSIT", "", start, "Wallet reset to the start amount in config.json")
    sync(P); return W

def sync(P): W = P["wallet"]; P["balance"] = round(W["cash"] + W["margin"], 2); P["start"] = W["start"]

def lock(P, now, tid, margin, fee):
    W = P["wallet"]; W["margin"] = round(W["margin"] + margin, 2); W["touched"] = True
    _add(W, now, "MARGIN_LOCK", tid, -margin, "Margin locked for open trade"); _add(W, now, "FEE_ENTRY", tid, -fee, "Entry fee"); sync(P)

def release(P, now, tid, margin, pnl, fee, note):
    W = P["wallet"]; W["margin"] = round(W["margin"] - margin, 2)
    _add(W, now, "MARGIN_RELEASE", tid, margin, "Margin released: " + note); _add(W, now, "PNL_REALIZED", tid, pnl, "Gross profit/loss: " + note); _add(W, now, "FEE_EXIT", tid, -fee, "Exit fee")
    if abs(W["margin"]) < 0.05: W["margin"] = 0.0     # rounding dust
    sync(P)

def summary(P):
    W = P.get("wallet") or {}
    if not W: return "💰 Wallet abhi bana nahi: pehla scan hone par ban jayega."
    eq = W.get("cash", 0) + W.get("margin", 0); st = W.get("start", eq or 1); op = [t for t in (P.get("pos") or {}).values() if t]
    return (f"💰 WALLET (virtual)\nEquity ₹{eq:,.0f} ({(eq / st - 1) * 100:+.1f}% since start ₹{st:,.0f})\nFree cash ₹{W.get('cash', 0):,.0f} | in open trades ₹{W.get('margin', 0):,.0f}\n"
            f"Open positions: {len(op)} | closed: {len(P.get('closed', []))} | max drawdown {P.get('max_dd_pct', 0)}%")

def trades_text(P, n=6):
    L = ["📒 OPEN"] + ([f"{t['id']} {'BUY' if t['side'] == 1 else 'SELL'} {t['qty']} BTC @ ${t['entry']:,.0f} stop ${t['sl']:,.0f}" for t in (P.get("pos") or {}).values() if t] or ["none"])
    L += ["", "📕 LAST CLOSED"] + [f"{t['id']} {t['outcome']} {t['R']:+.2f}R ₹{t['pnl_inr']:,.0f}" for t in P.get("closed", [])[-n:]]
    return "\n".join(L)
