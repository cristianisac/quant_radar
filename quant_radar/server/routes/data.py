"""Time-series hydration — turns a DataRef into Plotly-ready columns.

Returns columnar JSON (``timestamps + columns``) rather than records
because Plotly.js consumes arrays per trace. This is the only endpoint
that can return a large payload; cache TTL still applies on the
underlying fetchers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import pandas as pd
from fastapi import APIRouter, HTTPException

from quant_radar.cards.spec import DataRef
from quant_radar.server.schemas import TimeSeriesResponse
from quant_radar.sources import fred_src
from quant_radar.sources.hydrate import hydrate

router = APIRouter()


@router.get("/data", response_model=TimeSeriesResponse)
def get_data(
    source: str,
    kind: str,
    name: str,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> TimeSeriesResponse:
    ref = DataRef(
        source=source, kind=kind, name=name, interval=interval, start=start, end=end,
    )
    try:
        df = hydrate(ref, refresh=refresh)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    display_name = _resolve_display_name(source, name)

    if not isinstance(df.index, pd.DatetimeIndex) or len(df) == 0:
        return TimeSeriesResponse(
            source=source, kind=kind, name=name, interval=interval,
            timestamps=[], columns={}, display_name=display_name,
        )

    timestamps = [cast(pd.Timestamp, ts).to_pydatetime() for ts in df.index]
    # Per-column serialization. Numeric cols become floats (NaN preserved
    # as JSON null via Pydantic's None handling). Non-numeric cols (e.g.
    # `fiscal_period: "Q2"`, `reported_currency: "USD"`) pass through as
    # strings — fundamentals frames mix both. Datetimes serialize via
    # ISO string. None when the underlying value is NaN/NA.
    columns: dict[str, list[Any]] = {}
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            columns[col] = [
                float(v) if pd.notna(v) else None for v in series
            ]
        elif pd.api.types.is_datetime64_any_dtype(series):
            columns[col] = [
                cast(pd.Timestamp, v).isoformat() if pd.notna(v) else None
                for v in series
            ]
        else:
            columns[col] = [
                None if pd.isna(v) else (v if isinstance(v, str) else str(v))
                for v in series
            ]
    return TimeSeriesResponse(
        source=source, kind=kind, name=name, interval=interval,
        timestamps=timestamps, columns=columns, display_name=display_name,
    )


def _resolve_display_name(source: str, name: str) -> str | None:
    if source == "fred":
        return fred_src.series_title(name)
    return None
