"""FRED adapter — macro series via the public CSV endpoint (no API key required).

Uses ``https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>``, which
serves the same data as the API for free and without authentication.
"""

from __future__ import annotations

from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.sources.base import TTL_MACRO_SEC

SOURCE = "fred"
_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_TIMEOUT = 15


def _fetch(series_id: str, start: datetime | None, end: datetime | None) -> pd.DataFrame:
    params: dict[str, str] = {"id": series_id}
    if start is not None:
        params["cosd"] = start.date().isoformat()
    if end is not None:
        params["coed"] = end.date().isoformat()
    resp = requests.get(_CSV_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    raw = pd.read_csv(StringIO(resp.text))
    if raw.empty:
        return pd.DataFrame()
    date_col = raw.columns[0]
    value_col = raw.columns[1]
    out = pd.DataFrame({"value": pd.to_numeric(raw[value_col], errors="coerce")})
    out.index = pd.to_datetime(raw[date_col], utc=True)
    out.index.name = "timestamp"
    out = out.dropna()
    return out.sort_index()


def fetch_macro_series(
    series_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch a FRED macro series (e.g. ``DGS10``, ``CPIAUCSL``), cached on disk."""
    key = CacheKey(source=SOURCE, kind="macro", name=series_id, interval="1d")

    def fetcher(start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        return _fetch(series_id, start, end)

    return get_or_fetch(
        key,
        fetcher,
        start=start,
        end=end,
        refresh=refresh,
        ttl_seconds=TTL_MACRO_SEC,
    )
