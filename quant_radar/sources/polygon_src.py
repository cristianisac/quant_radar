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


# --- Options chain (kind="options_chain") -------------------------------
#
# Polygon /v3/reference/options/contracts is free-tier accessible. For
# a card-view preview we return a flat table of upcoming contracts:
# strike, expiration, call/put, primary exchange, the contract ticker
# (which the agent can pass to /v2/aggs to get historical prices).
#
# Indexed by expiration_date so chains naturally sort to the near
# expiries first. The free tier caps per-call results to ~1000.


def fetch_options_chain(
    underlying: str, *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Options contracts list for ``underlying``.

    Returns one row per available contract: strike, contract type
    (call/put), expiration_date (index), exchange, shares_per_contract,
    the contract ticker (O:<sym><exp><CP><strike>).

    Optionally filters by ``start`` / ``end`` on the expiration date so
    the user can request "options expiring next 30 days" by passing a
    start of today and end of today+30d.
    """

    key = CacheKey(
        source=SOURCE, kind="options_chain",
        name=underlying.upper(), interval="event",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        params: dict[str, object] = {
            "underlying_ticker": underlying.upper(),
            "limit": 1000,
            "order": "asc",
            "sort": "expiration_date",
            "apiKey": _key(),
        }
        if start is not None:
            params["expiration_date.gte"] = start.strftime("%Y-%m-%d")
        if end is not None:
            params["expiration_date.lte"] = end.strftime("%Y-%m-%d")
        resp = requests.get(
            f"{_BASE}/v3/reference/options/contracts",
            params=params, timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        items = (resp.json() or {}).get("results") or []
        rows: list[dict[str, object]] = []
        for it in items:
            try:
                ts = pd.to_datetime(it.get("expiration_date"), utc=True)
            except Exception:
                continue
            rows.append({
                "timestamp": ts,
                "contract_type": it.get("contract_type") or "",
                "strike_price": float(it.get("strike_price") or 0.0),
                "contract_ticker": it.get("ticker") or "",
                "primary_exchange": it.get("primary_exchange") or "",
                "shares_per_contract": int(it.get("shares_per_contract") or 0),
                "exercise_style": it.get("exercise_style") or "",
            })
        if not rows:
            return pd.DataFrame(columns=[
                "contract_type", "strike_price", "contract_ticker",
                "primary_exchange", "shares_per_contract", "exercise_style",
            ])
        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        df.index.name = "timestamp"
        return df

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=ttl_for_interval("1d"),
    )


# --- Per-ticker news ---------------------------------------------------
#
# Polygon's /v2/reference/news endpoint serves rich article rows on the
# free tier: title, author, publisher, article_url, image_url, tickers,
# keywords, insights (LLM-derived sentiment + sentiment_reasoning).
# Indexed by published_utc.


def fetch_ticker_news(
    ticker: str, *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Per-ticker news for ``ticker`` via /v2/reference/news."""

    key = CacheKey(
        source=SOURCE, kind="ticker_news",
        name=ticker.upper(), interval="event",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        params: dict[str, object] = {
            "ticker": ticker.upper(),
            "limit": 50,
            "order": "desc",
            "sort": "published_utc",
            "apiKey": _key(),
        }
        if start is not None:
            params["published_utc.gte"] = start.strftime("%Y-%m-%d")
        if end is not None:
            params["published_utc.lte"] = end.strftime("%Y-%m-%d")
        resp = requests.get(
            f"{_BASE}/v2/reference/news", params=params, timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        items = (resp.json() or {}).get("results") or []
        rows: list[dict[str, object]] = []
        for it in items:
            try:
                ts = pd.to_datetime(it.get("published_utc"), utc=True)
            except Exception:
                continue
            pub = it.get("publisher") or {}
            publisher_name = pub.get("name") if isinstance(pub, dict) else ""
            insights = it.get("insights") or []
            # Pull this ticker's insight from the array (Polygon attaches
            # one entry per tagged ticker per article).
            this_insight: dict[str, object] = {}
            for ins in insights:
                if (ins.get("ticker") or "").upper() == ticker.upper():
                    this_insight = ins
                    break
            rows.append({
                "timestamp": ts,
                "title": (it.get("title") or "")[:200],
                "author": it.get("author") or "",
                "publisher": publisher_name or "",
                "article_url": it.get("article_url") or "",
                "sentiment": (this_insight.get("sentiment") or ""),
                "sentiment_reasoning": (this_insight.get("sentiment_reasoning") or "")[:200],
                "keywords": ", ".join(it.get("keywords") or [])[:200],
            })
        if not rows:
            return pd.DataFrame(columns=[
                "title", "author", "publisher", "article_url",
                "sentiment", "sentiment_reasoning", "keywords",
            ])
        df = pd.DataFrame(rows).set_index("timestamp").sort_index(ascending=False)
        df.index.name = "timestamp"
        return df

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=ttl_for_interval("1d"),
    )


class _PolygonSource(Source):
    capability = CATALOG["polygon"]
    KINDS = ("ohlcv", "forex", "ticker_news", "options_chain")

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind in self.KINDS

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        if ref.kind == "ticker_news":
            return fetch_ticker_news(
                ref.name, start=ref.start, end=ref.end, refresh=refresh,
            )
        if ref.kind == "options_chain":
            return fetch_options_chain(
                ref.name, start=ref.start, end=ref.end, refresh=refresh,
            )
        return fetch_ohlcv(
            ref.name, interval=ref.interval, kind=ref.kind,
            start=ref.start, end=ref.end, refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        return search_tickers(query, limit=limit)

    def describe(self, name: str) -> dict | None:
        return describe_ticker(name)


register_source(_PolygonSource())
