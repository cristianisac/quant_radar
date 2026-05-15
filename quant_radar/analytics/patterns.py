"""Algorithmic channel & breakout detection.

A *channel* here is a pair of parallel-ish trendlines fit to recent
swing highs (upper) and swing lows (lower). We report:
- whether the algorithm thinks a channel is present (``found``)
- a 0-1 ``confidence`` derived from parallelism, fit quality, and the
  number of touches
- the slope/intercept of each trendline in **index space** (bar number
  within the lookback window starting at 0)

This module is deterministic. The chat agent decides whether to draw —
per SKILL.md, only when confidence ≥ threshold.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from scipy.stats import linregress

ChannelDirection = Literal["ascending", "descending", "sideways", "unknown"]

DEFAULT_LOOKBACK = 60
DEFAULT_SWING_DISTANCE = 5
DEFAULT_MIN_TOUCHES = 3
DEFAULT_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class Channel:
    found: bool
    confidence: float
    direction: ChannelDirection
    lookback: int
    window_start: pd.Timestamp | None
    window_end: pd.Timestamp | None
    slope_upper: float | None
    intercept_upper: float | None
    slope_lower: float | None
    intercept_lower: float | None
    touches_upper: int
    touches_lower: int
    r2_upper: float | None
    r2_lower: float | None
    parallel_score: float | None
    reason: str | None


def _find_swings(values: np.ndarray, distance: int) -> tuple[np.ndarray, np.ndarray]:
    highs, _ = find_peaks(values, distance=distance)
    lows, _ = find_peaks(-values, distance=distance)
    return highs, lows


def _parallel_score(slope_upper: float, slope_lower: float) -> float:
    avg = (abs(slope_upper) + abs(slope_lower)) / 2
    if avg < 1e-12:
        return 1.0 if abs(slope_upper - slope_lower) < 1e-9 else 0.0
    return float(max(0.0, 1.0 - abs(slope_upper - slope_lower) / avg))


def _fit_line(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Return (slope, intercept, rvalue) — wraps scipy's LinregressResult.

    scipy's typed stub returns a private dataclass with no exposed
    attributes, so we read it positionally via Any-cast.
    """
    res = cast(Any, linregress(x, y))
    return float(res[0]), float(res[1]), float(res[2])


def _classify_direction(slope_upper: float, slope_lower: float) -> ChannelDirection:
    if slope_upper > 0 and slope_lower > 0:
        return "ascending"
    if slope_upper < 0 and slope_lower < 0:
        return "descending"
    if abs(slope_upper) < 1e-6 and abs(slope_lower) < 1e-6:
        return "sideways"
    return "unknown"


