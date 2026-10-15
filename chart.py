"""Candlestick price-action chart (plotly): candles + EMA20/50, swing points, candlestick-pattern markers (engulfing, hammer, shooting star, stars),
support/resistance lines for the chosen timeframe, multi-timeframe confluence zones, the tool's own entry / stop / target lines and past trades,
volume, and the order-flow profile (buy vs sell volume at each price) on the right."""
import datetime as dt
import numpy as np, pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import methods as MT

G, R_, B_, GR = "#26a69a", "#ef5350", "#4da3ff", "#8a8f98"
IST = dt.timedelta(hours=5, minutes=30)


def _x(ts): return [dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).replace(tzinfo=None) + IST for t in ts]


def pattern_markers(I, start, strong_only=True):
    out = []
    for j in range(max(start, 210), I["n"] - 1):
        v = [x for x in MT.votes(I, j) if x[0] == "candles" and x[1] != 0]
        if v and (not strong_only or "bharosemand" in v[0][3]): out.append((j, v[0][1], v[0][3]))
    return out


def make_figure(df, tf, lv=None, zones=None, open_pos=None, closed=None, profile=None, bars=120, show_patterns=True, show_swings=True, strong_only=True, height=640):
    d = df.reset_index(drop=True); I = MT.prepare(d); n = I["n"]; s = max(0, n - bars); xs = _x(d.ts.values); px = float(d.c.iloc[-1])
    fig = make_subplots(rows=2, cols=2, column_widths=[0.84, 0.16], row_heights=[0.78, 0.22], shared_xaxes="columns", shared_yaxes="rows", horizontal_spacing=0.01, vertical_spacing=0.03, specs=[[{}, {}], [{}, None]])
    X = xs[s:]; fig.add_trace(go.Candlestick(x=X, open=d.o[s:], high=d.h[s:], low=d.l[s:], close=d.c[s:], increasing_line_color=G, decreasing_line_color=R_, name="Price", showlegend=False), 1, 1)
    fig.add_trace(go.Scatter(x=X, y=I["ema20"][s:], line=dict(color="#f5c542", width=1), name="EMA20", hoverinfo="skip"), 1, 1)
    fig.add_trace(go.Scatter(x=X, y=I["ema50"][s:], line=dict(color="#b57bff", width=1), name="EMA50", hoverinfo="skip"), 1, 1)
    fig.add_trace(go.Bar(x=X, y=d.v[s:], marker_color=[G if c >= o else R_ for o, c in zip(d.o[s:], d.c[s:])], name="Volume", showlegend=False), 2, 1)
    if show_swings:
        sh = [(xs[j], float(I["h"][j - MT.K])) for j in range(s + MT.K, n) if I["sh"][j] == I["sh"][j] and j - MT.K >= s]; sl = [(xs[j], float(I["l"][j - MT.K])) for j in range(s + MT.K, n) if I["sl"][j] == I["sl"][j] and j - MT.K >= s]
        # pivot value is stored at confirmation bar j; its candle is j-K
        sh = [(xs[j - MT.K], float(I["sh"][j])) for j in range(s + MT.K, n) if I["sh"][j] == I["sh"][j]]; sl = [(xs[j - MT.K], float(I["sl"][j])) for j in range(s + MT.K, n) if I["sl"][j] == I["sl"][j]]
        if sh: fig.add_trace(go.Scatter(x=[p[0] for p in sh], y=[p[1] for p in sh], mode="markers", marker=dict(symbol="diamond", size=6, color=R_), name="Swing high", hovertemplate="Swing high %{y:,.0f}<extra></extra>"), 1, 1)
        if sl: fig.add_trace(go.Scatter(x=[p[0] for p in sl], y=[p[1] for p in sl], mode="markers", marker=dict(symbol="diamond", size=6, color=G), name="Swing low", hovertemplate="Swing low %{y:,.0f}<extra></extra>"), 1, 1)
    if show_patterns:
        pm = pattern_markers(I, s, strong_only)
        up = [(j, t) for j, k, t in pm if k == 1]; dn = [(j, t) for j, k, t in pm if k == -1]
        if up: fig.add_trace(go.Scatter(x=[xs[j] for j, _ in up], y=[I["l"][j] - 0.6 * I["atr"][j] for j, _ in up], mode="markers", marker=dict(symbol="triangle-up", size=11, color=G, line=dict(color="white", width=1)), text=[t for _, t in up], hovertemplate="%{text}<extra></extra>", name="Bullish pattern"), 1, 1)
        if dn: fig.add_trace(go.Scatter(x=[xs[j] for j, _ in dn], y=[I["h"][j] + 0.6 * I["atr"][j] for j, _ in dn], mode="markers", marker=dict(symbol="triangle-down", size=11, color=R_, line=dict(color="white", width=1)), text=[t for _, t in dn], hovertemplate="%{text}<extra></extra>", name="Bearish pattern"), 1, 1)
    lo_v, hi_v = float(d.l[s:].min()), float(d.h[s:].max()); pad = (hi_v - lo_v) * 0.15
    for z in (zones or []):                                                          # multi-timeframe confluence zones
        if z["hi"] < lo_v - pad or z["lo"] > hi_v + pad: continue
        col = "rgba(38,166,154,0.16)" if z["kind"] == "support" else "rgba(239,83,80,0.16)"
        fig.add_hrect(y0=z["lo"] - px * 0.0006, y1=z["hi"] + px * 0.0006, fillcolor=col, line_width=0, row=1, col=1, annotation_text="+".join(z["tfs"]), annotation_position="top left", annotation_font_size=9)
    for kind, col in (("supports", G), ("resistances", R_)):                            # this timeframe's own levels
        for x in (lv or {}).get(kind, []):
            if lo_v - pad <= x["price"] <= hi_v + pad:
                fig.add_hline(y=x["price"], line=dict(color=col, width=1, dash="dot"), row=1, col=1, annotation_text=f"{'S' if kind == 'supports' else 'R'} {x['price']:,.0f} ({x['touches']}x)", annotation_position="bottom right" if kind == "supports" else "top right", annotation_font=dict(color=col, size=10))
    for t in (open_pos or []):
        for val, lab, col, dash in ((t["entry"], "ENTRY", B_, "solid"), (t["sl"], "STOP", R_, "dash"), (t.get("tp") or t.get("t2"), "TARGET", G, "dash")):
            if val: fig.add_hline(y=float(val), line=dict(color=col, width=1.6, dash=dash), row=1, col=1, annotation_text=f"{t.get('id', '')[-7:]} {lab} {float(val):,.0f}", annotation_position="top left", annotation_font=dict(color=col, size=10)); lo_v, hi_v = min(lo_v, float(val)), max(hi_v, float(val))
    t0 = X[0]
    for r in (closed or []):                                                         # past trades as markers
        try:
            ox = dt.datetime.fromisoformat(r["opened"]).astimezone(dt.timezone.utc).replace(tzinfo=None) + IST
            if ox >= t0: fig.add_trace(go.Scatter(x=[ox], y=[r["entry"]], mode="markers", marker=dict(symbol="triangle-up" if r["side"] == "LONG" else "triangle-down", size=10, color="rgba(0,0,0,0)", line=dict(color=B_, width=2)), text=[f"{r['id']} {r['side']} {r.get('outcome', '')} {r.get('R', 0):+.2f}R"], hovertemplate="%{text}<extra></extra>", name="Past trade", showlegend=False), 1, 1)
        except Exception: pass
    if profile:
        ys = [p[0] + 25 for p in profile]; fig.add_trace(go.Bar(y=ys, x=[p[1] for p in profile], orientation="h", marker_color=G, name="Buy vol", width=40, hovertemplate="%{y:,.0f}: buy %{x:.1f} BTC<extra></extra>"), 1, 2)
        fig.add_trace(go.Bar(y=ys, x=[p[2] for p in profile], orientation="h", marker_color=R_, name="Sell vol", width=40, hovertemplate="%{y:,.0f}: sell %{x:.1f} BTC<extra></extra>"), 1, 2)
    fig.add_hline(y=px, line=dict(color=GR, width=1, dash="dot"), row=1, col=1)
    fig.update_layout(template="plotly_dark", height=height, margin=dict(l=8, r=8, t=30, b=8), barmode="stack", xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False, showlegend=False,
                      title=dict(text=f"BTC perpetual {tf} (time = IST)", font=dict(size=13), x=0.01), hovermode="closest", dragmode="pan")
    fig.update_yaxes(range=[lo_v - pad, hi_v + pad], row=1, col=1); fig.update_yaxes(showticklabels=False, row=1, col=2); fig.update_xaxes(showticklabels=False, row=1, col=2)
    return fig
