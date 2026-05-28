"""yfinance adapter — OHLCV for equities, ETFs, FX, indices, BTC-USD etc."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import yfinance as yf

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.sources.base import ttl_for_interval

# yfinance.download defaults to period="1mo" when both start and end are
# absent. That's not enough bars for a 200d SMA, which broke the very
# first user query in the E2E run. Pick a sane default per interval.
_DEFAULT_LOOKBACK = {
    "1m": timedelta(days=7),
    "5m": timedelta(days=60),
    "15m": timedelta(days=60),
    "1h": timedelta(days=730),
    "1d": timedelta(days=5 * 365),
    "1w": timedelta(days=10 * 365),
    "1mo": timedelta(days=25 * 365),
}

SOURCE = "yfinance"

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1wk",
    "1mo": "1mo",
}


def _to_yf_interval(interval: str) -> str:
    if interval not in _INTERVAL_MAP:
        raise ValueError(f"unsupported interval for yfinance: {interval}")
    return _INTERVAL_MAP[interval]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    cols = [c for c in ("open", "high", "low", "close", "adj_close", "volume") if c in out.columns]
    out.index.name = "timestamp"
    return out.loc[:, cols]  # cache layer handles tz/sort


def _default_start(interval: str) -> datetime:
    delta = _DEFAULT_LOOKBACK.get(interval, timedelta(days=5 * 365))
    return datetime.now(UTC) - delta


# yfinance silently returns ~30 bars when `start` is older than its
# internal cutoff for the ticker — e.g. AAPL with start=1970-01-01
# returns only the last month. Switch to ``period="max"`` for these
# "give me everything" requests; it's reliable across tickers.
_PERIOD_MAX_CUTOFF = timedelta(days=40 * 365)


def _fetch(
    symbol: str, interval: str, start: datetime | None, end: datetime | None
) -> pd.DataFrame:
    if start is None:
        start = _default_start(interval)

    use_period_max = (
        end is None
        and (datetime.now(UTC) - start) > _PERIOD_MAX_CUTOFF
    )

    yf_interval = _to_yf_interval(interval)
    if use_period_max:
        raw = yf.download(
            tickers=symbol,
            period="max",
            interval=yf_interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    else:
        raw = yf.download(
            tickers=symbol,
            start=start,
            end=end,
            interval=yf_interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return _normalize(raw)


def fetch_ohlcv(
    symbol: str,
    *,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch OHLCV bars for ``symbol`` from yfinance, cached on disk."""
    key = CacheKey(source=SOURCE, kind="ohlcv", name=symbol, interval=interval)

    def fetcher(start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        return _fetch(symbol, interval, start, end)

    return get_or_fetch(
        key,
        fetcher,
        start=start,
        end=end,
        refresh=refresh,
        ttl_seconds=ttl_for_interval(interval),
    )


def search_symbols(query: str, *, limit: int = 10) -> list[dict]:
    """Search Yahoo Finance for matching tickers by keyword.

    Returns ``[{symbol, longname, shortname, exchange, quote_type,
    sector, industry, score}, ...]``. Lets the agent answer the
    user-said-"Apple"-find-AAPL flow when the exact ticker isn't known.

    Yahoo doesn't expose a full exchange listing, so this is the only
    discovery surface for yfinance — there's no "enumerate everything".

    Returns ``[]`` silently if the upstream call fails.
    """
    if not query.strip():
        return []
    try:
        s = yf.Search(
            query,
            max_results=max(1, min(int(limit), 50)),
            news_count=0,
            lists_count=0,
            include_research=False,
            include_nav_links=False,
            include_cultural_assets=False,
            raise_errors=False,
        )
        quotes = s.quotes or []
    except Exception:
        return []
    return [
        {
            "symbol": q.get("symbol"),
            "longname": q.get("longname") or q.get("shortname"),
            "shortname": q.get("shortname"),
            "exchange": q.get("exchDisp") or q.get("exchange"),
            "quote_type": q.get("quoteType"),
            "sector": q.get("sectorDisp") or q.get("sector"),
            "industry": q.get("industryDisp") or q.get("industry"),
            "score": q.get("score"),
        }
        for q in quotes
        if q.get("symbol")
    ]


# --- Source-ABC adapter ---------------------------------------------------
# Registered at import time so ``hydrate`` can dispatch via the registry.

from quant_radar.cards.spec import DataRef as _DataRef  # noqa: E402
from quant_radar.sources.base_source import Source, register_source  # noqa: E402
from quant_radar.sources.catalog import CATALOG  # noqa: E402


def _describe_symbol(symbol: str) -> dict | None:
    """Return longName/sector/industry/exchange for one yfinance symbol."""
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return None
    long_name = info.get("longName") or info.get("shortName")
    if not long_name:
        # Treat "no metadata" as "not a real symbol" — Yahoo returns a
        # mostly-empty dict for unknown tickers.
        return None
    return {
        "symbol": symbol,
        "longname": long_name,
        "shortname": info.get("shortName"),
        "exchange": info.get("fullExchangeName") or info.get("exchange"),
        "quote_type": info.get("quoteType"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "currency": info.get("currency"),
        "summary": (info.get("longBusinessSummary") or "")[:400],
    }


_KINDS = ("ohlcv", "futures_aggregate")


class _YFinanceSource(Source):
    """Multi-kind yfinance adapter.

    - ``ohlcv``: per-symbol OHLCV history (equities, ETFs, indices,
      FX with `=X`, crypto with `*-USD`, futures with `=F`).
    - ``futures_aggregate``: enumerates every active CME crypto futures
      contract month for an asset root (e.g. ``BTC``) and sums daily
      volume + notional separately for standard vs micro variants.
    """

    capability = CATALOG["yfinance"]

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind in _KINDS

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        if ref.kind == "futures_aggregate":
            # Late import — cme_futures_src lives in the same package and
            # importing at module top creates a circular ref through
            # base_source.
            from quant_radar.sources.cme_futures_src import (
                fetch_cme_futures_volume,
            )
            return fetch_cme_futures_volume(
                ref.name, start=ref.start, end=ref.end, refresh=refresh,
            )
        return fetch_ohlcv(
            ref.name,
            interval=ref.interval,
            start=ref.start,
            end=ref.end,
            refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        return search_symbols(query, limit=limit)

    def describe(self, name: str) -> dict | None:
        return _describe_symbol(name)


register_source(_YFinanceSource())
