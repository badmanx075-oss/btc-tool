"""Ask the tool: type ANY question (Hinglish/English) in Telegram or the dashboard, get an analysed answer. NO API key, NO paid AI.
How it works: the question is matched to topics (direction in 5m..24h, market status, move size, support/resistance, 'will 90000 be touched',
trade idea, wallet/position/performance, risk, order flow, timing, how the tool works, and 40+ trading/stock-market terms).
Every number comes from the tool's own live state (state.json) and from long history stats (ask_stats.json, askstats.py).
Honest by design: if history shows no stable edge, the answer says '50-50, koi edge nahi' instead of inventing a direction."""
import re, math, datetime as dt
import numpy as np
import askstats as AS

HZS = sorted(AS.HZ)                                              # supported horizons in minutes
P_ = lambda x: f"${x:,.0f}"
INR = lambda x: ("-" if x < 0 else "") + f"₹{abs(x):,.0f}"
DIS = "⚠️ Ye history ke aadhaar par sambhavna hai, guarantee ya paisa-salah nahi. Tool sirf paper (nakli) trading karta hai."
EXAMPLES = ("Aise poochho:\n• 1 ghante me upar jayega ya neeche?\n• 5 min me kya hoga?\n• market kaisa hai?\n• abhi trade lena chahiye?\n• kya 90000 tak jayega aaj?\n• 1000 points move hoga kya?\n"
            "• support resistance kahan hai?\n• kab sabse zyada move hota hai?\n• mera wallet / meri position?\n• tool ka win rate kaisa hai?\n• stop loss kitna door rakhu?\n• RSI kya hai? / stop loss kya hota hai?\n• ye tool kaise kaam karta hai?")

# ---------------------------------------------------------------- glossary (plain Hinglish)
GLOSS = {
    "rsi": ("RSI", "RSI (0-100) batata hai ki bhaav kitni tezi se chadha ya gira. 70 ke upar 'garam' (overbought: girne ka risk), 30 ke neeche 'thanda' (oversold: uchhalne ka mauka). Tez trend mein RSI der tak 70 ke upar reh sakta hai, isliye ye akela signal nahi."),
    "macd": ("MACD", "MACD do moving average ka fark hai. Histogram upar badh raha ho to upar ka momentum, neeche ja raha ho to neeche ka. Trend ki taakat dekhne ke kaam aata hai."),
    "ema|moving average|ma": ("Moving Average (EMA)", "Pichhle kuch candles ka average bhaav. Bhaav EMA ke upar ho to trend upar, neeche ho to neeche. Tool EMA20, 50, 200 dekhta hai."),
    "bollinger|bands": ("Bollinger Bands", "Average ke upar-neeche 2 standard deviation ke band. Band tang ho (squeeze) to bada move aa sakta hai. Bhaav band ke bahar ho to ya breakout ya mean-reversion, saath ka RSI/volume batata hai."),
    "atr": ("ATR", "Average True Range: ek candle mein bhaav average kitna hilta hai. Stop-loss aur target ki doori tay karne ke kaam aata hai (jaise stop 2 ATR door)."),
    "volume": ("Volume", "Kitna maal bika-khareeda gaya. Breakout ke saath zyada volume matlab move mein dum hai; kam volume ka breakout aksar fail hota hai."),
    "support": ("Support", "Neeche ka wo level jahan se bhaav pehle kai baar uchhla hai (khareedar aate hain). Toot jaye to aksar aur neeche ka raasta khulta hai."),
    "resistance": ("Resistance", "Upar ka wo level jahan se bhaav pehle kai baar palta hai (bechne wale aate hain). Upar band ho jaye to aksar aage badhta hai."),
    "breakout": ("Breakout", "Bhaav kisi range ya resistance ke bahar nikalna. Asli breakout mein candle mazboot band hoti hai aur volume badhta hai."),
    "fakeout|false breakout|stop hunt|liquidity sweep": ("Fakeout / Sweep", "Bhaav level todta lagta hai, phir turant wapas aa jata hai (stop-loss uda kar). Isliye tool candle BAND hone ka intezaar karta hai."),
    "stop loss|stoploss|sl": ("Stop-loss", "Pehle se tay wo bhaav jahan galat sabit hone par trade kat jata hai, taaki nuksaan chhota rahe. Bina stop ke trade sabse badi galti hai. Tool har trade mein stop lagata hai."),
    "target|take profit|tp": ("Target", "Wo bhaav jahan munafa book kiya jata hai. Tool target risk ka kai guna (jaise 2R ya 4R) rakhta hai."),
    "r multiple|risk reward|rr|1r|2r": ("R multiple / Risk-Reward", "1R = ek trade mein jitna risk liya (entry se stop tak). +2R matlab risk ka 2 guna munafa. Tool saare nateeje R mein naapta hai taaki alag size ke trade barabar tulna hon."),
    "leverage": ("Leverage", "Chhoti margin se bada position. 3x leverage mein 100 ke margin se 300 ka position. Munafa aur nuksaan dono badhte hain, liquidation ka risk bhi."),
    "margin": ("Margin", "Position kholne ke liye jama kiya gaya paisa (guarantee jaisa). Position band hone par wapas milta hai."),
    "liquidation": ("Liquidation", "Nuksaan itna badh jaye ki margin khatam ho jaye to exchange position zabardasti band kar deta hai. Stop-loss aur chhota leverage isse bachate hain."),
    "perpetual|perp|futures|future": ("Perpetual futures", "Bina expiry wala contract jisme bhaav spot ke paas rakhne ke liye funding rate chalta hai. Long aur short dono lena aasan."),
    "funding": ("Funding rate", "Perpetual mein longs aur shorts ke beech chalne wali chhoti fees. Funding bahut positive ho to longs ki bheed (girne ka risk), bahut negative ho to shorts ki bheed."),
    "open interest|oi": ("Open Interest", "Kitne contract abhi khule hain. Bhaav + OI saath badhe to naye longs aaye; bhaav girte OI badhe to naye shorts. OI achanak ghate to positions band ho rahi hain."),
    "long": ("Long / Buy", "Ye soch kar khareedna ki bhaav upar jayega. Upar gaya to munafa."),
    "short": ("Short / Sell", "Ye soch kar bechna ki bhaav neeche jayega; neeche gaya to munafa (upar gaya to nuksaan)."),
    "bull|bullish|bull market": ("Bullish / Bull market", "Upar ka rujhaan ya upar ki ummeed. Bear/Bearish = neeche ka rujhaan."),
    "bear|bearish|bear market": ("Bearish / Bear market", "Neeche ka rujhaan ya neeche ki ummeed."),
    "candlestick|candle": ("Candlestick", "Ek candle ek time-frame ka open, high, low, close dikhati hai. Body bada = zor, lambi wick = us taraf se rejection."),
    "doji": ("Doji", "Open aur close lagbhag barabar, chhoti body: market confuse hai, agla move level par nirbhar."),
    "engulfing": ("Engulfing", "Bada candle pichhle chhote candle ko poora nigal le: palatne ka sanket (support/resistance ke paas zyada bharosemand)."),
    "hammer|pin bar|shooting star": ("Hammer / Pin bar", "Lambi wick wali chhoti body: wahan se tez rejection. Support par neeche ki lambi wick = bounce, resistance par upar ki lambi wick = girawat ka sanket."),
    "trend": ("Trend", "Bhaav ka mukhya rukh: upar (higher highs, higher lows) ya neeche (lower highs, lower lows). 'Trend is your friend': trend ke saath trade aksar aasan."),
    "range|sideways": ("Range / Sideways", "Bhaav ek upar-neeche ki patti mein ghoomta hai, koi saaf trend nahi. Yahan breakout ka intezaar ya edge par palatna chalta hai."),
    "volatility|volatile": ("Volatility", "Bhaav kitna zyada hilta hai. Zyada volatility = bade mauke par bade jhatke bhi."),
    "order flow|orderflow|taker|delta|aggressive": ("Order flow", "Kaun zyada aakramak hai: market order se khareedne wale (buy taker) ya bechne wale (sell taker). Buy taker zyada = khareedaron ka dabaav, par ye akela signal nahi."),
    "paper trading|paper": ("Paper trading", "Nakli paise se asli bhaav par practice. Is tool ka wallet nakli hai (₹20,000 virtual); koi asli order nahi lagta."),
    "drawdown": ("Drawdown", "Peak se neeche kitna gir gaye. Max drawdown batata hai ki strategy mein sabse bura daur kitna gehra tha."),
    "win rate|winrate": ("Win rate", "Kitne % trade jeete. Akela kaafi nahi: 40% win rate bhi munafe wala ho sakta hai agar jeet haar se badi ho (jaise 2R vs 1R)."),
    "backtest": ("Backtest", "Strategy ko purane data par chala kar dekhna ki pehle kaisi chalti. Achha backtest bhi future ki guarantee nahi; tool kam sample ko 'NOT PROVEN' bolta hai."),
    "slippage|spread|fees": ("Slippage / Fees", "Order ka asli bhaav dikhe bhaav se thoda alag ho sakta hai (slippage) aur har trade par fees lagti hai. Chhote target mein ye munafa kha jate hain; tool fees ginta hai."),
    "pullback": ("Pullback", "Trend ke beech chhota ulta move (jaise uptrend mein thoda girna). Trend-pullback strategy wahan se trend ki taraf wapas jaane par entry leti hai."),
    "confluence": ("Confluence", "Kai alag tareeke/levels ka ek hi nateeje par aana. Jitne zyada alag sanket ek taraf, utna bharosa (par guarantee nahi)."),
    "divergence": ("Divergence", "Bhaav naya high bana raha par RSI/MACD nahi (bearish) ya ulta (bullish): trend kamzor padne ka sanket."),
    "fibonacci|fib": ("Fibonacci", "Move ke 38.2%, 50%, 61.8% wapsi ke levels jahan pullback aksar rukta hai. Ek support/resistance ka tareeka."),
    "vwap": ("VWAP", "Volume-weighted average price: din ka 'sahi' average bhaav. Upar ho to khareedar haavi, neeche ho to bechne wale."),
    "stock|share|equity|shares": ("Stock / Share", "Kisi company ka hissa. Bhaav company ki kamai, khabar aur mang-aapurti se badalta hai. Ye tool stock nahi, sirf BTC perpetual track karta hai."),
    "nifty|sensex|banknifty": ("Nifty / Sensex", "Nifty 50 aur Sensex bharat ke bade shares ke index hain (market ka mizaaj). Is tool mein inka live data nahi, sirf BTC hai."),
    "intraday|delivery": ("Intraday vs Delivery", "Intraday: usi din khareed kar bech dena. Delivery: share rakh lena (demat mein aa jata hai). Alag charges aur risk."),
    "option|options|call|put|f&o|fno": ("Options / F&O", "Option mein ek tay bhaav par khareedne/bechne ka haq milta hai: Call = upar ka daav, Put = neeche ka. Time ke saath value ghatti hai, risk zyada. Ye tool options nahi karta."),
    "demat": ("Demat account", "Shares ko electronic roop mein rakhne wala khata, bank account jaisa par shares ke liye."),
    "ipo": ("IPO", "Company pehli baar shares janta ko bechti hai. Listing par bhaav upar ya neeche kuch bhi ho sakta hai."),
    "dividend": ("Dividend", "Company ke munafe ka wo hissa jo shareholders ko milta hai."),
    "pe ratio|p/e|pe": ("P/E ratio", "Share ka bhaav / company ki kamai per share. Bahut zyada P/E = mehnga (ya tez growth ki ummeed)."),
    "sip|mutual fund": ("SIP / Mutual fund", "Mutual fund mein har mahine tay rakam lagana SIP kehlata hai. Lambi avadhi ka tareeka; trading se alag."),
}


