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
    kind_coverage as _kind_coverage,
    kind_relationships as _kind_relationships,
    yfinance_src,
)
from quant_radar.sources.base_source import all_sources, get_source

# Far enough back that any real API will be the limiting factor.
_FAR_BACK = datetime(1970, 1, 1, tzinfo=UTC)


def list_sources() -> list[dict[str, Any]]:
    """Return all sources with their capabilities."""
    return catalog.list_sources()


def describe_source(name: str) -> dict[str, Any] | None:
    """Return one source's full capability, or ``None`` if unknown."""
    return catalog.describe_source(name)


def list_kind_relationships() -> list[dict[str, Any]]:
    """Every cross-kind relationship (e.g. social_sentiment ↔ sentiment).

    Use this at session start to know which kinds the agent should
    pull together. See ``quant_radar/sources/kind_relationships.py``.
    """
    return _kind_relationships.list_relationships()


def relationships_for_kind(kind: str) -> list[dict[str, Any]]:
    """All cross-kind relationships that involve ``kind``.

    When the agent has chosen a primary kind (e.g. ``ohlcv``), this
    surfaces every other kind that would enrich the read (news,
    sentiment, social_sentiment, ...).
    """
    return _kind_relationships.relationships_for_kind(kind)


def describe_kind_coverage(kind: str) -> dict[str, Any] | None:
    """Cross-source comparison for one ``kind`` (e.g. sentiment).

    Returns the routing record from ``kind_coverage.py``: which sources
    serve this kind, their tiers, rate limits, signal quality, and the
    default routing chain. ``None`` when the kind is single-source.
    """
    return _kind_coverage.get_coverage(kind)


def list_covered_kinds() -> list[str]:
    """Kinds with multi-source coverage declared in ``kind_coverage.py``."""
    return _kind_coverage.list_covered_kinds()


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


def search_source(
    source: str, query: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    """Generic discovery — search any registered source by keyword.

    Every adapter implements the same ``search(query, limit)`` contract,
    so this dispatches by source name. Use it when the user names a
    source explicitly ("look up XLF on yfinance", "find me a Binance
    pair for SUI"). Each hit always has ``symbol`` + (when available)
    ``longname``; extra source-specific keys (frequency/units/notes for
    FRED, exchange/sector for yfinance, base/quote for Binance) come
    along for free.

    Returns ``[]`` if the source is unknown or upstream is unreachable.
    """
    src = get_source(source)
    if src is None:
        return []
    return src.search(query, limit=limit)


def describe_symbol(source: str, name: str) -> dict[str, Any] | None:
    """Generic per-symbol metadata — works on any registered source.

    Returns the long-form description for one symbol/series on
    ``source``. For FRED that's title/notes/units; for yfinance it's
    longName/sector/industry/exchange/summary; for Binance it's
    base/quote with a long pair name from CoinGecko.

    Returns ``None`` if the symbol isn't recognized or the upstream
    doesn't expose metadata.
    """
    src = get_source(source)
    if src is None:
        return None
    return src.describe(name)


def list_all_symbols(
    source: str, *, limit: int | None = None
) -> list[dict[str, Any]]:
    """Enumerate every symbol/series ``source`` offers.

    Only practical for sources with bounded catalogs (currently Binance).
    Returns ``[]`` for sources with unbounded catalogs (FRED, yfinance)
    — use ``search_source(source, query)`` for those instead.
    """
    src = get_source(source)
    if src is None:
        return []
    return src.list_all(limit=limit)


def list_searchable_sources() -> list[dict[str, Any]]:
    """Quick sanity probe — which sources currently support search?

    The ABC requires every source to *define* ``search`` and
    ``describe``, but a source may legitimately return ``[]`` /
    ``None`` (e.g. deferred or unreachable). This calls each one with a
    no-op query to see who actually responds.
    """
    return [
        {
            "source": s.name,
            "status": s.capability.status,
            "kinds": s.capability.kinds,
        }
        for s in all_sources()
    ]


# --- Convenience wrappers ----------------------------------------------
# Thin shortcuts around search_source / describe_symbol for the agent's
# most common discovery flows. Reach for these when the source is fixed
# at call time.


def search_fred(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """FRED keyword search (~800k series). Requires ``FRED_API_KEY``."""
    return search_source("fred", query, limit=limit)


def search_yfinance(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """yfinance keyword search via Yahoo's quote endpoint.

    Yahoo doesn't expose a full exchange list, so this is the only way
    to discover symbols. Returns longname/exchange/quoteType/sector.
    """
    return search_source("yfinance", query, limit=limit)


def search_binance(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Binance spot-pair search. Matches against pair symbol + base
    long name (e.g. "Bitcoin" or "BTC" both find BTCUSDT)."""
    return search_source("binance", query, limit=limit)


def list_binance_pairs(
    quote: str | None = None, *, status: str = "TRADING"
) -> list[dict[str, Any]]:
    """Enumerate Binance spot pairs (filterable by quote currency).

    Pass ``quote="USDT"`` for USDT pairs only. Long names from CoinGecko
    are included per pair.
    """
    return binance_src.list_pairs(quote=quote, status=status)
