"""DataFrame utilities the chat agent can call regardless of source.

Every source adapter normalizes to ``DatetimeIndex`` named ``timestamp``
(see ``quant_radar.sources.base``), so a single helper covers every
frame in the system — no need to teach the agent per-source date
column names.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd


def filter_by_date(
    df: pd.DataFrame,
    *,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
) -> pd.DataFrame:
    """Return rows whose index falls in ``[start, end]`` inclusive.

    ``start`` and ``end`` accept timezone-naive ISO strings or datetimes;
    they are interpreted as UTC to match the canonical index timezone.
    Either bound may be ``None`` for an open-ended slice. The returned
    frame preserves the original index name and column order.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "filter_by_date requires a DatetimeIndex; got "
            f"{type(df.index).__name__}"
        )
    if start is None and end is None:
        return df

    def _coerce(v: datetime | str) -> pd.Timestamp:
        ts = pd.Timestamp(v)
        # Align tz to the index so > / < comparisons don't error.
        if df.index.tz is not None and ts.tz is None:
            ts = ts.tz_localize("UTC")
        elif df.index.tz is None and ts.tz is not None:
            ts = ts.tz_localize(None)
        return ts

    lo = _coerce(start) if start is not None else None
    hi = _coerce(end) if end is not None else None
    mask = pd.Series(True, index=df.index)
    if lo is not None:
        mask &= df.index >= lo
    if hi is not None:
        mask &= df.index <= hi
    return df.loc[mask]