def _gloss_find(n):
    best = None
    for keys, v in GLOSS.items():
        for k in keys.split("|"):
            if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", n) and (best is None or len(k) > best[0]): best = (len(k), v)
    return best[1] if best else None


# ---------------------------------------------------------------- question understanding
def _norm(q): return " " + re.sub(r"[^\w\s$.,%₹/&+-]", " ", q.lower()).replace("‌", "") + " "
def _has(n, pat): return re.search(pat, n) is not None


def horizon_of(n):
    """-> minutes (one of HZS) or None. Understands '5 min', '1h', '2 ghante', 'aaj', 'ek ghante', 'aadha ghanta'."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-\s*\d+\s*)?(?:m|min|mins|minute|minutes|minat|mnt)(?!\w)", n)
    if m: return _near(float(m.group(1)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-\s*\d+\s*)?(?:h|hr|hrs|hour|hours|ghanta|ghante|ghanton|gante)(?!\w)", n)
    if m: return _near(float(m.group(1)) * 60)
    if _has(n, r"(aadha|adha|half)\s*(ghant|hour|hr)"): return 30
    if _has(n, r"(?<!\w)(ek|one)\s*(ghant|hour|hr)"): return 60
    if _has(n, r"(?<!\w)(do|two)\s*(ghant|hour|hr)"): return 120
    if _has(n, r"(?<!\w)(char|four)\s*(ghant|hour|hr)"): return 240
    if _has(n, r"(aaj|today|din|day|kal|tomorrow|24\s*h|raat tak|shaam tak)"): return 1440
    return None


def _near(m):
    m = max(m, 1.0); return min(HZS, key=lambda h: abs(math.log(h / m)))


def prices_in(n, px):
    """Price targets mentioned (84000, 84,500, 90k). Plausible only (0.4x..2.5x of price)."""
    out = []
    for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d{4,6})(?:\.\d+)?(?!\d)(?!\s*(?:pts|points?|point|min|h\b|hr|ghant))", n): out.append(float(m.group(1).replace(",", "")))
    for m in re.finditer(r"(?<![\w.])(\d{2,3}(?:\.\d)?)\s?k(?!\w)", n): out.append(float(m.group(1)) * 1000)
    return [x for x in out if px and 0.4 * px <= x <= 2.5 * px][:2]


def points_in(n):
    m = re.search(r"(\d[\d,]*)\s*(?:pts|points?|point|poin)", n)
    return float(m.group(1).replace(",", "")) if m else None


OTHER = r"(?<!\w)(nifty|sensex|banknifty|reliance|tcs|infosys|hdfc|adani|tata|nasdaq|s&p|sp500|dow|gold|silver|crude|eth|ethereum|solana|sol|xrp|doge|bnb|usd|dollar|forex|eurusd)(?!\w)"
INTENTS = [
    ("accuracy", r"(ye|iska|tera|tumhara|ask|jawab|forecast|andaza|andaaz).{0,30}(sahi|accura|bharos|kitna sach|hit rate)|accuracy|kitne sahi"),
    ("direction", r"(?<!\w)(up|down|upar|oopar|ooper|neeche|niche|girega|girne|gir|badhega|badhne|badh|tutega|toot|jayega|jaega|jaayega|jayegi|chadhega|chadh|bullish|bearish|pump|dump|crash|rally|direction|taraf|kidhar|kahan jayega|kaha jayega|predict|forecast|expect|sambhavna|probability|chance|kya hoga|kya hone|what will|aage kya|next kya|ऊपर|नीचे)(?!\w)"),
    ("size", r"(?<!\w)(points?|pts|range|kitna move|kitne move|move size|hilega|swing|movement|kitna ja|kitna chal)(?!\w)"),
    ("market", r"(market|bazaar|bazar).{0,25}(kaisa|kaisi|haal|halat|chal|status|mood|dikh|kya)|(?<!\w)(halat|haal|situation|overview|summary|sentiment|analysis|analyze|analyse|regime|abhi kya)(?!\w)"),
    ("advice", r"(trade|entry|enter|position)\s*(le|lu|lun|lena|leni|kar|karu|karun|open)|(?<!\w)(should i|kya karu|lena chahiye|lu kya|buy karu|sell karu|long karu|short karu|entry kab|kab (lu|lun|kharid|bech)|safe hai|long ya short|buy ya sell|long or short|buy or sell|trade chahiye)(?!\w)"),
    ("levels", r"(?<!\w)(support|resistance|levels?|sr|rukega|atkega|zone|barrier|ceiling|floor)(?!\w)|kahan (ruk|atk)|kaha (ruk|atk)"),
    ("position", r"(meri|mera|my|abhi wali|open)\s*.{0,10}(position|trade)|(?<!\w)(pnl|p/l)(?!\w)|chal raha trade"),
    ("wallet", r"(?<!\w)(wallet|balance|paisa|paise|rupee|rupees|₹|inr|capital|kamaya|kamai|equity|funds?)(?!\w)"),
    ("performance", r"(win\s*rate|winrate|stats?|statistics|performance|kitne trade|kitne jeete|edge|strategy.{0,12}(kaisi|kaisa|chal|result)|results?)"),
    ("flow", r"(order\s*flow|orderflow|buyers?|sellers?|aggressive|aggression|taker|delta|kaun (haavi|jyada)|dabaav|dabav|khareedar|bechne wale)"),
    ("dailyhist", r"(pichhle|pichle|last|past)\s*\d+\s*(din|days?|hafte|weeks?|mahine|months?)|(hafte|week|mahine|month)\s*(ka|me|mein|ke)|average range|avg range|weekday|kis din|konsa din|somvar|mangalvar|budhvar|guruvar|shukravar|shanivar|ravivar|monday|tuesday|wednesday|thursday|friday|saturday|sunday|archive|saved|record|streak|sabse bada din|din ka high|din ka low|history (dikha|batao|save)"),
    ("daily", r"(kal|yesterday|pichhle din|pichle din|last day|daily|din (bhar|me|mein)|ek din|1 din|ek din me).{0,40}(kitna|kitne|move|gaya|gira|badha|range|points?|pts|%|percent|percentage)|(kitna|kitne).{0,30}(kal|din|daily)|(?<!\w)(daily range|din ka range|day range|roz)(?!\w)"),
    ("timing", r"(?<!\w)(kab|kis (samay|time|waqt)|best time|konsa (time|samay)|session|active (window|time|hour)|peak hour|volatile (time|hour|samay)|trading hours?)(?!\w)"),
    ("radar", r"(radar|good move|achha move|accha move|move aane|move coming|big move|bada move)"),
    ("stoploss", r"(stop\s*loss|stoploss|(?<!\w)sl(?!\w)).{0,30}(kitna|kitne|kahan|kaha|door|rakhu|rakhun|lagau|lagaun|lagana|rakhna|set|points?|pts|kaise|decide|tay|guide|suggest)|(kitna|kitne|kahan|kaha).{0,20}(stop\s*loss|stoploss|(?<!\w)sl(?!\w))"),
    ("risk", r"(?<!\w)(risk|leverage|position size|drawdown|loss limit|daily loss|kitna lagau|kitna lagana|kitna invest)(?!\w)"),
    ("tool", r"(?<!\w)(tool|bot|system|strateg\w*|confluence|early signal|pullback|kaise (kaam|chalta|chal)|how (does|do)|kya karta|kya kar raha|health|working|alive|delay|last scan|smart exit)(?!\w)"),
]
GLOSS_Q = r"(kya hai|kya hota|kya hoti|kya hote|kise kehte|meaning|matlab|explain|what is|what are|samjhao|samjha|define|difference|farak|batao.{0,12}(kya|about))"


SEM = {"direction": ["upar jayega ya neeche", "market girega ya badhega", "agle ghante direction kya hogi", "bitcoin upar ya niche jayega", "price badhega kya", "market tutega kya", "kya hoga aage"],
       "market": ["market kaisa hai", "abhi halat kya hai", "bazaar ka mood kaisa", "current situation batao", "overall analysis do"],
       "stoploss": ["stop loss kitna rakhu", "sl kahan lagau", "stop kitna door rakhna chahiye", "stoploss kitne points"],
       "advice": ["abhi trade lu kya", "entry lena chahiye", "buy karu ya sell", "long ya short lu"],
       "levels": ["support resistance kahan hai", "kaunsa level important hai", "price kahan rukega"],
       "daily": ["kal kitna move hua", "kal ka high low kya tha", "pichhle din kitna upar neeche gaya"],
       "size": ["kitna move ho sakta hai", "kitne points hilega", "range kitni hogi"],
       "performance": ["tool ka win rate", "kitne trade jeete", "strategy kaisi chal rahi hai"],
       "wallet": ["mera wallet kitna hai", "balance kitna bacha", "kitna paisa kamaya"],
       "position": ["meri position kaisi hai", "mera trade abhi kaisa chal raha hai", "open trade ka pnl"],
       "flow": ["buyers ya sellers kaun zyada", "order flow kaisa hai", "aggressive buying chal rahi hai kya"],
       "timing": ["kab sabse zyada move hota hai", "kis time market active rehta hai", "best trading time"],
       "tool": ["tool kaise kaam karta hai", "ye bot kya karta hai", "kaunsi strategy chal rahi hai"]}
_SEM = {}


def _grams(s):
    s = " " + re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", s.lower())).strip() + " "; c = {}
    for i in range(len(s) - 2): c[s[i:i + 3]] = c.get(s[i:i + 3], 0) + 1
    return c


def _semantic(n, thr=0.42):
    """Typo-tolerant intent guess: character-3-gram TF-IDF cosine against example questions (no API, no model download)."""
    if not _SEM:
        docs = [(k, _grams(e)) for k, v in SEM.items() for e in v]; df = {}
        for _, g in docs:
            for t in g: df[t] = df.get(t, 0) + 1
        idf = {t: math.log(1 + len(docs) / c) for t, c in df.items()}; _SEM.update(docs=docs, idf=idf)
    idf = _SEM["idf"]; qg = _grams(n); vec = lambda g: {t: c * idf.get(t, 1.0) for t, c in g.items()}; nq = vec(qg); nrm = lambda v: math.sqrt(sum(x * x for x in v.values())) or 1.0; qn = nrm(nq); best = (0.0, None)
    for k, g in _SEM["docs"]:
        v = vec(g); s = sum(x * v.get(t, 0) for t, x in nq.items()) / (qn * nrm(v))
        if s > best[0]: best = (s, k)
    return best[1] if best[0] >= thr else None


def understand(q, S):
    n = _norm(q); px = (S or {}).get("last_price"); hz = horizon_of(n); hit = [k for k, pat in INTENTS if _has(n, pat)]; g = _gloss_find(n)
    pr = prices_in(n, px); pts = points_in(n)
    if _has(n, r"(?<!\w)(hi|hello|hey|namaste|hii+|help|menu)(?!\w)") and len(n.split()) <= 3 and not hit: return dict(n=n, hz=hz, intents=["hello"], gloss=g, prices=pr, pts=pts)
    if g and _has(n, GLOSS_Q): return dict(n=n, hz=hz, intents=["glossary"], gloss=g, prices=pr, pts=pts)
    out = []
    if "accuracy" in hit: out.append("accuracy")
    if (pr or pts) and _has(n, r"(tak|touch|reach|cross|pahunch|pahuch|hit|jayega|jaega|tutega|toot|break|upar|neeche|up|down|agar|if|hoga|ho jayega|chhu|chu)"): out.append("target")
    for k in ("dailyhist", "daily", "stoploss", "direction", "size", "market", "advice", "levels", "position", "wallet", "performance", "flow", "timing", "radar", "risk", "tool"):
        if k in hit and not (k == "size" and ("direction" in out or "target" in out)) and not (k == "market" and "direction" in out): out.append(k)
    if "daily" in out and not _has(n, r"(hoga|hogi|jayega|jaega|jayegi|will|expect|aaj|aane wale|aage|next)"): out = [x for x in out if x not in ("direction", "size", "market")]
    if "dailyhist" in out: out = [x for x in out if x not in ("daily", "direction", "size", "market", "timing")]
    if "target" in out: out = [x for x in out if x != "direction"]
    if "performance" in out: out = [x for x in out if x != "tool"]
    if "stoploss" in out: out = [x for x in out if x not in ("risk", "advice", "size", "direction", "market")]
    if "risk" in out and "advice" in out and not _has(n, r"(trade|entry|buy|sell|long|short)"): out = [x for x in out if x != "advice"]
    if _has(n, OTHER) and not _has(n, r"(btc|bitcoin)"): out = ["other"] + (["glossary"] if g and False else [])
    ctx = (S or {}).get("ask_ctx") or {}; fresh = False
    try: fresh = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ctx["ts"])).total_seconds() < 900
    except Exception: pass
    follow = _has(n, r"(?<!\w)(aur|phir|and|also|same|isi|uska|iska|us ke|us ka|ye wala|aur kya|ab|then)(?!\w)") or (hz is not None and len(n.split()) <= 5)
    if not out and fresh and follow and ctx.get("intents"):                              # follow-up like 'aur 4 ghante me?' keeps the previous topic
        out = [x for x in ctx["intents"] if x in ("direction", "size", "stoploss", "target", "market", "advice")][:2] or []
        if hz is None: hz = ctx.get("hz")
    if not out and hz: out.append("direction")
    if not out and g: out.append("glossary")
    if not out and _has(n, OTHER): out.append("other")
    if not out:                                                                           # typo-tolerant fallback: text similarity with example questions
        s_ = _semantic(n)
        if s_: out.append(s_)
    return dict(n=n, hz=hz, intents=out[:3], gloss=g, prices=pr, pts=pts)


# ---------------------------------------------------------------- live-state helpers
def _live(S, frame):
    L = (S.get("ask_state") or {}).get(frame)
    if L: return L
    m = (S.get("paper") or {}).get("methods") or {}
    if frame == "1H" and m.get("net") is not None:
        px = S.get("last_price") or m.get("price"); a = (S.get("market") or {}).get("atr1h")
        return dict(net=m["net"], bucket=AS.bucket(m["net"]), atr_pct=(a / px * 100 if a and px else None), price=px, votes=[[v["name"], v["dir"], v["why"]] for v in m.get("votes", [])], rsi=None)
    return None


def _vol_bucket(blk_frame, atr_pct):
    if atr_pct is None or not blk_frame: return None
    e1, e2 = blk_frame["vol_edges"]; return int(atr_pct > e1) + int(atr_pct > e2)


def edge_of(b, base, H):
    """Is this bucket's P(up) really different from the normal base rate? Uses effective sample = n / horizon (overlapping windows), and needs both halves of history to agree."""
    n_eff = max(b["n"] / max(H, 1), 1); p, q = b["p_up"], base["p_up"]; z = (p - q) / math.sqrt(max(q * (1 - q), 1e-6) / n_eff)
    st = b.get("p1") is not None and b.get("p2") is not None and (b["p1"] - base["p1"]) * (b["p2"] - base["p2"]) > 0 and min(abs(b["p1"] - base["p1"]), abs(b["p2"] - base["p2"])) >= 0.01
    big = abs(p - q) >= 0.02
    lab = "STABLE jhukaav" if abs(z) >= 3 and st and big else "halka jhukaav (pakka nahi)" if abs(z) >= 2 and st and big else "koi saaf edge nahi (lagbhag sikke jaisa)"
    return round(z, 1), st, lab


