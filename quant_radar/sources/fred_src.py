"""FRED adapter — macro series via the public CSV endpoint (no API key required).

Uses ``https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>``, which
serves the same data as the API for free and without authentication.

The optional ``/fred/series`` JSON endpoint *does* need a key, but only
for the human-readable ``title`` field. We read ``FRED_API_KEY`` from
the environment when present and cache titles in-process so the UI can
show "DGS10 — 10-Year Treasury Constant Maturity Rate".
"""

from __future__ import annotations

import os
from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.sources.base import TTL_MACRO_SEC

SOURCE = "fred"
_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_SERIES_URL = "https://api.stlouisfed.org/fred/series"
_TIMEOUT = 15

_TITLE_CACHE: dict[str, str] = {}


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


def series_title(series_id: str) -> str | None:
    """Return FRED's human-readable title for ``series_id``, or None.

    Cached in-process. Returns None silently if the key is missing or
    the upstream is unreachable — the UI falls back to the raw symbol.
    """
    if series_id in _TITLE_CACHE:
        return _TITLE_CACHE[series_id]
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.get(
            _SERIES_URL,
            params={"series_id": series_id, "api_key": api_key, "file_type": "json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        title = payload.get("seriess", [{}])[0].get("title")
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None
    if isinstance(title, str) and title:
        # FRED titles are often phrased like
        # "Market Yield on U.S. Treasuries..., Quoted on an Investment Basis";
        # the qualifier after the first comma rarely adds signal at a
        # glance, so trim it for the card legend.
        short = title.split(",", 1)[0].strip()
        _TITLE_CACHE[series_id] = short
        return short
    return None