def detect_channel(
    close: pd.Series,
    *,
    lookback: int = DEFAULT_LOOKBACK,
    swing_distance: int = DEFAULT_SWING_DISTANCE,
    min_touches: int = DEFAULT_MIN_TOUCHES,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict:
    """Fit a price channel to the last ``lookback`` bars and score it."""
    n_total = len(close)
    if n_total < lookback:
        return asdict(
            Channel(
                found=False, confidence=0.0, direction="unknown",
                lookback=lookback, window_start=None, window_end=None,
                slope_upper=None, intercept_upper=None,
                slope_lower=None, intercept_lower=None,
                touches_upper=0, touches_lower=0,
                r2_upper=None, r2_lower=None, parallel_score=None,
                reason=f"insufficient bars ({n_total} < {lookback})",
            )
        )

    window = close.iloc[-lookback:]
    values = window.to_numpy(dtype=float)
    high_idx, low_idx = _find_swings(values, swing_distance)

    window_start_ts = cast(pd.Timestamp, pd.Timestamp(window.index[0]))
    window_end_ts = cast(pd.Timestamp, pd.Timestamp(window.index[-1]))

    if len(high_idx) < 2 or len(low_idx) < 2:
        return asdict(
            Channel(
                found=False, confidence=0.0, direction="unknown",
                lookback=lookback,
                window_start=window_start_ts,
                window_end=window_end_ts,
                slope_upper=None, intercept_upper=None,
                slope_lower=None, intercept_lower=None,
                touches_upper=int(len(high_idx)),
                touches_lower=int(len(low_idx)),
                r2_upper=None, r2_lower=None, parallel_score=None,
                reason="too few swing points",
            )
        )

    slope_up, intercept_up, rvalue_up = _fit_line(
        high_idx.astype(float), values[high_idx]
    )
    slope_lo, intercept_lo, rvalue_lo = _fit_line(
        low_idx.astype(float), values[low_idx]
    )

    parallel = _parallel_score(slope_up, slope_lo)
    r2_up = rvalue_up ** 2
    r2_lo = rvalue_lo ** 2
    fit = (r2_up + r2_lo) / 2
    touches = min(1.0, (len(high_idx) + len(low_idx)) / (min_touches * 2))
    confidence = parallel * 0.4 + fit * 0.4 + touches * 0.2

    return asdict(
        Channel(
            found=confidence >= threshold
                  and len(high_idx) >= min_touches // 2 + 1
                  and len(low_idx) >= min_touches // 2 + 1,
            confidence=float(confidence),
            direction=_classify_direction(slope_up, slope_lo),
            lookback=lookback,
            window_start=window_start_ts,
            window_end=window_end_ts,
            slope_upper=slope_up,
            intercept_upper=intercept_up,
            slope_lower=slope_lo,
            intercept_lower=intercept_lo,
            touches_upper=int(len(high_idx)),
            touches_lower=int(len(low_idx)),
            r2_upper=r2_up,
            r2_lower=r2_lo,
            parallel_score=parallel,
            reason=None,
        )
    )


def detect_breakout(
    close: pd.Series,
    channel: dict,
    *,
    atr: pd.Series | None = None,
    atr_multiple: float = 0.5,
) -> dict:
    """Given a channel, decide whether the last bar broke out of it.

    If ``atr`` is provided, the close must exceed the channel boundary
    by ``atr_multiple * ATR`` to count as a breakout (filters noise).
    """
    if not channel.get("found"):
        return {
            "found": False,
            "direction": None,
            "reason": "no channel to break out of",
        }
    if channel.get("slope_upper") is None or channel.get("slope_lower") is None:
        return {"found": False, "direction": None, "reason": "channel missing slopes"}

    lookback = int(channel["lookback"])
    last_x = float(lookback - 1)
    upper = channel["slope_upper"] * last_x + channel["intercept_upper"]
    lower = channel["slope_lower"] * last_x + channel["intercept_lower"]
    last_close = float(close.iloc[-1])

    margin = 0.0
    if atr is not None and len(atr) and not pd.isna(atr.iloc[-1]):
        margin = float(atr.iloc[-1]) * atr_multiple

    if last_close > upper + margin:
        return {
            "found": True,
            "direction": "up",
            "close": last_close,
            "boundary": float(upper),
            "margin": margin,
            "confidence": float(channel["confidence"]),
        }
    if last_close < lower - margin:
        return {
            "found": True,
            "direction": "down",
            "close": last_close,
            "boundary": float(lower),
            "margin": margin,
            "confidence": float(channel["confidence"]),
        }
    return {
        "found": False,
        "direction": None,
        "close": last_close,
        "upper": float(upper),
        "lower": float(lower),
    }


def channel_to_annotation_points(
    close: pd.Series, channel: dict
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]] | None:
    """Translate a channel into ``(upper_points, lower_points)`` ready for
    ``Annotation(kind="trendline", points=...)``.

    Points are ``(unix_seconds, price)`` pairs in the **windowed**
    timeframe — endpoints of each trendline at the first and last bar of
    the window.
    """
    if not channel.get("found"):
        return None
    lookback = int(channel["lookback"])
    window = close.iloc[-lookback:]
    if len(window) == 0:
        return None
    x0, x1 = 0.0, float(lookback - 1)
    su, iu = channel["slope_upper"], channel["intercept_upper"]
    sl, il = channel["slope_lower"], channel["intercept_lower"]
    t0 = float(cast(pd.Timestamp, pd.Timestamp(window.index[0])).timestamp())
    t1 = float(cast(pd.Timestamp, pd.Timestamp(window.index[-1])).timestamp())
    upper = [(t0, su * x0 + iu), (t1, su * x1 + iu)]
    lower = [(t0, sl * x0 + il), (t1, sl * x1 + il)]
    return upper, lower
