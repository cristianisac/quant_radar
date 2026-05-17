"""Agent-facing pattern-detection tools.

Per the user spec the chat agent first asks the user whether they want
algorithmic detection, LLM-vision detection, or both, and only then
calls these tools.

- ``detect_channels``: deterministic, scipy-based. Returns a dict with
  ``found``, ``confidence``, slopes, intercepts, touches. Confidence
  below threshold → caller should not draw.
- ``detect_breakouts``: deterministic, given a channel. ATR-based noise
  filter applied if an OHLC frame is provided.
- ``detect_patterns_vision``: renders the chart to PNG and returns the
  path. The agent should open the image with its Read tool and identify
  any patterns visually.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from quant_radar.analytics import patterns
from quant_radar.analytics.indicators import atr
from quant_radar.analytics.vision import render_chart_png
from quant_radar.tools.compat import requires_columns
from quant_radar.tools.dataframe import filter_by_date

VISION_INSTRUCTIONS = (
    "Open the image at `image_path` with your Read tool, then look for chart "
    "patterns (head-and-shoulders, channels, wedges, triangles, flags, "
    "double tops/bottoms, support/resistance). For each pattern, report its "
    "name and a confidence score 0.0-1.0. If confidence < 0.7, do not draw "
    "the pattern on the dashboard; instead state that no pattern was found "
    "at high enough confidence. Be precise and conservative."
)


@requires_columns("close")
def detect_channels(
    df: pd.DataFrame,
    *,
    price_col: str = "close",
    lookback: int = 60,
    swing_distance: int = 5,
    min_touches: int = 3,
    confidence_threshold: float = 0.65,
    min_r2: float = 0.55,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
) -> dict[str, Any]:
    """``start``/``end`` slice the frame *before* the lookback is applied,
    so e.g. ``end="2024-12-31"`` runs detection on the last 60 bars of 2024.
    """
    if start is not None or end is not None:
        df = filter_by_date(df, start=start, end=end)
    if price_col not in df.columns:
        raise ValueError(f"price column '{price_col}' not in DataFrame")
    return patterns.detect_channel(
        cast(pd.Series, df[price_col]),
        lookback=lookback,
        swing_distance=swing_distance,
        min_touches=min_touches,
        threshold=confidence_threshold,
        min_r2=min_r2,
    )


@requires_columns("close")
def detect_breakouts(
    df: pd.DataFrame,
    channel: dict | None = None,
    *,
    price_col: str = "close",
    lookback: int = 60,
    confidence_threshold: float = 0.6,
    use_atr_filter: bool = True,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
) -> dict[str, Any]:
    """If ``channel`` is not provided, one is detected automatically first.

    ``start``/``end`` slice the frame so detection runs on a specific window.
    """
    if start is not None or end is not None:
        df = filter_by_date(df, start=start, end=end)
    if price_col not in df.columns:
        raise ValueError(f"price column '{price_col}' not in DataFrame")
    ch = channel or detect_channels(
        df,
        price_col=price_col,
        lookback=lookback,
        confidence_threshold=confidence_threshold,
    )
    atr_series: pd.Series | None = None
    if use_atr_filter and {"high", "low", "close"}.issubset(df.columns):
        atr_series = atr(
            cast(pd.Series, df["high"]),
            cast(pd.Series, df["low"]),
            cast(pd.Series, df["close"]),
        )
    return patterns.detect_breakout(
        cast(pd.Series, df[price_col]), ch, atr=atr_series
    )


@requires_columns("close")
def detect_patterns_vision(
    df: pd.DataFrame,
    *,
    asset_name: str,
    title: str | None = None,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
) -> dict[str, Any]:
    """Render the chart and ask the calling agent to read it.

    Returns ``{"image_path": str, "instructions": str}``. The agent uses
    its own Read tool on ``image_path`` — no external API call here.
    ``start``/``end`` restrict the rendered window so the LLM only sees
    the period the user asked about.
    """
    if start is not None or end is not None:
        df = filter_by_date(df, start=start, end=end)
    path: Path = render_chart_png(df, asset_name=asset_name, title=title)
    return {
        "image_path": str(path),
        "instructions": VISION_INSTRUCTIONS,
        "confidence_threshold": 0.7,
    }


def channel_annotations(
    df: pd.DataFrame, channel: dict, *, price_col: str = "close"
) -> list[dict] | None:
    """Return two ``Annotation`` dicts (upper + lower) ready for ``add_annotation``."""
    pts = patterns.channel_to_annotation_points(
        cast(pd.Series, df[price_col]), channel
    )
    if pts is None:
        return None
    upper, lower = pts
    return [
        {
            "kind": "trendline",
            "points": [list(p) for p in upper],
            "label": "channel upper",
            "color": "#ef4444",
        },
        {
            "kind": "trendline",
            "points": [list(p) for p in lower],
            "label": "channel lower",
            "color": "#22c55e",
        },
    ]