def _block(stats, m):
    fr, bars = AS.HZ[m]; F = ((stats or {}).get("frames") or {}).get(fr)
    return fr, F, (F or {}).get("H", {}).get(str(bars))


def _days(F): return max(int((F["to"] - F["from"]) / 86400000), 1) if F and F.get("from") else 0


def one_horizon(S, stats, m, px):
    """Facts for ONE horizon -> dict (or dict with 'err')."""
    fr, F, blk = _block(stats, m); L = _live(S, fr)
    if not blk or not L: return dict(m=m, err=("History stats abhi bani nahi (scanner ka agla run, ya research workflow, ke baad aa jayengi)." if not blk else f"{fr} candle ka live data abhi state mein nahi (agle scan ke baad)."))
    k = L["bucket"]; b = blk["by_net"].get(str(k)); base = blk["base"]; vb = _vol_bucket(F, L.get("atr_pct")); V = blk["by_vol"].get(str(vb)) if vb is not None else None
    z, st, lab = (edge_of(b, base, blk["h_bars"]) if b else (0.0, False, "is halat ke liye history mein kam cases (sample kam)"))
    p = b["p_up"] if b else base["p_up"]; used_edge = bool(b) and not lab.startswith("koi")
    return dict(m=m, fr=fr, k=k, net=L["net"], n=(b or {}).get("n", 0), p=p, base=base["p_up"], z=z, stable=st, label=lab, lean_ok=used_edge, vb=vb, V=V, days=_days(F), px=px)


