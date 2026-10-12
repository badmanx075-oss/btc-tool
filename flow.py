"""Free order-flow recorder (spec 34): taker buy/sell balance from the latest public trades and recent liquidations (OKX public API, no key).
Written to flow_log.csv, its own file so market_log.csv keeps its format. Best effort: any failure just records nothing for that run."""
import os, datetime as dt
import engine as E

FILE = "flow_log.csv"; HEAD = "ts,price,buy_ct,sell_ct,n_trades,liq_long_usd,liq_short_usd\n"
CT_BTC = 0.01        # BTC-USDT-SWAP: one contract = 0.01 BTC


def fetch():
    t = E._get("market/trades", instId=E.INST, limit=500)
    buy = sum(float(x["sz"]) for x in t if x.get("side") == "buy"); sell = sum(float(x["sz"]) for x in t if x.get("side") == "sell")
    px = float(t[0]["px"]) if t else 0.0; ll = ls = 0.0
    try:
        for grp in E._get("public/liquidation-orders", instType="SWAP", uly="BTC-USDT", state="filled", limit=100):
            for d in grp.get("details", []):
                usd = float(d["sz"]) * CT_BTC * float(d.get("bkPx") or px)
                if d.get("side") == "sell": ll += usd          # a long position was force-sold
                elif d.get("side") == "buy": ls += usd         # a short position was force-bought
    except Exception: ll = ls = float("nan")
    return dict(price=px, buy=buy, sell=sell, n=len(t), liq_long=ll, liq_short=ls)


def record(now, path=FILE):
    try: r = fetch()
    except Exception as e: print("flow record skipped:", type(e).__name__); return None
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new: f.write(HEAD)
        f.write(f"{now.isoformat(timespec='seconds')},{r['price']},{r['buy']},{r['sell']},{r['n']},{r['liq_long']:.0f},{r['liq_short']:.0f}\n")
    return r
