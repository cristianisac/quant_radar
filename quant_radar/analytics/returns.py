"""Period-over-period returns over a time series.

Given a close-price Series with a ``DatetimeIndex``, compute returns for
named periods (``1d``, ``1w``, ``1m``, ``1y``, ``yoy``, ``ytd``). For each
period the function locates the last observation at or before the target
historical date and computes ``(last - base) / base``.

If the series doesn't extend back far enough for a given period, that
period's return is ``None``.
"""

from __future__ import annotations

from typing import Final, cast

import pandas as pd

DEFAULT_PERIODS: Final[tuple[str, ...]] = ("1d", "1w", "1m", "1y", "yoy", "ytd")


def _target_timestamp(last_ts: pd.Timestamp, period: str) -> pd.Timestamp | None:
    if period == "1d":
        return cast(pd.Timestamp, last_ts - pd.Timedelta(days=1))
    if period == "1w":
        return cast(pd.Timestamp, last_ts - pd.Timedelta(days=7))
    if period == "1m":
        return cast(pd.Timestamp, last_ts - pd.DateOffset(months=1))
    if period in ("1y", "yoy"):
        return cast(pd.Timestamp, last_ts - pd.DateOffset(years=1))
    if period == "ytd":
        return cast(
            pd.Timestamp,
            pd.Timestamp(year=last_ts.year, month=1, day=1, tz=last_ts.tz),
        )
    return None


def compute_returns(
    series: pd.Series,
    periods: tuple[str, ...] | list[str] = DEFAULT_PERIODS,
) -> dict[str, float | None]:
    """Return percentage change vs the closest historical bar per period."""
    if len(series) == 0:
        return dict.fromkeys(periods)
    last_ts = cast(pd.Timestamp, series.index[-1])
    last_val = float(series.iloc[-1])
    out: dict[str, float | None] = {}
    for p in periods:
        target = _target_timestamp(last_ts, p)
        if target is None:
            out[p] = None
            continue
        past = series.loc[:target]
        if len(past) == 0:
            out[p] = None
            continue
        base = float(past.iloc[-1])
        out[p] = (last_val - base) / base if base != 0 else None
    return out