def lean_line(o):
    pu = o["p"] * 100
    if o["lean_ok"]: return f"Jhukaav: {'UPAR' if o['p'] > o['base'] else 'NEECHE'} (upar {pu:.0f}% / neeche {100 - pu:.0f}%), par {o['label']}."
    return f"Nateeja: upar {o['base'] * 100:.0f}% / neeche {100 - o['base'] * 100:.0f}%, yaani {o['label']}. Seedha 'upar' ya 'neeche' bolna jhooth hoga."


def move_line(o):
    V = o.get("V"); px = o["px"]
    if not V: return ""
    a = V["absq"]; pt = lambda x: f"{x / 100 * px:,.0f}"
    return (f"Move size ({AS.VNAME[o['vb']]} volatility ke hisaab se): aksar ±{pt(a[1])} pts; 4 mein se 1 baar {pt(a[2])}+ pts; 10 mein se 1 baar {pt(a[3])}+ pts.\n"
            f"Is dauraan beech mein upar tak aksar +{pt(V['upq'][0])} pts aur neeche tak -{pt(V['dnq'][0])} pts (touch) jaata hai.")


def _levels_hint(S):
    R = (S.get("sr") or {}).get("tf") or {}; v = R.get("1H") or R.get("4H") or R.get("15m") or {}
    sup = (v.get("supports") or [None])[0]; res = (v.get("resistances") or [None])[0]; out = []
    if res: out.append(f"Upar ka jhukaav tab mazboot jab 1H candle {P_(res['price'])} ke upar BAND ho")
    if sup: out.append(f"neeche ka tab jab 1H candle {P_(sup['price'])} ke neeche band ho")
    return ("🔁 Raay kab badlegi: " + "; ".join(out) + ".") if out else ""


