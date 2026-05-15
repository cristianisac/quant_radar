"""Card → Plotly figure / Streamlit component renderers.

Pure-ish: the figure builders return ``plotly.graph_objects.Figure``s
without touching Streamlit. The Streamlit-aware ``render_card`` lives in
``app.py``.

A chart spec can request:
- overlays: indicator series drawn on top of price (``sma_50``, ``sma_200``,
  ``ema_12``, ``ema_26``)
- subplots: separate panels below (``rsi``, ``atr``, ``volume``, ``macd``,
  ``yoy``)
- annotations: user-drawn lines/shapes/text persisted on the card
"""

from __future__ import annotations

from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quant_radar.analytics import indicators
from quant_radar.cards.spec import Annotation, Card

_OVERLAY_PERIODS: dict[str, tuple[str, int]] = {
    "sma_50": ("sma", 50),
    "sma_200": ("sma", 200),
    "ema_12": ("ema", 12),
    "ema_26": ("ema", 26),
}


def _is_ohlcv(df: pd.DataFrame) -> bool:
    return {"open", "high", "low", "close"}.issubset(df.columns)


def _base_price_trace(df: pd.DataFrame, name: str) -> Any:
    if _is_ohlcv(df):
        return go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=name,
        )
    col = "close" if "close" in df.columns else df.columns[0]
    return go.Scatter(x=df.index, y=df[col], mode="lines", name=name)


def _overlay_trace(df: pd.DataFrame, name: str) -> go.Scatter | None:
    if name not in _OVERLAY_PERIODS or "close" not in df.columns:
        return None
    fn_name, period = _OVERLAY_PERIODS[name]
    fn = indicators.sma if fn_name == "sma" else indicators.ema
    series = fn(cast(pd.Series, df["close"]), period)
    return go.Scatter(x=df.index, y=series, mode="lines", name=name)


def _subplot_series(df: pd.DataFrame, name: str) -> tuple[str, pd.Series] | None:
    if name == "rsi" and "close" in df.columns:
        return "RSI", indicators.rsi(cast(pd.Series, df["close"]))
    if name == "atr" and _is_ohlcv(df):
        return "ATR", indicators.atr(
            cast(pd.Series, df["high"]),
            cast(pd.Series, df["low"]),
            cast(pd.Series, df["close"]),
        )
    if name == "volume" and "volume" in df.columns:
        return "Volume", cast(pd.Series, df["volume"])
    if name == "yoy" and "close" in df.columns:
        close = cast(pd.Series, df["close"])
        yoy = close.pct_change(periods=252) * 100
        return "YoY %", yoy
    return None


def _apply_annotation(fig: go.Figure, ann: Annotation) -> None:
    if ann.kind == "hline" and ann.points:
        fig.add_hline(y=ann.points[0][1], line_color=ann.color or "white")
    elif ann.kind == "vline" and ann.points:
        fig.add_vline(x=ann.points[0][0], line_color=ann.color or "white")
    elif ann.kind == "trendline" and len(ann.points) >= 2:
        xs = [p[0] for p in ann.points]
        ys = [p[1] for p in ann.points]
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys, mode="lines",
                line={"color": ann.color or "white", "dash": "dash"},
                name=ann.label or "trendline",
            )
        )
    elif ann.kind == "rect" and len(ann.points) >= 2:
        (x0, y0), (x1, y1) = ann.points[0], ann.points[1]
        fig.add_shape(
            type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
            line={"color": ann.color or "white"},
        )
    elif ann.kind == "text" and ann.points:
        x, y = ann.points[0]
        fig.add_annotation(x=x, y=y, text=ann.label or "")


def build_chart_figure(
    card: Card,
    frames: list[pd.DataFrame],
    *,
    show_modebar: bool = False,
) -> go.Figure:
    """Build a Plotly figure for a chart card.

    Frames must be the hydrated DataFrames in the same order as
    ``card.data_refs``. The first frame is treated as the price series;
    additional frames are plotted as line overlays.
    """
    assert card.chart_spec is not None
    spec = card.chart_spec
    subplot_specs = [s for s in spec.subplots if _subplot_series(frames[0], s)]
    n_rows = 1 + len(subplot_specs)
    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.6] + [0.4 / max(len(subplot_specs), 1)] * len(subplot_specs),
    )

    fig.add_trace(_base_price_trace(frames[0], card.data_refs[0].name), row=1, col=1)
    for extra_ref, extra_df in zip(card.data_refs[1:], frames[1:], strict=False):
        col = "close" if "close" in extra_df.columns else extra_df.columns[0]
        fig.add_trace(
            go.Scatter(x=extra_df.index, y=extra_df[col], mode="lines", name=extra_ref.name),
            row=1, col=1,
        )

    for overlay in spec.overlays:
        trace = _overlay_trace(frames[0], overlay)
        if trace is not None:
            fig.add_trace(trace, row=1, col=1)

    for i, sub in enumerate(subplot_specs, start=2):
        result = _subplot_series(frames[0], sub)
        if result is None:
            continue
        label, series = result
        fig.add_trace(
            go.Scatter(x=series.index, y=series, mode="lines", name=label),
            row=i, col=1,
        )

    for ann in spec.annotations:
        _apply_annotation(fig, ann)

    fig.update_layout(
        title=card.title,
        height=420 + 140 * len(subplot_specs),
        showlegend=True,
        xaxis_rangeslider_visible=False,
        margin={"l": 40, "r": 20, "t": 40, "b": 20},
    )
    if show_modebar:
        fig.update_layout(dragmode="drawopenpath")
    return fig


def chart_modebar_config(*, drawing_enabled: bool) -> dict[str, Any]:
    """Plotly modebar config — extra draw tools shown when enlarged."""
    extra = (
        ["drawline", "drawopenpath", "drawrect", "eraseshape"] if drawing_enabled else []
    )
    return {
        "displayModeBar": True,
        "modeBarButtonsToAdd": extra,
        "scrollZoom": True,
    }
