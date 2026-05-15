"""On-disk cache for time-series data.

Layout: ``data/cache/<source>/<kind>/<name>/<interval>.parquet`` plus a
``.meta.json`` sidecar with the cached time range, row count, fetch
timestamp, and TTL.

The cache stores ``pandas.DataFrame`` objects with a ``DatetimeIndex``
named ``timestamp``. Every source adapter must return data in this shape.

``get_or_fetch`` reads from disk, decides whether a fetch is needed
(based on requested range and TTL), and merges new rows in by timestamp.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pandas as pd
from pydantic import BaseModel

from quant_radar.core.config import paths

Fetcher = Callable[..., pd.DataFrame]


@dataclass(frozen=True)
class CacheKey:
    source: str
    kind: str  # "ohlcv" | "macro" | "news" | ...
    name: str  # e.g. "BTC-USD", "DGS10"
    interval: str  # e.g. "1d"

    def relpath(self) -> Path:
        safe_name = self.name.replace("/", "_")
        return Path(self.source) / self.kind / safe_name / f"{self.interval}.parquet"


class Meta(BaseModel):
    last_fetch: datetime
    range_start: datetime | None
    range_end: datetime | None
    rows: int
    ttl_seconds: int = 3600

    def is_fresh(self, now: datetime) -> bool:
        return (now - self.last_fetch).total_seconds() < self.ttl_seconds


def _data_path(key: CacheKey) -> Path:
    return paths.cache / key.relpath()


def _meta_path(key: CacheKey) -> Path:
    p = _data_path(key)
    return p.with_suffix(".meta.json")


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_index(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame has a UTC DatetimeIndex named 'timestamp'."""
    if isinstance(df.index, pd.DatetimeIndex):
        out = df.copy()
    elif "timestamp" in df.columns:
        out = df.set_index("timestamp")
    else:
        raise ValueError("DataFrame must have a DatetimeIndex or a 'timestamp' column")
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    out.index.name = "timestamp"
    return out.sort_index()


def read(key: CacheKey) -> tuple[pd.DataFrame | None, Meta | None]:
    p = _data_path(key)
    if not p.exists():
        return None, None
    df = pd.read_parquet(p)
    df = _ensure_index(df)
    mp = _meta_path(key)
    meta = Meta.model_validate_json(mp.read_text()) if mp.exists() else None
    return df, meta


def write(key: CacheKey, df: pd.DataFrame, *, ttl_seconds: int = 3600) -> Meta:
    df = _ensure_index(df)
    p = _data_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    if len(df) and isinstance(df.index, pd.DatetimeIndex):
        rs: datetime | None = cast(pd.Timestamp, df.index[0]).to_pydatetime()
        re: datetime | None = cast(pd.Timestamp, df.index[-1]).to_pydatetime()
    else:
        rs, re = None, None
    meta = Meta(
        last_fetch=_now(),
        range_start=rs,
        range_end=re,
        rows=len(df),
        ttl_seconds=ttl_seconds,
    )
    _meta_path(key).write_text(meta.model_dump_json())
    return meta


def clear(key: CacheKey) -> None:
    for p in (_data_path(key), _meta_path(key)):
        p.unlink(missing_ok=True)


def _merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    new = _ensure_index(new)
    if old is None or len(old) == 0:
        return new
    if len(new) == 0:
        return old
    merged = pd.concat([old, new])
    merged = merged.loc[~merged.index.duplicated(keep="last")]
    return cast(pd.DataFrame, merged.sort_index())


def _as_utc_ts(dt: datetime | None) -> pd.Timestamp | None:
    if dt is None:
        return None
    ts = pd.Timestamp(dt)
    out = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return cast(pd.Timestamp, out)


def _slice(
    df: pd.DataFrame, start: datetime | None, end: datetime | None
) -> pd.DataFrame:
    if start is None and end is None:
        return df
    return df.loc[_as_utc_ts(start) : _as_utc_ts(end)]


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _needs_fetch(
    meta: Meta,
    start: datetime | None,
    end: datetime | None,
    now: datetime,
) -> tuple[bool, datetime | None, datetime | None]:
    """Return ``(needs_fetch, fetch_start, fetch_end)``.

    Within TTL the cache is authoritative — callers get whatever slice is
    present. Outside TTL we fetch the tail (and optionally backfill before
    the cached start if the caller asked for older data).
    """
    if meta.is_fresh(now):
        return False, None, None

    start_utc = _to_utc(start)
    rs = _to_utc(meta.range_start)
    re = _to_utc(meta.range_end)

    extend_before = start_utc is not None and rs is not None and start_utc < rs
    fetch_start = start_utc if extend_before else re
    return True, fetch_start, _to_utc(end)


def get_or_fetch(
    key: CacheKey,
    fetcher: Fetcher,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
    ttl_seconds: int = 3600,
) -> pd.DataFrame:
    """Return cached DataFrame, fetching/merging only what is missing."""
    now = _now()
    cached, meta = read(key)

    if refresh or cached is None or meta is None:
        fresh = fetcher(start=start, end=end)
        merged = _merge(cached, fresh) if (cached is not None and not refresh) else fresh
        write(key, merged, ttl_seconds=ttl_seconds)
        return _slice(merged, start, end)

    needs, fs, fe = _needs_fetch(meta, start, end, now)
    if needs:
        fresh = fetcher(start=fs, end=fe)
        merged = _merge(cached, fresh)
        write(key, merged, ttl_seconds=ttl_seconds)
        return _slice(merged, start, end)

    return _slice(cached, start, end)
