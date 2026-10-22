"""Every tunable setting lives here. Change it by editing config.json on GitHub, or from Telegram with /set. No code change needed."""
import json, os, copy, datetime as dt
PATH = os.environ.get("BTC_CONFIG") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEFAULTS = {
    "wallet": {"start_inr": 20000, "leverage": 3, "fee_rate_per_side": 0.0005, "max_open_positions": 3, "qty_step": 0.0001},
    "alerts": {"paper_open": True, "paper_close": True, "stage_alerts": True, "feedback_buttons": True, "advice": True, "signals": True, "reversal": True,
               "learning": True, "setup": True, "move": True, "flow": True, "confirm": True, "timing": True, "milestone": True, "morning": True, "evening": True, "weekly": True},
    "schedule": {"morning_hour": 8, "evening_hour": 20, "listen_seconds": 210},
    "timing": {"skip_low_activity": False, "window_alerts": True},
    "risk": {"max_daily_loss_pct": 3.0, "min_methods_agree": 0, "min_stop_pct": 0.5},
    "exits": {"smart_exit": True, "min_profit_R": 1.0, "exhaustion_min": 70, "stall_hours": 10, "stall_band_R": 0.3, "use_expected_move": False},
    "strategies": {
        "trend_pullback": {"enabled": True, "label": "Trend Pullback", "risk_pct": 1.0, "stop_atr": 3.0, "target_r": 4.0, "expiry_hours": 120, "cooldown_hours": 24},
        "early_signal": {"enabled": True, "label": "Early Signal (experimental)", "risk_pct": 0.5, "min_score": 65, "partial_pct": 50, "expiry_hours": 72, "cooldown_hours": 1},
        "session_breakout": {"enabled": True, "label": "Session Breakout (experimental)", "risk_pct": 0.3, "box_hours": 6, "vol_mult": 1.3, "stop_min_atr": 1.0, "stop_max_atr": 2.5, "target_r": 2.0, "expiry_hours": 24, "cooldown_hours": 6},
        "confluence": {"enabled": False, "label": "Multi-Method Confluence (experimental)", "risk_pct": 0.4, "need": 4, "net_min": 35, "stop_min_atr": 1.2, "stop_max_atr": 3.0, "target_r": 2.0, "expiry_hours": 48, "cooldown_hours": 12},
        "analog_edge": {"enabled": False, "label": "Analog Engine (experimental)", "risk_pct": 0.3, "stop_atr": 1.5, "target_r": 1.5, "expiry_hours": 12, "cooldown_hours": 4, "require_validated": True}}}
LIMITS = {"start_inr": (1000, 10000000), "leverage": (1, 20), "fee_rate_per_side": (0, 0.005), "max_open_positions": (1, 10), "qty_step": (0.00001, 0.01), "risk_pct": (0.05, 5),
          "stop_atr": (0.5, 10), "target_r": (0.5, 20), "expiry_hours": (1, 720), "cooldown_hours": (0, 168), "partial_pct": (10, 90), "min_score": (40, 95),
          "max_daily_loss_pct": (0.5, 50), "min_methods_agree": (0, 7), "min_stop_pct": (0, 5), "exhaustion_min": (30, 100), "min_profit_R": (0.2, 10), "stall_hours": (2, 120), "stall_band_R": (0.05, 1.5), "need": (2, 7), "net_min": (10, 90), "box_hours": (3, 24), "vol_mult": (1, 5), "stop_min_atr": (0.3, 5), "stop_max_atr": (0.5, 10), "morning_hour": (0, 23), "evening_hour": (0, 23), "listen_seconds": (0, 250)}

def _merge(a, b):
    out = copy.deepcopy(a)
    for k, v in b.items(): out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out

def load():
    try: over = json.load(open(PATH))
    except Exception: over = {}
    return _merge(DEFAULTS, over)
get = load

def snapshot(C, name): return copy.deepcopy(dict(C["strategies"][name], leverage=C["wallet"]["leverage"], fee_per_side=C["wallet"]["fee_rate_per_side"]))
def ist(now, C=None): return (now + dt.timedelta(hours=5, minutes=30)).strftime("%d %b %H:%M")
def inr(x): return f"{'-' if x < 0 else ''}₹{abs(x):,.0f}"

def _find(name):
    C = load()
    if "." in name: return ("strategies." + name) if name.split(".")[0] in C["strategies"] else name
    hits = [f"{sec}.{name}" if sec != "strategies" else None for sec in ("wallet", "alerts", "schedule", "timing", "risk", "exits") if name in C[sec]] + [f"strategies.{s}.{name}" for s, v in C["strategies"].items() if name in v]
    hits = [h for h in hits if h]
    return hits[0] if len(hits) == 1 else (hits if hits else None)

def set_path(path, raw):
    cfg = load(); disk = {}
    try: disk = json.load(open(PATH))
    except Exception: pass
    node, keys = cfg, path.split(".")
    for k in keys[:-1]:
        if not isinstance(node.get(k), dict): return False, f"Unknown setting: {path}"
        node = node[k]
    if keys[-1] not in node or isinstance(node[keys[-1]], dict): return False, f"Unknown setting: {path}"
    try: val = json.loads(raw)
    except Exception: return False, "Value must be a number or true/false (on/off)."
    old = node[keys[-1]]
    if isinstance(old, bool) != isinstance(val, bool) or isinstance(old, list) != isinstance(val, list): return False, f"{path} expects the same kind of value as {old!r}"
    lo, hi = LIMITS.get(keys[-1], (None, None))
    if lo is not None and not (lo <= val <= hi): return False, f"{keys[-1]} must be between {lo} and {hi}"
    d = disk
    for k in keys[:-1]: d = d.setdefault(k, {})
    d[keys[-1]] = val; json.dump(disk, open(PATH, "w"), indent=1)
    return True, f"{path}: {old} -> {val}"

def set_value(name, raw):
    p = _find(name)
    if p is None: return f"Unknown setting '{name}'. Send /config to see all."
    if isinstance(p, list): return "Kaunsa? Poora naam likho: " + ", ".join(p)
    ok, msg = set_path(p, raw.lower().replace("on", "true").replace("off", "false") if raw.lower() in ("on", "off") else raw)
    return ("✅ " if ok else "❌ ") + msg + ("\nNaye trades par lagega. Kholi hui positions pehle ki rules par chalti hain." if ok and p.startswith("strategies") else "")

def set_notify(name, onoff): return set_value("alerts." + name, "true" if onoff.lower() in ("on", "true", "1") else "false")

def show(C=None):
    C = C or load(); L = ["⚙️ SETTINGS (/set naam value, jaise /set trend_pullback.risk_pct 2)"]
    for sec in ("wallet", "schedule", "timing", "risk", "exits"): L.append(f"[{sec}] " + ", ".join(f"{k}={v}" for k, v in C[sec].items()))
    L.append("[alerts] " + ", ".join(f"{k}={'on' if v else 'off'}" for k, v in C["alerts"].items()))
    for s, v in C["strategies"].items(): L.append(f"[{s}] " + ", ".join(f"{k}={v}" for k, v in v.items() if k != "label"))
    L.append("Backtested rules: trend_pullback stop 3, target 4, expiry 120. Dusri settings untested hain.")
    return "\n".join(L)
