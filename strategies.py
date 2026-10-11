"""Strategy registry. To add a strategy: write signal(env, cfg) -> dict | None, register it in SIGNALS, add its block in config.json."""
import datetime as dt
import backtest_v4 as W4

HIN = {"price near range low": "bhaav range ke sabse neeche (support ke paas) hai", "price near range high": "bhaav range ke upar (resistance ke paas) hai",
       "failed breakdown / liquidity sweep": "neeche tootne ki koshish fail hui (stop-loss hunt jaisa) aur bhaav wapas upar aaya",
       "failed breakout / sweep of highs": "upar nikalne ki koshish fail hui aur bhaav wapas neeche aaya",
       "higher low forming": "naya higher-low ban raha hai (bikri ka dabav ghat raha hai)", "lower high forming": "naya lower-high ban raha hai (kharidari kamzor)",
       "selling volume fading": "bechne wala volume ghat raha hai", "buying volume fading": "kharidne wala volume ghat raha hai",
       "volatility compression": "volatility sikud rahi hai (badi move se pehle ki shaanti)", "momentum turning up": "momentum upar mudne laga hai", "momentum turning down": "momentum neeche mudne laga hai",
       "price not at range edge (mid-range risk)": "bhaav range ke beech mein hai (risk zyada)", "no sweep of prior lows": "pichle lows ka sweep nahi hua", "no sweep of prior highs": "pichle highs ka sweep nahi hua",
       "no higher low yet": "higher-low abhi nahi bana", "no lower high yet": "lower-high abhi nahi bana", "selling volume not fading": "bechne ka volume abhi ghata nahi", "buying volume not fading": "kharidne ka volume abhi ghata nahi",
       "no compression": "volatility sikudi nahi", "momentum not turning": "momentum abhi palta nahi", "higher-timeframe regime against setup": "bade timeframe ka trend setup ke khilaaf hai"}
hin = lambda xs: [HIN.get(x, x) for x in xs]

def feat(h1, i, k):
    c = k * h1.c.values; hi = h1.h.values if k == 1 else -h1.l.values; a = float(h1.atr.iloc[i]); ts = dt.datetime.fromtimestamp(float(h1.ts.iloc[i]) / 1000, dt.timezone.utc)
    return dict(er4=round(float(h1.er4.iloc[i]), 3), atr_pct=round(a / float(h1.c.iloc[i]) * 100, 3), depth=round((float(hi[i - 23:i + 1].max()) - float(c[i])) / a, 2), hour=ts.hour, wd=ts.weekday())

def trend_pullback(env, sc):
    h1, i = env["h1"], env["i"]; Sg = {n: [] for n in ("trend_pullback", "breakout_retest", "squeeze_breakout", "slow_trend")}
    W4.side_sigs(h1, 1, Sg, i, i + 1); W4.side_sigs(h1, -1, Sg, i, i + 1)
    if not Sg["trend_pullback"]: return None
    k = Sg["trend_pullback"][0][1]; e = float(h1.c.iloc[i]); risk = sc["stop_atr"] * float(h1.atr.iloc[i]); M = env["S"].get("market") or {}
    ctx = dict(feat(h1, i, k), side_n=k, side="LONG" if k == 1 else "SHORT", funding=float(M.get("funding", 0)), regime=M.get("regime")); up = k == 1
    why = (f"Bade (4H) chart pe BTC ka trend {'upar' if up else 'neeche'} hai (taakat {ctx['er4']:.2f}, kam se kam 0.30 chahiye thi). Us trend ke beech bhaav thoda {'neeche gira' if up else 'upar chadha'} "
           f"({ctx['depth']:.1f} ATR ki halchal) aur ab trend ki taraf palat raha hai (pichli 1H candle trend ke saath band hui). Isliye trend ke saath {'BUY' if up else 'SELL'} liya. "
           f"Stop-loss {sc['stop_atr']}×ATR door rakha taaki chhoti uthal-puthal se na toote, target risk ka {sc['target_r']} guna. Backtest mein har 3 mein ~2 trade harte hain, isliye loss normal hai.")
    return dict(side=k, entry=e, sl=e - k * risk, tp=e + k * sc["target_r"] * risk, risk=risk, mode="fixed", ctx=ctx, why=why)

def early_signal(env, sc):
    r = env.get("scan")
    if not r or not r["signal"].startswith("EARLY") or r["score"] < sc["min_score"]: return None
    k = 1 if r["side"] == "LONG" else -1; e = float(r["entry"]); risk = abs(e - r["sl"])
    if risk <= 0: return None
    now, M, h1 = env["now"], env["S"].get("market") or {}, env["h1"]; a = float(h1.atr.iloc[-2] / h1.c.iloc[-2] * 100)
    ctx = dict(score=r["score"], regime=r["regime"], side_n=k, side=r["side"], hour=now.hour, wd=now.weekday(), funding=float(M.get("funding", 0)), atr_pct=round(a, 3))
    why = (f"Bhaav range ke {'neeche (support)' if k == 1 else 'upar (resistance)'} ke paas tha aur ye cheezein ek saath mili: " + "; ".join(hin(r["pro"])) + f". Setup score {r['score']}/100 (kam se kam {sc['min_score']} chahiye). "
           + ("Kamzor pehlu: " + "; ".join(hin(r["con"][:2])) + ". " if r["con"] else "") + "Ye 'early' signal hai (palatne se pehle pakadne ki koshish), isliye risk kam rakha aur aadha profit T1 par book hota hai. Iska pichla backtest record negative tha, to ise experiment samjho.")
    return dict(side=k, entry=e, sl=float(r["sl"]), t1=float(r["t1"]), t2=float(r["t2"]), t3=float(r["t3"]), tp=float(r["t2"]), risk=risk, mode="staged", ctx=ctx, why=why)

SIGNALS = {"trend_pullback": trend_pullback, "early_signal": early_signal}
