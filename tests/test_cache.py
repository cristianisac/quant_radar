"""Tests for the on-disk cache layer.

We replace ``quant_radar.core.config.paths`` with a tmp_path-scoped
instance so cache files land in the test directory, never in the real
``data/cache``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from quant_radar.core import config as config_module


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    fake = config_module._build_paths(tmp_path)
    fake.ensure()
    monkeypatch.setattr(config_module, "paths", fake)
    import quant_radar.cache.store as store

    monkeypatch.setattr(store, "paths", fake)
    yield fake


@pytest.fixture
def cache_key():
    from quant_radar.cache import CacheKey

    return CacheKey(source="test", kind="ohlcv", name="BTC-USD", interval="1d")


def _series(start: str, n: int, base: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=n, freq="D", tz="UTC", name="timestamp")
    return pd.DataFrame({"close": [base + i for i in range(n)]}, index=idx)


def test_write_then_read_roundtrip(cache_key):
    from quant_radar.cache import read, write

    df = _series("2025-01-01", 5)
    meta = write(cache_key, df)
    assert meta.rows == 5

    loaded, loaded_meta = read(cache_key)
    assert loaded is not None and loaded_meta is not None
    pd.testing.assert_frame_equal(loaded, df, check_freq=False)
    assert loaded_meta.range_start == datetime(2025, 1, 1, tzinfo=UTC)
    assert loaded_meta.range_end == datetime(2025, 1, 5, tzinfo=UTC)


def test_read_missing_returns_none(cache_key):
    from quant_radar.cache import read

    df, meta = read(cache_key)
    assert df is None and meta is None


def test_clear_removes_files(cache_key):
    from quant_radar.cache import clear, read, write

    write(cache_key, _series("2025-01-01", 3))
    clear(cache_key)
    df, meta = read(cache_key)
    assert df is None and meta is None


def test_get_or_fetch_cold_call(cache_key):
    from quant_radar.cache import get_or_fetch, read

    df = _series("2025-01-01", 4)
    calls: list[tuple] = []

    def fetcher(start=None, end=None):
        calls.append((start, end))
        return df

    out = get_or_fetch(cache_key, fetcher)
    assert len(calls) == 1
    pd.testing.assert_frame_equal(out, df, check_freq=False)

    cached, meta = read(cache_key)
    assert cached is not None and meta is not None
    assert meta.rows == 4


def test_get_or_fetch_warm_within_ttl_skips_fetcher(cache_key):
    from quant_radar.cache import get_or_fetch, write

    write(cache_key, _series("2025-01-01", 3), ttl_seconds=3600)

    calls = []

    def fetcher(start=None, end=None):
        calls.append((start, end))
        raise AssertionError("fetcher should not be called")

    out = get_or_fetch(cache_key, fetcher)
    assert calls == []
    assert len(out) == 3


def test_get_or_fetch_refresh_overwrites(cache_key):
    from quant_radar.cache import get_or_fetch, read, write

    write(cache_key, _series("2025-01-01", 3, base=100.0), ttl_seconds=3600)

    new = _series("2025-01-01", 3, base=200.0)

    def fetcher(start=None, end=None):
        return new

    out = get_or_fetch(cache_key, fetcher, refresh=True)
    cached, _ = read(cache_key)
    assert cached is not None
    assert out["close"].iloc[0] == 200.0
    assert cached["close"].iloc[0] == 200.0


def test_get_or_fetch_extends_range_by_appending(cache_key):
    """When cache is stale, requesting newer data fetches the tail and appends."""
    from quant_radar.cache import get_or_fetch, read, write

    initial = _series("2025-01-01", 3)
    write(cache_key, initial, ttl_seconds=0)  # immediately stale

    extension = _series("2025-01-04", 2, base=104.0)
    calls = []

    def fetcher(start=None, end=None):
        calls.append((start, end))
        return extension

    requested_end = datetime(2025, 1, 5, tzinfo=UTC)
    out = get_or_fetch(cache_key, fetcher, end=requested_end)

    assert len(calls) == 1
    cached, _ = read(cache_key)
    assert cached is not None
    assert len(cached) == 5
    assert len(out) == 5


def test_merge_dedupes_overlapping_timestamps(cache_key):
    from quant_radar.cache import get_or_fetch, read, write

    initial = _series("2025-01-01", 3, base=100.0)
    write(cache_key, initial, ttl_seconds=0)  # stale → will fetch

    overlap = _series("2025-01-02", 3, base=999.0)

    def fetcher(start=None, end=None):
        return overlap

    requested_end = datetime(2025, 1, 5, tzinfo=UTC)
    get_or_fetch(cache_key, fetcher, end=requested_end)

    cached, _ = read(cache_key)
    assert cached is not None
    assert cached["close"].loc["2025-01-02"] == 999.0
    assert cached["close"].loc["2025-01-01"] == 100.0


def test_within_ttl_cache_is_authoritative_for_range(cache_key):
    """Within TTL, do not re-fetch even if requested end > cached end."""
    from quant_radar.cache import get_or_fetch, write

    write(cache_key, _series("2025-01-01", 3), ttl_seconds=3600)

    def fetcher(start=None, end=None):
        raise AssertionError("should not fetch while TTL is fresh")

    requested_end = datetime(2025, 1, 30, tzinfo=UTC)
    out = get_or_fetch(cache_key, fetcher, end=requested_end)
    assert len(out) == 3


def test_stale_ttl_triggers_refresh(cache_key, monkeypatch):
    from quant_radar.cache import get_or_fetch, write
    from quant_radar.cache import store as store_module

    write(cache_key, _series("2025-01-01", 3), ttl_seconds=60)
    future = datetime.now(UTC) + timedelta(hours=2)
    monkeypatch.setattr(store_module, "_now", lambda: future)

    calls = []

    def fetcher(start=None, end=None):
        calls.append((start, end))
        return _series("2025-01-03", 2, base=200.0)

    get_or_fetch(cache_key, fetcher)
    assert len(calls) == 1


def test_get_or_fetch_refresh_with_tz_naive_fresh_data(cache_key):
    """Regression: yfinance returns tz-naive index. With refresh=True the
    fresh frame skipped tz normalization and _slice crashed comparing
    against UTC-aware start/end. The fix normalizes the fresh result.
    """
    from quant_radar.cache import get_or_fetch

    def fetcher(start=None, end=None):
        idx = pd.date_range("2025-01-01", periods=5, freq="D")  # tz-naive!
        return pd.DataFrame({"close": [100.0, 101, 102, 103, 104]}, index=idx)

    out = get_or_fetch(
        cache_key,
        fetcher,
        start=datetime(2025, 1, 2, tzinfo=UTC),
        end=datetime(2025, 1, 4, tzinfo=UTC),
        refresh=True,
    )
    assert len(out) == 3
    assert isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None


def test_slice_returns_requested_window(cache_key):
    from quant_radar.cache import get_or_fetch, write

    write(cache_key, _series("2025-01-01", 10), ttl_seconds=3600)

    def fetcher(start=None, end=None):
        raise AssertionError("should not fetch")

    out = get_or_fetch(
        cache_key,
        fetcher,
        start=datetime(2025, 1, 3, tzinfo=UTC),
        end=datetime(2025, 1, 5, tzinfo=UTC),
    )
    assert len(out) == 3
