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


def _fetch(
    symbol: str, interval: str, start: datetime | None, end: datetime | None
) -> pd.DataFrame:
    if start is None:
        start = _default_start(interval)
    raw = yf.download(
        tickers=symbol,
        start=start,
        end=end,
        interval=_to_yf_interval(interval),
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