# ---------------------------------------------------------------- sections
def sec_market(S, stats, short=False):
    M, A, P = S.get("market") or {}, S.get("analysis") or {}, S.get("paper") or {}; px = S.get("last_price"); L = []
    if not px: return "Market data abhi state mein nahi (scanner ka pehla run chalne do)."
    L.append(f"📍 BTC {P_(px)} | Regime: {A.get('regime') or M.get('regime', '?')} | {A.get('stage', '')} | {A.get('status', M.get('signal', ''))}")
    one = _live(S, "1H")
    if one:
        word = AS.BNAME[one["bucket"]]; L.append(f"🧩 7 tareeke ka vote (1H): {word} (net {one['net']:+.0f})")
        for nm, d, why in [v for v in one["votes"] if v[1] != 0][:4 if not short else 2]: L.append(f"   {'🟢' if d == 1 else '🔴'} {nm}: {why}")
        if one.get("rsi") is not None: L.append(f"📈 RSI(1H) {one['rsi']:.0f}")
        F = ((stats or {}).get("frames") or {}).get("1H"); vb = _vol_bucket(F, one.get("atr_pct"))
        if vb is not None: L.append(f"🌊 Volatility abhi: {AS.VNAME[vb]} (ATR {one['atr_pct']:.2f}% per ghanta)")
    of = (S.get("orderflow") or {}).get("now") or {}
    if of.get("state") and of["state"] != "NO DATA": L.append(f"🛒 Order flow (60 min): {of['state']} (delta {of['ratio'] * 100:+.0f}%, bade orders {of['big_share'] * 100:.0f}%)")
    rm = P.get("radar_move")
    if rm: L.append(f"🚀 Move radar: {rm['score']}/100 ({rm['state']})")
    T = S.get("timing")
    if T: L.append(f"🕒 Abhi {T['ist']} IST: activity {T['cls']} (typical range {T['avg_range']:,.0f} pts per ghanta)")
    if M.get("funding") is not None: fr = M["funding"] * 100; L.append(f"💸 Funding {fr:.4f}% ({'longs ki bheed' if fr > 0.03 else 'shorts ki bheed' if fr < -0.03 else 'balanced'})")
    return "\n".join(L)


def sec_direction(S, stats, hz, log):
    px = S.get("last_price")
    if not px: return "Market data abhi state mein nahi."
    L = [sec_market(S, stats, short=True), ""]
    if hz:
        o = one_horizon(S, stats, hz, px)
        if o.get("err"): return "\n".join(L) + o["err"]
        L += [f"🎯 {AS.HZ_NAME[hz].upper()} KA ANDAAZA", f"Is jaisi halat ({AS.BNAME[o['k']]}) ke baad pichhle {o['days']} din ki history mein ({o['n']} cases): upar {o['p'] * 100:.0f}% | neeche {100 - o['p'] * 100:.0f}%.",
              f"Normal din (koi bhi halat): upar {o['base'] * 100:.0f}% | neeche {100 - o['base'] * 100:.0f}%.", lean_line(o), move_line(o)]
        if log: _log(S, hz, o["p"], px)
        extra = [m for m in (15, 60, 240) if m != hz]
    else:
        L.append("🎯 ALAG-ALAG SAMAY KA ANDAAZA (history ke hisaab se)")
        extra = [5, 15, 30, 60, 240, 1440]
    for m in extra:
        o = one_horizon(S, stats, m, px)
        if o.get("err"): continue
        V = o.get("V"); mv = f", typical ±{V['absq'][1] / 100 * px:,.0f} pts" if V else ""
        L.append(f"• {AS.HZ_NAME[m]}: upar {(o['p'] if o['lean_ok'] else o['base']) * 100:.0f}% / neeche {100 - (o['p'] if o['lean_ok'] else o['base']) * 100:.0f}% ({'jhukaav ' + ('upar' if o['p'] > o['base'] else 'neeche') if o['lean_ok'] else 'koi edge nahi'}){mv}")
        if log and not hz and m == 60: _log(S, 60, o["p"], px)
    an = sec_analog(S, hz)
    if an: L += ["", an]
    h = _levels_hint(S)
    if h: L += ["", h]
    return "\n".join(x for x in L if x is not None)


def _log(S, m, p, px):
    try:
        now = dt.datetime.now(dt.timezone.utc); lg = S.setdefault("ask_log", [])
        if any(e["h"] == m and (now - dt.datetime.fromisoformat(e["ts"])).total_seconds() < 600 for e in lg[-20:]): return
        lg.append(dict(ts=now.isoformat(timespec="seconds"), due=(now + dt.timedelta(minutes=m)).isoformat(timespec="seconds"), h=m, p_up=round(float(p), 4), px0=float(px), done=False))
    except Exception: pass


def sec_size(S, stats, hz):
    px = S.get("last_price"); L = ["📏 KITNA MOVE HO SAKTA HAI (history ke hisaab se, abhi ki volatility par)"]
    for m in ([hz] if hz else [15, 60, 240, 1440]):
        o = one_horizon(S, stats, m, px)
        if o.get("err") or not o.get("V"): continue
        L.append(f"{AS.HZ_NAME[m]}:\n" + move_line(o))
    T = S.get("timing")
    if T and T.get("next_high"): n = T["next_high"]; L.append(f"⏰ Agla active window: {n['ist']} IST ({n['in_min']} min baad), typical range {n['avg_range']:,.0f} pts.")
    an = sec_analog(S, hz)
    if an: L += ["", an]
    return "\n".join(L) if len(L) > 1 else "Move-size stats abhi bani nahi."


