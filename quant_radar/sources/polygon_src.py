"""Polygon.io adapter — equity OHLCV via their REST API.

Polygon used to be in OpenBB Platform but was removed for licensing,
so per the waterfall step 3 (existing client / raw HTTP) this is a
hand-written adapter using their public REST API.

Free tier: 5 calls/min, ~2 years of historical end-of-day equity data.
The cache TTL + our refresh-button pattern keeps us well under the
limit for normal use.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.cards.spec import DataRef as _DataRef
from quant_radar.sources.base import ttl_for_interval
from quant_radar.sources.base_source import Source, register_source
from quant_radar.sources.catalog import CATALOG

SOURCE = "polygon"
_BASE = "https://api.polygon.io"
_TIMEOUT = 20

# Free tier ceiling: 2 years of EOD daily bars.
_DEFAULT_LOOKBACK_DAYS = 365 * 2 - 7


def _key() -> str:
    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        raise RuntimeError(
            "POLYGON_API_KEY not set. Add it to .env (free signup at polygon.io)."
        )
    return key


def _interval_path(interval: str) -> tuple[int, str]:
    """Map our interval names to Polygon's (multiplier, timespan)."""
    mapping = {
        "1m": (1, "minute"),
        "5m": (5, "minute"),
        "15m": (15, "minute"),
        "1h": (1, "hour"),
        "1d": (1, "day"),
        "1w": (1, "week"),
        "1mo": (1, "month"),
    }
    if interval not in mapping:
        raise ValueError(f"unsupported polygon interval: {interval}")
    return mapping[interval]


def _ticker_for_kind(kind: str, symbol: str) -> str:
    """Polygon aggregates use prefixed tickers per asset class.

    - Equities/ETFs: bare ticker (AAPL, SPY)
    - Forex: ``C:<PAIR>`` (C:EURUSD)
    - Crypto: ``X:<PAIR>`` (X:BTCUSD)
    """
    s = symbol.upper().lstrip("C:").lstrip("X:")
    if kind == "forex":
        return f"C:{s}"
    return s


def _fetch(
    symbol: str, interval: str, kind: str,
    start: datetime | None, end: datetime | None,
) -> pd.DataFrame:
    end = end or datetime.now(UTC)
    start = start or (end - timedelta(days=_DEFAULT_LOOKBACK_DAYS))
    mult, span = _interval_path(interval)
    ticker = _ticker_for_kind(kind, symbol)
    url = (
        f"{_BASE}/v2/aggs/ticker/{ticker}/range/{mult}/{span}"
        f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
    )
    resp = requests.get(
        url, params={"apiKey": _key(), "adjusted": "true", "sort": "asc", "limit": 50000},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("results") or []
    if not results:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp(r["t"], unit="ms", tz="UTC"),
                "open": float(r["o"]),
                "high": float(r["h"]),
                "low": float(r["l"]),
                "close": float(r["c"]),
                "volume": float(r["v"]),
            }
            for r in results
        ]
    )
    df = df.set_index("timestamp").sort_index()
    return df


def fetch_ohlcv(
    symbol: str, *, interval: str = "1d", kind: str = "ohlcv",
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    key = CacheKey(source=SOURCE, kind=kind, name=symbol.upper(), interval=interval)

    def fetcher(start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        return _fetch(symbol, interval, kind, start, end)

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=ttl_for_interval(interval),
    )


def search_tickers(query: str, *, limit: int = 20) -> list[dict]:
    """Search Polygon's ~70k ticker universe by keyword."""
    if not query.strip():
        return []
    try:
        resp = requests.get(
            f"{_BASE}/v3/reference/tickers",
            params={
                "search": query, "active": "true", "limit": max(1, min(limit, 1000)),
                "apiKey": _key(),
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except (requests.RequestException, ValueError, RuntimeError):
        return []
    return [
        {
            "symbol": r.get("ticker"),
            "longname": r.get("name"),
            "exchange": r.get("primary_exchange"),
            "type": r.get("type"),
            "market": r.get("market"),
            "currency": r.get("currency_name"),
        }
        for r in results
        if r.get("ticker")
    ]


def describe_ticker(symbol: str) -> dict | None:
    try:
        resp = requests.get(
            f"{_BASE}/v3/reference/tickers/{symbol.upper()}",
            params={"apiKey": _key()}, timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json().get("results") or {}
    except (requests.RequestException, ValueError, RuntimeError):
        return None
    if not result.get("ticker"):
        return None
    return {
        "symbol": result.get("ticker"),
        "longname": result.get("name"),
        "exchange": result.get("primary_exchange"),
        "type": result.get("type"),
        "market": result.get("market"),
        "currency": result.get("currency_name"),
        "summary": (result.get("description") or "")[:400],
        "list_date": result.get("list_date"),
        "market_cap": result.get("market_cap"),
        "share_class_shares_outstanding": result.get("share_class_shares_outstanding"),
    }


class _PolygonSource(Source):
    capability = CATALOG["polygon"]
    KINDS = ("ohlcv", "forex")

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind in self.KINDS

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        return fetch_ohlcv(
            ref.name, interval=ref.interval, kind=ref.kind,
            start=ref.start, end=ref.end, refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        return search_tickers(query, limit=limit)

    def describe(self, name: str) -> dict | None:
        return describe_ticker(name)


register_source(_PolygonSource())
