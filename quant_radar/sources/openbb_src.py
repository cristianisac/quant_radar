"""OpenBB-backed adapters for FMP + Tiingo.

Both providers are in the OpenBB Platform's bundled equity coverage, so
the adapter is a thin parametric wrapper around
``obb.equity.price.historical(provider="<name>")`` + ``obb.equity.search``
+ ``obb.equity.profile``. One ~30-line subclass per provider — adding
Intrinio, Alpha Vantage, etc. later is the same pattern.

Polygon lives in ``polygon_src.py`` (raw HTTP) — OpenBB removed Polygon
from its bundled providers due to licensing, so the waterfall picks
step 3 (existing client / raw HTTP) for it.

API keys flow via the standard .env → docker --env-file → OPENBB
credentials store wiring below. Idempotent at module import.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import cast

import pandas as pd

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.cards.spec import DataRef as _DataRef
from quant_radar.sources.base import ttl_for_interval
from quant_radar.sources.base_source import Source, register_source
from quant_radar.sources.catalog import CATALOG


def _wire_openbb_credentials() -> None:
    """Map our .env keys into OpenBB's credentials store.

    Our env vars are ``<PROVIDER>_API_KEY`` (FMP_API_KEY, TIINGO_API_KEY,
    POLYGON_API_KEY). OpenBB uses slightly different names per provider
    (e.g. ``tiingo_token`` not ``tiingo_api_key``). Map them once at
    import time so the rest of the adapter can call ``obb.*`` without
    worrying about credentials.
    """
    from openbb import obb

    mapping = {
        "fmp_api_key": "FMP_API_KEY",
        "tiingo_token": "TIINGO_API_KEY",
        "polygon_api_key": "POLYGON_API_KEY",  # honored if/when openbb-polygon is installed
        "fred_api_key": "FRED_API_KEY",
        "finnhub_api_key": "FINNHUB_API_KEY",
    }
    for openbb_name, env_var in mapping.items():
        value = os.environ.get(env_var)
        if value:
            try:
                setattr(obb.user.credentials, openbb_name, value)
            except Exception:
                # Credential name unsupported in installed version — skip silently.
                pass


_wire_openbb_credentials()


# OpenBB ships canonical OHLCV columns plus per-provider extras (vwap,
# adj_open, etc.). Normalize to the schema we declared in the catalog.
_CANONICAL = ("open", "high", "low", "close", "volume")


def _fetch_via_openbb(
    provider: str, symbol: str,
    start: datetime | None, end: datetime | None, interval: str,
) -> pd.DataFrame:
    from openbb import obb

    kwargs: dict[str, object] = {
        "symbol": symbol, "provider": provider, "interval": interval,
    }
    if start is not None:
        kwargs["start_date"] = start.strftime("%Y-%m-%d")
    if end is not None:
        kwargs["end_date"] = end.strftime("%Y-%m-%d")

    result = obb.equity.price.historical(**kwargs)  # type: ignore[arg-type]
    df = result.to_df()
    if df.empty:
        return df
    # OpenBB returns the index named "date" with object dtype (string
    # dates like "2026-05-21"). Normalize to a tz-aware DatetimeIndex
    # named "timestamp" so the cache layer and downstream tools see the
    # same shape every other adapter produces.
    df.columns = [str(c).lower() for c in df.columns]
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "timestamp"
    keep = [c for c in _CANONICAL if c in df.columns]
    return df[keep]


def _search_via_openbb(provider: str, query: str, limit: int) -> list[dict]:
    from openbb import obb

    try:
        result = obb.equity.search(query=query, provider=provider)
        df = result.to_df()
        if df.empty:
            return []
    except Exception:
        return []
    out: list[dict] = []
    for _, row in df.head(limit).iterrows():
        d = row.to_dict()
        out.append({
            "symbol": d.get("symbol") or d.get("ticker"),
            "longname": d.get("name") or d.get("longname") or d.get("long_name"),
            "exchange": d.get("exchange") or d.get("exchange_short_name"),
        })
    return [h for h in out if h.get("symbol")]


def _describe_via_openbb(provider: str, symbol: str) -> dict | None:
    from openbb import obb

    try:
        result = obb.equity.profile(symbol=symbol, provider=provider)
        df = result.to_df()
        if df.empty:
            return None
    except Exception:
        return None
    row = df.iloc[0].to_dict()
    return {
        "symbol": symbol,
        "longname": row.get("name") or row.get("longname") or row.get("long_name"),
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "exchange": row.get("exchange"),
        "summary": (row.get("description") or row.get("long_description") or "")[:400],
    }


class _OpenBBOHLCVSource(Source):
    """Parametric base. Concrete subclasses set PROVIDER + capability."""

    PROVIDER: str = ""  # override in subclass

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == self.PROVIDER and ref.kind == "ohlcv"

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        key = CacheKey(
            source=self.PROVIDER, kind="ohlcv",
            name=ref.name, interval=ref.interval,
        )

        def fetcher(start, end):
            return _fetch_via_openbb(self.PROVIDER, ref.name, start, end, ref.interval)

        return get_or_fetch(
            key, fetcher, start=ref.start, end=ref.end,
            refresh=refresh, ttl_seconds=ttl_for_interval(ref.interval),
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        return _search_via_openbb(self.PROVIDER, query, limit)

    def describe(self, name: str) -> dict | None:
        return _describe_via_openbb(self.PROVIDER, name)


class _FMPSource(_OpenBBOHLCVSource):
    PROVIDER = "fmp"
    capability = CATALOG["fmp"]


class _TiingoSource(_OpenBBOHLCVSource):
    PROVIDER = "tiingo"
    capability = CATALOG["tiingo"]


register_source(_FMPSource())
register_source(_TiingoSource())