def _interp(grid, arr, x):
    if x <= grid[0]: return 1.0
    if x >= grid[-1]: return None
    return float(np.interp(x, grid, arr))


def sec_target(S, stats, prices, pts, n):
    px = S.get("last_price"); L = []; grid = AS.GRID
    goals = [(t, (t - px) / px * 100) for t in prices] if prices else ([(None, pts / px * 100), (None, -pts / px * 100)] if pts else [])
    if pts and not prices and _has(n, r"(?<!\w)(upar|up|badh|chadh)(?!\w)") and not _has(n, r"(?<!\w)(neeche|niche|down|gir|toot)(?!\w)"): goals = goals[:1]
    if pts and not prices and _has(n, r"(?<!\w)(neeche|niche|down|gir|toot)(?!\w)") and not _has(n, r"(?<!\w)(upar|up|badh|chadh)(?!\w)"): goals = goals[1:]
    if not goals: return "Kaunsa level ya kitne points? Jaise: 'kya 90000 tak jayega?' ya '1000 points neeche jayega?'"
    L.append(f"🎯 LEVEL TAK PAHUNCHNE KI SAMBHAVNA (BTC {P_(px)})")
    for t, pc in goals[:2]:
        side = "up" if pc > 0 else "dn"; dist = abs(pc); L.append(f"\n{(P_(t) + ' ') if t else ''}{'upar' if pc > 0 else 'neeche'} {abs(pc / 100 * px):,.0f} pts ({dist:.2f}%) door:")
        for m in (30, 60, 240, 1440):
            fr, F, blk = _block(stats, m); L_ = _live(S, fr)
            if not blk or not L_: continue
            vb = _vol_bucket(F, L_.get("atr_pct")); V = blk["by_vol"].get(str(vb)) if vb is not None else None
            if not V: continue
            p = _interp(grid, V[side], dist)
            L.append(f"  {AS.HZ_NAME[m]} mein kabhi chhu lega (touch): " + ("lagbhag pakka (bahut paas)" if p is not None and p >= 0.99 else "<1% (history mein bahut kam)" if p is None else f"{p * 100:.0f}%"))
    L.append("(Touch = beech mein ek baar bhi chhoo le. Us par TIKNA ya band hona alag aur kam sambhavna hai. Ye abhi ki volatility wale dinon ki history hai, direction ki bhavishyavani nahi.)")
    return "\n".join(L)


def sec_advice(S, stats, hz, cfg):
    A, P = S.get("analysis") or {}, S.get("paper") or {}; M = P.get("methods") or {}; px = S.get("last_price"); L = ["🧭 KYA TRADE LENA CHAHIYE? (tool ka nazariya, paisa-salah nahi)"]
    pos = [t for t in (P.get("pos") or {}).values() if t]
    L.append(f"Tool ka status: {A.get('status', (S.get('market') or {}).get('signal', 'n/a'))}")
    if M.get("votes"): L.append(f"Tareeke: {M['verdict']} (LONG {M['long']} / SHORT {M['short']} of {M['total']}, net {M['net']:+.0f}). Trade tab khulta hai jab kam se kam {cfg_need(cfg)} tareeke ek taraf hon.")
    if pos: L.append(f"Abhi {len(pos)} paper position khuli hai (dekho: 'meri position').")
    lv = A.get("levels")
    if lv: L.append(f"Setup ke levels: entry zone {P_(lv['early_zone'][0])}-{P_(lv['early_zone'][1])}, stop {P_(lv['preferred_sl'])}, T1 {P_(lv['t1'])}. Late entry (peechha karna) {P_(lv['late_above'])} ke baad.")
    rad = P.get("radar") or {}
    for side, nm in (("LONG", "BUY"), ("SHORT", "SELL")):
        rows = rad.get(side) or []
        if rows: L.append(f"Trend-pullback {nm} checklist {sum(r[1] for r in rows)}/{len(rows)}: " + ", ".join(("✅ " if r[1] else "❌ ") + r[0] for r in rows))
    o = one_horizon(S, stats, hz or 60, px) if px else {}
    if o and not o.get("err"): L.append(f"History ({AS.HZ_NAME[o['m']]}): {lean_line(o)}")
    ok = M.get("verdict") in ("LONG", "SHORT")
    L.append("Nateeja: " + (f"tareeke {M['verdict']} ki taraf hain, par stop-loss ke bina entry mat socho aur candle band hone ka intezaar karo." if ok else "abhi koi saaf mauka nahi: WAIT (intezaar) bhi ek valid faisla hai. Jaldi ka trade aksar kharab hota hai."))
    L.append("Is tool ke trade sirf paper (nakli) hain. Asli paise ka faisla aapka apna risk hai.")
    return "\n".join(L)


def cfg_need(cfg): return ((cfg or {}).get("strategies") or {}).get("confluence", {}).get("need", 4)


def sec_levels(S):
    import sr as SRM
    px = S.get("last_price"); R = S.get("sr"); t = SRM.text(R)
    z = [x for x in (R or {}).get("zones", [])]
    if z: nr = min([x for x in z if x["kind"] == "resistance"], key=lambda x: x["mid"] - px, default=None); ns = max([x for x in z if x["kind"] == "support"], key=lambda x: x["mid"], default=None); t += "\n" + " | ".join(filter(None, [nr and f"Sabse paas ka mazboot resistance {P_(nr['mid'])} ({nr['mid'] - px:+,.0f} pts)", ns and f"mazboot support {P_(ns['mid'])} ({ns['mid'] - px:+,.0f} pts)"]))
    return t


def sec_position(S):
    P = S.get("paper") or {}; px = S.get("last_price"); pos = [t for t in (P.get("pos") or {}).values() if t]
    if not pos: return "📭 Abhi koi paper position khuli nahi hai. Tool naya setup milne par khud kholega."
    L = ["📌 KHULI PAPER POSITION"]
    for t in pos:
        u = (px - t["entry"]) * t["side"]; r = u / t["risk"] if t.get("risk") else 0; inr = u * t.get("qty", 0) * t.get("remaining", 1) * t.get("fx", 88)
        L.append(f"{t.get('label', t.get('strategy'))}: {'BUY' if t['side'] == 1 else 'SELL'} entry {P_(t['entry'])} | stop {P_(t['sl'])} | target {P_(t.get('tp') or t.get('t2') or t['entry'])} | abhi {r:+.2f}R ({INR(inr)})")
        m = t.get("mgmt") or {}
        if m: L.append(f"   Status: {m.get('status', '')}. {m.get('hold_vs_book', '')}")
    return "\n".join(L)


def _closed(S): return [t for t in ((S.get("paper") or {}).get("closed") or []) if t.get("R") is not None]


def sec_wallet(S):
    W = (S.get("paper") or {}).get("wallet") or {}
    if not W: return "Wallet abhi bana nahi (pehla scan chalne do)."
    eq = W.get("cash", 0) + W.get("margin", 0); st = W.get("start", 20000); C = _closed(S); net = sum(t.get("pnl_inr") or 0 for t in C)
    return f"💰 WALLET (nakli ₹)\nShuruaat {INR(st)} | abhi {INR(eq)} ({INR(eq - st)}, {(eq - st) / st * 100:+.1f}%)\nCash {INR(W.get('cash', 0))} | margin mein {INR(W.get('margin', 0))}\nBand trade: {len(C)} | unka net {INR(net)}"


