"""Binance public spot API adapter — free, no key, no signup.

Endpoint: ``GET https://api.binance.com/api/v3/klines``. Free tier
allows up to 1200 weight/min from one IP, and OHLCV requests cost 1-2
each, so realistic use never hits the limit.

Symbol convention: case-insensitive. Pre-formed pairs are passed
through (``BTCUSDT``, ``ETHBTC``). Bare base symbols ('BTC', 'ETH',
'SOL') are mapped to '<base>USDT' since that's almost always what the
user means.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import cast

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.sources.base import ttl_for_interval

SOURCE = "binance"
_BASE = "https://api.binance.com/api/v3/klines"
_TIMEOUT = 15
_LIMIT_MAX = 1000

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1w",
    "1mo": "1M",
}

_DEFAULT_LOOKBACK = {
    "1m": timedelta(days=2),
    "5m": timedelta(days=30),
    "15m": timedelta(days=60),
    "1h": timedelta(days=365),
    "1d": timedelta(days=5 * 365),
    "1w": timedelta(days=10 * 365),
    "1mo": timedelta(days=25 * 365),
}

_QUOTE_SUFFIXES = ("USDT", "BUSD", "USDC", "FDUSD", "TUSD", "BTC", "ETH", "BNB", "EUR", "GBP")


def to_binance_symbol(s: str) -> str:
    """Normalize a user-supplied symbol to a Binance spot pair.

    Bare base symbols ("BTC", "ETH", "SOL") map to ``<base>USDT``. The
    input must be strictly longer than a quote suffix for that suffix to
    count — otherwise "BTC" alone would match the "BTC" quote and be
    passed through as a degenerate pair.
    """
    norm = s.upper().replace("-", "").replace("/", "").replace("_", "")
    for suffix in _QUOTE_SUFFIXES:
        if len(norm) > len(suffix) and norm.endswith(suffix):
            return norm
    return norm + "USDT"


def _to_binance_interval(interval: str) -> str:
    if interval not in _INTERVAL_MAP:
        raise ValueError(f"unsupported interval for binance: {interval}")
    return _INTERVAL_MAP[interval]


def _ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.astimezone(UTC).timestamp() * 1000)


def _default_start(interval: str) -> datetime:
    return datetime.now(UTC) - _DEFAULT_LOOKBACK.get(interval, timedelta(days=5 * 365))


def _fetch_page(
    symbol: str, interval: str, start_ms: int, end_ms: int
) -> list[list]:
    params: dict[str, str | int] = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": _LIMIT_MAX,
    }
    resp = requests.get(_BASE, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _fetch(
    symbol: str, interval: str, start: datetime | None, end: datetime | None
) -> pd.DataFrame:
    sym = to_binance_symbol(symbol)
    bin_interval = _to_binance_interval(interval)
    if start is None:
        start = _default_start(interval)
    if end is None:
        end = datetime.now(UTC)

    start_ms = _ms(start)
    end_ms = _ms(end)

    rows: list[list] = []
    cursor = start_ms
    while cursor < end_ms:
        page = _fetch_page(sym, bin_interval, cursor, end_ms)
        if not page:
            break
        rows.extend(page)
        last_close_ms = int(page[-1][6])
        if last_close_ms <= cursor or len(page) < _LIMIT_MAX:
            break
        cursor = last_close_ms + 1
        time.sleep(0.05)  # be polite

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    out = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col])
    out = out.set_index("timestamp").sort_index()
    return cast(pd.DataFrame, out)


def fetch_ohlcv(
    symbol: str,
    *,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch OHLCV bars for ``symbol`` from Binance, cached on disk.

    Examples:
        >>> fetch_ohlcv("BTC")        # → BTCUSDT
        >>> fetch_ohlcv("ETHUSDT")    # passthrough
        >>> fetch_ohlcv("SOL", interval="1h", start=...)
    """
    sym = to_binance_symbol(symbol)
    key = CacheKey(source=SOURCE, kind="ohlcv", name=sym, interval=interval)

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


# --- Source-ABC adapter ---------------------------------------------------

from quant_radar.cards.spec import DataRef as _DataRef  # noqa: E402
from quant_radar.sources.base_source import Source, register_source  # noqa: E402
from quant_radar.sources.catalog import CATALOG  # noqa: E402


class _BinanceSource(Source):
    capability = CATALOG["binance"]

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind == "ohlcv"

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        return fetch_ohlcv(
            ref.name,
            interval=ref.interval,
            start=ref.start,
            end=ref.end,
            refresh=refresh,
        )


register_source(_BinanceSource())
