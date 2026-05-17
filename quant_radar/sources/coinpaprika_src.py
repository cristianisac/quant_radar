"""CoinPaprika adapter — historical OHLCV for crypto via REST API.

.. warning::
   CoinPaprika moved historical OHLCV behind a paid plan in 2025. The
   ``/v1/coins/<coin_id>/ohlcv/historical`` endpoint returns
   ``402 Payment Required`` for free-tier callers. This adapter is kept
   for callers with a paid plan, but the default crypto source in
   ``quant_radar`` is now :mod:`quant_radar.sources.binance_src`. See
   ``SKILL.md`` for the routing convention.

Public endpoint: ``https://api.coinpaprika.com/v1/coins/<coin_id>/ohlcv/historical``.
``coin_id`` is the CoinPaprika identifier, e.g. ``btc-bitcoin``, ``eth-ethereum``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.sources.base import TTL_DAILY_SEC

SOURCE = "coinpaprika"
_BASE = "https://api.coinpaprika.com/v1"
_TIMEOUT = 15


def _to_unix(dt: datetime | None, default: datetime) -> int:
    if dt is None:
        dt = default
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())


def _fetch(
    coin_id: str, start: datetime | None, end: datetime | None
) -> pd.DataFrame:
    now = datetime.now(UTC)
    one_year_ago = now.replace(year=now.year - 1)
    params = {
        "start": _to_unix(start, one_year_ago),
        "end": _to_unix(end, now),
    }
    url = f"{_BASE}/coins/{coin_id}/ohlcv/historical"
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["time_open"], utc=True)
    keep = ["timestamp", "open", "high", "low", "close", "volume"]
    df = df[[c for c in keep if c in df.columns]].set_index("timestamp")
    df.index.name = "timestamp"
    return df.sort_index()


def fetch_ohlcv(
    coin_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch daily OHLCV bars for ``coin_id`` from CoinPaprika, cached on disk."""
    key = CacheKey(source=SOURCE, kind="ohlcv", name=coin_id, interval="1d")

    def fetcher(start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        return _fetch(coin_id, start, end)

    return get_or_fetch(
        key,
        fetcher,
        start=start,
        end=end,
        refresh=refresh,
        ttl_seconds=TTL_DAILY_SEC,
    )


# --- Source-ABC adapter ---------------------------------------------------

from quant_radar.cards.spec import DataRef as _DataRef  # noqa: E402
from quant_radar.sources.base_source import Source, register_source  # noqa: E402
from quant_radar.sources.catalog import CATALOG  # noqa: E402


class _CoinPaprikaSource(Source):
    capability = CATALOG["coinpaprika"]

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind == "ohlcv"

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        return fetch_ohlcv(
            ref.name, start=ref.start, end=ref.end, refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        # Deferred (paid-only). The agent should reach for binance_src instead.
        return []

    def describe(self, name: str) -> dict | None:
        return None


register_source(_CoinPaprikaSource())