def sec_performance(S):
    C = _closed(S); n = len(C)
    if not n: return "📊 Abhi koi band paper trade nahi, isliye performance kehne ko kuch nahi."
    w = [t for t in C if (t.get("pnl_inr") or 0) > 0]; avgR = sum(t["R"] for t in C) / n; net = sum(t.get("pnl_inr") or 0 for t in C); L = [f"📊 TOOL KA PERFORMANCE: {n} band trade | jeete {len(w)} ({len(w) / n * 100:.0f}%) | average {avgR:+.2f}R | net {INR(net)}"]
    by = {}
    for t in C: by.setdefault(t.get("label") or t.get("strategy", "?"), []).append(t)
    for k, v in by.items(): L.append(f"• {k}: {len(v)} trade, {sum((x.get('pnl_inr') or 0) > 0 for x in v)} jeete, {sum(x['R'] for x in v) / len(v):+.2f}R avg")
    L.append(f"Sachchai: {n} trade bahut kam hain (kam se kam 30, behtar 100 chahiye) isliye ye number kuch SABIT nahi karta. Abhi tak koi backtest bhi pakka edge sabit nahi kar paya.")
    return "\n".join(L)


def sec_flow(S):
    import orderflow as OF
    return OF.text(S.get("orderflow"))


def sec_timing(S):
    import timing as TM
    C = S.get("timing")
    if not C:
        try: C = TM.now_context(TM.load(), dt.datetime.now(dt.timezone.utc))
        except Exception: C = None
    return TM.text(C)


def sec_radar(S):
    import moveradar as MR
    return MR.text((S.get("paper") or {}).get("radar_move"), S.get("move_watch"))


def sec_risk(S, cfg):
    cfg = cfg or {}; st = (cfg.get("wallet") or {}).get("start_inr", 20000); lev = (cfg.get("wallet") or {}).get("leverage", 3); r = cfg.get("risk") or {}; L = ["🛡 RISK KE NIYAM (tool ke)"]
    for k, v in (cfg.get("strategies") or {}).items():
        if v.get("enabled", True): L.append(f"• {v.get('label', k)}: har trade mein wallet ka {v.get('risk_pct')}% risk (≈ {INR(st * v.get('risk_pct', 0) / 100)} agar stop lage)")
    L.append(f"Leverage {lev}x | ek din ka max nuksaan {r.get('max_daily_loss_pct', 3)}% (uske baad naye trade band) | har trade mein stop-loss zaroori.")
    L.append("Seedha niyam: ek trade mein wallet ka 1% se zyada risk mat lo, aur stop ke bina trade mat lo.")
    return "\n".join(L)


def sec_tool(S, cfg):
    M = S.get("market") or {}; ts = M.get("ts"); L = ["🤖 YE TOOL KAISE KAAM KARTA HAI"]
    L.append("Har 5 min GitHub par scan chalta hai: OKX ka free public data (price, funding, OI, trades) leta hai, 7 tareeke se market padhta hai, nakli ₹20,000 wallet se paper trade kholta/band karta hai. Koi asli order nahi, koi API key nahi.")
    L.append("Strategies: Trend Pullback (4H trend ke saath, pullback ke baad), Early Signal (range edge par sweep + palatna), Session Breakout (6h tight box se volume ke saath), Confluence (7 mein se 4+ tareeke ek taraf).")
    L.append("Analog engine (AI jaisa, bina API): pichhle saal ki milti-julti halat dhoondh kar upar/neeche, range aur stop-loss ka andaaza deta hai aur apni jaanch unseen data par dikhata hai. Extra: Move radar (bada move banne se pehle chetavni), Smart exit (move poora hone par trade band, lamba nahi chalta), Doosri raay (har trade par baaki tareeke kya bolte hain), Review pack (30+ trade ke baad mujhe bhejne ke liye).")
    if ts:
        try: L.append(f"Last scan: {(dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ts)).total_seconds() / 60:.0f} min pehle." + (" ⏸ PAUSED." if S.get("paused") else ""))
        except Exception: pass
    return "\n".join(L)


def sec_accuracy(S, stats):
    L = ["🔬 YE JAWAB KITNE SAHI HAIN? (do tarah ki jaanch)"]
    L.append("1) History ki jaanch (purane aadhe data par bana, baaki aadhe par parkha):")
    cnt = 0
    for m in (15, 60, 240, 1440):
        fr, F, blk = _block(stats, m)
        if not blk: continue
        st = [(k, edge_of(b, blk["base"], blk["h_bars"])) for k, b in blk["by_net"].items()]
        good = [f"{AS.BNAME[int(k)]} ({'upar' if blk['by_net'][k]['p_up'] > blk['base']['p_up'] else 'neeche'} {blk['by_net'][k]['p_up'] * 100:.0f}%)" for k, (z, s, lab) in st if not lab.startswith("koi")]
        L.append(f"• {AS.HZ_NAME[m]}: " + ("stable/halka jhukaav mila: " + ", ".join(good) if good else "koi bhi halat stable edge nahi (lagbhag sikka)")); cnt += 1
    if not cnt: L.append("• History stats abhi bani nahi.")
    D = [e for e in S.get("ask_log") or [] if e.get("done") and e.get("up") is not None]
    L.append(f"2) Asli (live) jaanch: jitne andaaze tool ne diye unka baad mein sach-jhooth: {len(D)} pure hue.")
    for m in sorted({e['h'] for e in D}):
        x = [e for e in D if e["h"] == m and abs(e["p_up"] - 0.5) >= 0.03]
        if x: L.append(f"• {AS.HZ_NAME[m]}: jhukaav wale {len(x)} andaazon mein se {sum((e['p_up'] > 0.5) == e['up'] for e in x)} sahi")
    L.append("Seedhi baat: 5 min/1 ghante ki direction koi bhi tool 55% se zyada pakka nahi bata sakta. Isliye jahan edge nahi hota wahan ye tool 50-50 hi likhta hai.")
    return "\n".join(L)


def sec_dailyhist(arc, n):
    import dailylog as DL
    arc = arc or DL.load(); m = re.search(r"(\d+)\s*(din|days?|hafte|weeks?|mahine|months?)", n)
    if m:
        k = int(m.group(1)) * (7 if m.group(2).startswith(("hafte", "week")) else 30 if m.group(2).startswith(("mahine", "month")) else 1); k = max(1, min(k, 30))
        return DL.text_days(arc, k) + ("\n\n" + DL.text_stats(arc) if len(arc.get("days", {})) >= 3 else "")
    return DL.text_stats(arc) + "\n\n" + DL.text_days(arc, 7)


def _hkey(hz): return "4" if hz is None else "1" if hz <= 90 else "4" if hz <= 480 else "24"
HK_NAME = {"1": "1 ghanta", "4": "4 ghante", "24": "24 ghante (1 din)"}


