"""Agent-facing source-introspection tools.

Three tools:
- ``list_sources()`` — what sources exist and what they cover
- ``describe_source(name)`` — one source's full capability
- ``probe_history(symbol, source, kind)`` — hit the API and report the
  actual earliest/latest bar for a specific asset (uses ``refresh=True``
  so the cache doesn't mask real history limits)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pandas as pd

from quant_radar.sources import (
    binance_src,
    catalog,
    fred_src,
    yfinance_src,
)

# Far enough back that any real API will be the limiting factor.
_FAR_BACK = datetime(1970, 1, 1, tzinfo=UTC)


def list_sources() -> list[dict[str, Any]]:
    """Return all sources with their capabilities."""
    return catalog.list_sources()


def describe_source(name: str) -> dict[str, Any] | None:
    """Return one source's full capability, or ``None`` if unknown."""
    return catalog.describe_source(name)


def _probe_frame(
    symbol: str, source: str, kind: str
) -> pd.DataFrame:
    if kind == "ohlcv" and source == "yfinance":
        return yfinance_src.fetch_ohlcv(symbol, start=_FAR_BACK, refresh=True)
    if kind == "ohlcv" and source == "binance":
        return binance_src.fetch_ohlcv(symbol, start=_FAR_BACK, refresh=True)
    if kind == "macro" and source == "fred":
        return fred_src.fetch_macro_series(symbol, start=_FAR_BACK, refresh=True)
    raise ValueError(
        f"probe_history doesn't know how to fetch (source={source!r}, kind={kind!r})"
    )


def probe_history(
    symbol: str, *, source: str = "yfinance", kind: str = "ohlcv"
) -> dict[str, Any]:
    """Return ``{first, last, bars}`` for an asset by hitting the API.

    Uses ``refresh=True`` to bypass the cache, then re-populates it with
    the full history. Subsequent reads via ``fetch_*`` then return
    instantly from the cache.

    Examples:
        >>> probe_history("BTC", source="binance")
        {"symbol": "BTC", "source": "binance", "kind": "ohlcv",
         "first": "2017-08-17T00:00:00+00:00", "last": "...", "bars": 3194}
        >>> probe_history("DGS10", source="fred", kind="macro")
        {"symbol": "DGS10", "source": "fred", "kind": "macro",
         "first": "1962-01-02T00:00:00+00:00", "last": "...", "bars": ...}
    """
    df = _probe_frame(symbol, source, kind)
    if len(df) == 0:
        return {"symbol": symbol, "source": source, "kind": kind, "bars": 0}
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        idx = pd.DatetimeIndex(idx)
    first = cast(pd.Timestamp, idx[0]).isoformat()
    last = cast(pd.Timestamp, idx[-1]).isoformat()
    return {
        "symbol": symbol,
        "source": source,
        "kind": kind,
        "first": first,
        "last": last,
        "bars": int(len(df)),
    }
