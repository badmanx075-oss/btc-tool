"""Point-move classification (spec 12, 13, 25). The same absolute move means different things in different volatility, so every row shows
POINTS + PERCENT + VOLATILITY-ADJUSTED size (multiples of the 4-hour ATR), a size class that adapts to current volatility, and, when
move_stats.json exists, how often price HISTORICALLY travelled that far in 24h / 72h from the same volatility bucket (up and down separately)."""
import numpy as np

POINTS = (500, 1000, 2000, 5000, 10000)
CLASSES = ((1.0, "SMALL"), (2.0, "MEDIUM"), (4.0, "LARGE"), (1e9, "VERY LARGE / EXTENDED"))


def size_class(pts, atr4h):
    r = abs(pts) / max(atr4h, 1e-9)
    for lim, name in CLASSES:
        if r < lim: return name
    return CLASSES[-1][1]


def bucket(stats, atr1h, px):
    if not stats: return None
    p = atr1h / px * 100; e = stats["edges"]; return int(p > e[0]) + int(p > e[1])


def _odds(stats, b, hz, pct):
    H = stats["H"][str(hz)][str(b)]; g = stats["grid"]
    return round(float(np.interp(pct, g, H["up"])), 3), round(float(np.interp(pct, g, H["dn"])), 3)


def table(px, atr1h, atr4h, stats=None):
    b = bucket(stats, atr1h, px); rows = []
    for pts in POINTS:
        pct = pts / px * 100; row = dict(points=pts, pct=round(pct, 2), atr4h_multiple=round(pts / max(atr4h, 1e-9), 2), size_class=size_class(pts, atr4h), atr1h_multiple=round(pts / max(atr1h, 1e-9), 1))
        if stats and b is not None and pct <= max(stats["grid"]):
            row["up_24h"], row["dn_24h"] = _odds(stats, b, 24, pct); row["up_72h"], row["dn_72h"] = _odds(stats, b, 72, pct)
        rows.append(row)
    ranges = None
    if stats and b is not None:
        q = stats["Q"]["24"][str(b)]; ranges = {s: [round(x / 100 * px) for x in q[s]] for s in ("up", "dn")}   # 50/75/90/95th percentile travel in 24h, in points
    return dict(bucket=b, bucket_name=None if b is None else ("calm", "normal", "wild")[b], sample=None if not stats or b is None else stats["n_bucket"][str(b)], rows=rows, typical_24h_points=ranges,
                note="Class is relative to the 4H ATR (SMALL <1x, MEDIUM 1-2x, LARGE 2-4x, VERY LARGE >4x). Probabilities are history, not forecasts.")


def classify_setup(entry, target, atr4h):
    """Size class of the move from entry to a target (used for the live setup)."""
    pts = abs(target - entry); return dict(points=round(pts), size_class=size_class(pts, atr4h), atr4h_multiple=round(pts / max(atr4h, 1e-9), 2))