def sec_analog(S, hz=None):
    A = S.get("analog"); px = S.get("last_price")
    if not A or not A.get("hz") or not px: return ""
    key = _hkey(hz); st = A["hz"].get(key)
    if not st: return ""
    v = (A.get("val") or {}).get(key) or {}; pt = lambda x: f"{x / 100 * px:,.0f}"; p = st["p_up"]; clear = st["lo"] > 0.5 or st["hi"] < 0.5
    dir_ok = bool(v.get("hit_pct") and v["hit_pct"] >= 53 and v.get("lean_n", 0) >= 300 and v.get("brier", 1) < v.get("brier_base", 0))
    L = [f"🔬 ANALOG ENGINE (AI jaisa, bina API): pichhle {A.get('days', '?')} din mein abhi jaisi sabse milti-julti {st['n']} halat dhoondhi. Unke baad {HK_NAME[key]} mein:",
         f"• Upar {p * 100:.0f}% / neeche {100 - p * 100:.0f}% (95% daayra {st['lo'] * 100:.0f}-{st['hi'] * 100:.0f}%, normal din {st['base'] * 100:.0f}%)"]
    L.append("• " + (f"Jhukaav {'UPAR' if p > 0.5 else 'NEECHE'} dikh raha hai" + (" aur engine ki unseen-data jaanch bhi pass hai." if dir_ok else ", par engine ki direction wali jaanch pass nahi hui (unseen data par bharosa nahi), isliye ise pakka mat maano.") if clear else "koi saaf jhukaav nahi: lagbhag 50-50."))
    L.append(f"• Range ({HK_NAME[key]}): aksar {pt(st['rng'][0])} pts; 4 mein 1 baar {pt(st['rng'][1])}+; 10 mein 1 baar {pt(st['rng'][2])}+. Beech mein upar tak aksar +{pt(st['up50'])}, neeche tak -{pt(st['dn50'])} pts.")
    if v: L.append(f"• Engine ki apni jaanch (unseen data, {v.get('tests', 0)} test): direction sahi {v.get('hit_pct', 'n/a')}% (sikka = 50%), range ka ranking-score {v.get('range_corr', 'n/a')} (sirf ATR se {v.get('range_corr_atr', 'n/a')}), 90% sima {v.get('p90_coverage', 'n/a')}% baar sahi.")
    return "\n".join(L)


def sec_stoploss(S, hz):
    A = S.get("analog"); px = S.get("last_price"); M = S.get("market") or {}; key = _hkey(hz); L = ["🛑 STOP-LOSS KITNA DOOR RAKHO? (andaaza, guarantee nahi)"]
    st = ((A or {}).get("hz") or {}).get(key)
    if st and px:
        import analog as AN
        L.append(f"Analog engine: abhi jaisi halat mein position {HK_NAME[key]} rakhne par stop kitni baar chhu jata hai (beech mein ek baar bhi wahan pahunchna):")
        for g, tu, td in zip(AN.GRID, st["touch_up"], st["touch_dn"]):
            if g in (0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0): L.append(f"  stop {g}% ({g / 100 * px:,.0f} pts) door: BUY ka stop chhuega {td * 100:.0f}% | SELL ka stop chhuega {tu * 100:.0f}%")
        L.append("Chhota stop zyada baar kat-ta hai; bada stop kam kat-ta hai par ek haar badi hoti hai (position chhoti rakhni padti hai).")
    else: L.append("Analog engine ka data abhi bana nahi (scanner ka agla run), isliye neeche ka ATR aur daily range dekho.")
    a1, a4 = M.get("atr1h"), M.get("atr4h")
    if a1: L.append(f"ATR: 1H {a1:,.0f} pts, 4H {(a4 or 0):,.0f} pts. Aam niyam: stop 1.5 se 2.5 ATR door rakho taaki normal halchal se na kate.")
    D = (S.get("daily") or {}).get("avg7")
    if D: L.append(f"Daily range (pichhle {D['n']} din ka average): {D['rng']:,.0f} pts ({D['rng_pct']}%), upar +{D['up']:,.0f} / neeche -{D['dn']:,.0f}.")
    L.append("Fees: aana-jaana ~0.1%, isliye stop 0.5% se chhota ho to akele fees 0.2R se zyada kha jati hain. Tool 0.5% se tight stop wale trade nahi leta (31 trade ke review ke baad).")
    L.append("Stop wahan rakho jahan trade ka idea galat sabit ho (swing low/high ke us paar), sirf 'itne points' dekh kar nahi.")
    return "\n".join(L)


def sec_gloss(g): return f"📖 {g[0]}\n{g[1]}"


def sec_other(n):
    m = re.search(OTHER, n)
    return f"Ye tool sirf BTC perpetual ka live data track karta hai, '{m.group(1) if m else 'dusre asset'}' ka nahi. Isliye uski direction par main andaaza nahi de sakta. Concepts (RSI, support, stop-loss, options...) samjha sakta hu, aur BTC par poora analysis de sakta hu."


# ---------------------------------------------------------------- entry point
def answer(q, S, cfg=None, stats=None, log=False, max_len=3800, arc=None):
    """q: question text. S: state.json dict. cfg: merged config. stats: ask_stats.json dict. log: True in the worker only (stores forecasts to measure real accuracy)."""
    S = S or {}; q = (q or "").strip()
    if not q: return "Sawaal likho. " + EXAMPLES
    u = understand(q, S); it = u["intents"]; px = S.get("last_price"); out = []
    needs_px = {"direction", "size", "market", "advice", "levels", "target", "stoploss"}
    if not it: return "Ye sawaal main samajh nahi paya. " + EXAMPLES
    S["ask_ctx"] = dict(intents=it, hz=u["hz"], ts=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    if "hello" in it: return "Namaste 👋 Main BTC tool ka 'Ask' hu. Market, trade, wallet ya trading ke kisi bhi sawaal par bina API key ke tool ke apne data se jawab deta hu.\n" + EXAMPLES
    if px is None and set(it) & needs_px: return "Market data abhi state mein nahi aaya (scanner ka pehla run chalne do), isliye abhi analysis nahi de sakta."
    for k in it:
        try:
            out.append({"direction": lambda: sec_direction(S, stats, u["hz"], log), "size": lambda: sec_size(S, stats, u["hz"]), "daily": lambda: AS.daily_text(S.get("daily"), px), "stoploss": lambda: sec_stoploss(S, u["hz"]), "dailyhist": lambda: sec_dailyhist(arc, u["n"]), "market": lambda: sec_market(S, stats), "advice": lambda: sec_advice(S, stats, u["hz"], cfg),
                        "levels": lambda: sec_levels(S), "position": lambda: sec_position(S), "wallet": lambda: sec_wallet(S), "performance": lambda: sec_performance(S), "flow": lambda: sec_flow(S), "timing": lambda: sec_timing(S),
                        "radar": lambda: sec_radar(S), "risk": lambda: sec_risk(S, cfg), "tool": lambda: sec_tool(S, cfg), "accuracy": lambda: sec_accuracy(S, stats), "target": lambda: sec_target(S, stats, u["prices"], u["pts"], u["n"]),
                        "glossary": lambda: sec_gloss(u["gloss"]), "other": lambda: sec_other(u["n"])}[k]())
        except Exception as e: out.append(f"({k} wala hissa abhi bana nahi paya: {type(e).__name__})")
    text = "\n\n".join(x for x in out if x)
    if set(it) & {"direction", "target", "size", "advice", "stoploss"}: text += "\n\n" + DIS
    return text[:max_len] + ("…" if len(text) > max_len else "")
