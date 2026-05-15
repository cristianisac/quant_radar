"""Moving-average state analysis.

``analyze_moving_averages`` answers the user-visible questions from the
spec:
- price above or below the 50d / 200d
- 50d above or below the 200d
- 50d catching up to the 200d from below
- recent golden / death cross
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, cast

import pandas as pd

from quant_radar.analytics.indicators import sma

Position = Literal["above", "below", "equal"]


@dataclass
class MAState:
    fast_period: int
    slow_period: int
    last_close: float | None
    last_fast: float | None
    last_slow: float | None
    price_vs_fast: Position | None
    price_vs_slow: Position | None
    fast_vs_slow: Position | None
    fast_slope: float | None
    slow_slope: float | None
    fast_catching_up_from_below: bool
    golden_cross_recent: bool
    death_cross_recent: bool
    insufficient_data: bool
    summary: str


def _position(a: float, b: float) -> Position:
    if a > b:
        return "above"
    if a < b:
        return "below"
    return "equal"


def _slope(ma: pd.Series, lookback: int) -> float | None:
    if len(ma.dropna()) <= lookback:
        return None
    last = ma.iloc[-1]
    past = ma.iloc[-1 - lookback]
    if pd.isna(last) or pd.isna(past):
        return None
    return float((last - past) / lookback)


def _detect_recent_crosses(
    fast: pd.Series, slow: pd.Series, lookback: int
) -> tuple[bool, bool]:
    diff = (fast - slow).dropna().iloc[-lookback - 1 :]
    if len(diff) < 2:
        return False, False
    prev = diff.shift(1)
    golden = bool(((prev < 0) & (diff > 0)).any())
    death = bool(((prev > 0) & (diff < 0)).any())
    return golden, death


def _build_summary(state: MAState, asset: str | None) -> str:
    name = asset or "the series"
    if state.insufficient_data:
        return (
            f"Not enough data to compute {state.fast_period}d / "
            f"{state.slow_period}d moving averages for {name}."
        )
    parts = [
        f"{name} is {state.price_vs_fast} its {state.fast_period}d MA",
        f"and {state.price_vs_slow} its {state.slow_period}d MA.",
        f"The {state.fast_period}d MA is {state.fast_vs_slow} the "
        f"{state.slow_period}d MA.",
    ]
    if state.fast_catching_up_from_below:
        parts.append(
            f"The {state.fast_period}d MA is catching up to the "
            f"{state.slow_period}d MA from below."
        )
    if state.golden_cross_recent:
        parts.append("A golden cross occurred recently.")
    if state.death_cross_recent:
        parts.append("A death cross occurred recently.")
    return " ".join(parts)


def analyze_moving_averages(
    close: pd.Series,
    *,
    fast_period: int = 50,
    slow_period: int = 200,
    cross_lookback: int = 20,
    slope_lookback: int = 20,
    asset: str | None = None,
) -> dict:
    """Return a dict describing MA state for the given close series."""
    ma_fast = sma(close, fast_period)
    ma_slow = sma(close, slow_period)

    last_close_val = float(close.iloc[-1]) if len(close) else None
    last_fast_val = ma_fast.iloc[-1] if len(ma_fast) else None
    last_slow_val = ma_slow.iloc[-1] if len(ma_slow) else None

    insufficient = (
        last_close_val is None
        or last_fast_val is None
        or last_slow_val is None
        or pd.isna(last_fast_val)
        or pd.isna(last_slow_val)
    )

    if insufficient:
        state = MAState(
            fast_period=fast_period,
            slow_period=slow_period,
            last_close=last_close_val,
            last_fast=None,
            last_slow=None,
            price_vs_fast=None,
            price_vs_slow=None,
            fast_vs_slow=None,
            fast_slope=None,
            slow_slope=None,
            fast_catching_up_from_below=False,
            golden_cross_recent=False,
            death_cross_recent=False,
            insufficient_data=True,
            summary="",
        )
        state.summary = _build_summary(state, asset)
        return asdict(state)

    last_fast_f = float(cast(float, last_fast_val))
    last_slow_f = float(cast(float, last_slow_val))
    last_close_f = cast(float, last_close_val)

    fast_slope = _slope(ma_fast, slope_lookback)
    slow_slope = _slope(ma_slow, slope_lookback)

    catching_up = (
        last_fast_f < last_slow_f
        and fast_slope is not None
        and slow_slope is not None
        and fast_slope > slow_slope
    )

    golden, death = _detect_recent_crosses(ma_fast, ma_slow, cross_lookback)

    state = MAState(
        fast_period=fast_period,
        slow_period=slow_period,
        last_close=last_close_f,
        last_fast=last_fast_f,
        last_slow=last_slow_f,
        price_vs_fast=_position(last_close_f, last_fast_f),
        price_vs_slow=_position(last_close_f, last_slow_f),
        fast_vs_slow=_position(last_fast_f, last_slow_f),
        fast_slope=fast_slope,
        slow_slope=slow_slope,
        fast_catching_up_from_below=bool(catching_up),
        golden_cross_recent=bool(golden),
        death_cross_recent=bool(death),
        insufficient_data=False,
        summary="",
    )
    state.summary = _build_summary(state, asset)
    return asdict(state)
