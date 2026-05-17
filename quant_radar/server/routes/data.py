"""Time-series hydration — turns a DataRef into Plotly-ready columns.

Returns columnar JSON (``timestamps + columns``) rather than records
because Plotly.js consumes arrays per trace. This is the only endpoint
that can return a large payload; cache TTL still applies on the
underlying fetchers.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

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
    columns = {
        col: [float(v) if pd.notna(v) else float("nan") for v in df[col]]
        for col in df.columns
    }
    return TimeSeriesResponse(
        source=source, kind=kind, name=name, interval=interval,
        timestamps=timestamps, columns=columns, display_name=display_name,
    )


def _resolve_display_name(source: str, name: str) -> str | None:
    if source == "fred":
        return fred_src.series_title(name)
    return None
