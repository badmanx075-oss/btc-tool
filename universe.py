"""Universe of perpetual futures (USDT-margined swaps on OKX, Bybit as fallback). Free public endpoints only, no key.
ONE tickers call gives price + 24h change + 24h volume for EVERY perpetual; candles are then fetched in parallel (rate-limited) only for the coins we trade/analyse
(top `max_coins` by 24h USD volume, above `min_vol_usd`). A coin that has an open position or an unfinished shadow trade is always kept, even if it fell out of the list.
Nothing here raises: a failure just means fewer coins this scan."""
import time, threading
import concurrent.futures as cf
import requests, pandas as pd
import engine as E

STABLES = {"USDC", "DAI", "TUSD", "FDUSD", "USDD", "USDP", "PYUSD", "EURI", "USDG", "USDE", "USTC"}
BY = "https://api.bybit.com/v5/market/"


def _okx_rows():
    d = E._get("market/tickers", instType="SWAP"); out = []
    for x in d:
        iid = x.get("instId", "")
        if not iid.endswith("-USDT-SWAP"): continue
        try:
            last = float(x["last"]); o24 = float(x.get("open24h") or last)
            out.append(dict(sym=iid[:-10], px=last, chg=round((last / o24 - 1) * 100, 2) if o24 else 0.0, vol=float(x.get("volCcy24h") or 0) * last))
        except Exception: continue
    return out


def _bybit_rows():
    r = requests.get(BY + "tickers", params=dict(category="linear"), timeout=20); r.raise_for_status(); out = []
    for x in r.json()["result"]["list"]:
        s = x.get("symbol", "")
        if not s.endswith("USDT"): continue
        try: out.append(dict(sym=s[:-4], px=float(x["lastPrice"]), chg=round(float(x.get("price24hPcnt") or 0) * 100, 2), vol=float(x.get("turnover24h") or 0)))
        except Exception: continue
    return out


def listing(max_coins=100, min_vol_usd=5e6):
    """[{sym, px, chg, vol}] sorted by 24h USD volume (BTC excluded: it has its own full pipeline)."""
    try: rows = _okx_rows()
    except Exception as e:
        print("universe okx error", type(e).__name__); rows = []
    if not rows:
        try: rows = _bybit_rows()
        except Exception as e: print("universe bybit error", type(e).__name__); return []
    rows = [r for r in rows if r["sym"] != "BTC" and r["sym"] not in STABLES and r["px"] > 0 and r["vol"] >= min_vol_usd]
    rows.sort(key=lambda r: -r["vol"]); return rows[:int(max_coins)]


class Coin(dict):
    """Per-coin candles. 'h15' (15m) is fetched only when something needs it (open position, a signal) to keep the number of requests low."""
    def __missing__(self, k):
        if k == "h15": self[k] = E.candles_sym(self["sym"], "15m", 300); return self[k]
        raise KeyError(k)


_lock = threading.Lock(); _last = [0.0]


def _paced(sym, bar, limit=300, gap=0.07):                       # ~14 requests/s overall: inside OKX's public limit
    with _lock:
        w = gap - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        _last[0] = time.time()
    return E.candles_sym(sym, bar, limit)


def fetch_h1(syms, budget_s=150, workers=6):
    """{sym: 1H DataFrame} for as many of `syms` as fit in the time budget (higher volume first)."""
    out, t0 = {}, time.time()
    if not syms: return out
    ex = cf.ThreadPoolExecutor(max_workers=workers)
    futs = {}
    try:
        for s in syms: futs[ex.submit(_paced, s, "1H")] = s
        for f in cf.as_completed(futs, timeout=budget_s):
            try: out[futs[f]] = f.result()
            except Exception: pass
    except cf.TimeoutError: print(f"universe: time budget hit, got {len(out)}/{len(syms)} coins")
    finally: ex.shutdown(wait=False, cancel_futures=True)
    return out


def indication(h1p, i):
    """Compact verdict for the home table: 7-method vote + how close the trend-pullback setup is. h1p = prepared 1H frame."""
    import methods as MT, paper
    m = MT.consensus(MT.votes(MT.prepare(h1p.reset_index(drop=True)), i)); r = paper.radar(h1p, i)
    return dict(verdict=m["verdict"], net=m["net"], long=m["long"], short=m["short"], total=m["total"], rb=sum(c[1] for c in r["LONG"]), rs=sum(c[1] for c in r["SHORT"]))
