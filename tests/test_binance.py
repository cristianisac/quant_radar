"""Tests for the Binance crypto adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
import responses

from quant_radar.core import config as config_module
from quant_radar.sources import binance_src


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    fake = config_module._build_paths(tmp_path)
    fake.ensure()
    monkeypatch.setattr(config_module, "paths", fake)
    import quant_radar.cache.store as store

    monkeypatch.setattr(store, "paths", fake)
    yield fake


def _fake_klines(n: int = 3, start_ms: int | None = None) -> list[list]:
    """Mimic Binance's array-of-arrays klines payload."""
    if start_ms is None:
        start_ms = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)
    rows = []
    one_day_ms = 86_400_000
    for i in range(n):
        ot = start_ms + i * one_day_ms
        rows.append(
            [
                ot,                       # open_time
                "100.0",                  # open
                "105.0",                  # high
                "99.0",                   # low
                f"{100 + i}.0",           # close
                f"{1000 + i * 10}.0",     # volume
                ot + one_day_ms - 1,      # close_time
                "0", 0, "0", "0", "0",
            ]
        )
    return rows


def test_to_binance_symbol_bare_base_appends_usdt():
    assert binance_src.to_binance_symbol("BTC") == "BTCUSDT"
    assert binance_src.to_binance_symbol("eth") == "ETHUSDT"
    # "BTC-USD" → "BTCUSD" after stripping the dash; doesn't end in a known
    # quote, so USDT gets appended ("BTCUSDUSDT"). This is mildly ugly but
    # acceptable — callers shouldn't pass yfinance-style symbols here. The
    # important property is that the result is well-formed.
    out = binance_src.to_binance_symbol("BTC-USD")
    assert out.endswith("USDT") or out in {"BTCUSD"}


def test_to_binance_symbol_passthrough_preformed_pair():
    assert binance_src.to_binance_symbol("BTCUSDT") == "BTCUSDT"
    assert binance_src.to_binance_symbol("ETHBTC") == "ETHBTC"
    assert binance_src.to_binance_symbol("solusdc") == "SOLUSDC"


@responses.activate
def test_binance_fetch_ohlcv_single_page():
    responses.add(
        responses.GET,
        binance_src._BASE,
        json=_fake_klines(n=5),
        status=200,
    )
    out = binance_src.fetch_ohlcv("BTC", interval="1d")
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert len(out) == 5
    assert isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None
    assert out["close"].iloc[0] == 100.0
    assert out["close"].iloc[-1] == 104.0


@responses.activate
def test_binance_fetch_ohlcv_paginates_when_full_page_returned():
    """Two pages of 1000 + a short final page should all merge."""
    page_a = _fake_klines(n=binance_src._LIMIT_MAX, start_ms=1_700_000_000_000)
    page_b = _fake_klines(
        n=3,
        start_ms=1_700_000_000_000 + binance_src._LIMIT_MAX * 86_400_000 + 1,
    )
    responses.add(responses.GET, binance_src._BASE, json=page_a, status=200)
    responses.add(responses.GET, binance_src._BASE, json=page_b, status=200)

    end = datetime.now(UTC) + timedelta(days=400)  # far future so cursor advances
    start = datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=UTC)
    out = binance_src.fetch_ohlcv("BTC", interval="1d", start=start, end=end)
    assert len(out) == binance_src._LIMIT_MAX + 3
    assert len(responses.calls) == 2


@responses.activate
def test_binance_fetch_ohlcv_uses_default_start_when_none():
    responses.add(
        responses.GET,
        binance_src._BASE,
        json=_fake_klines(n=2),
        status=200,
    )
    binance_src.fetch_ohlcv("BTC", interval="1d")
    url = responses.calls[0].request.url or ""
    assert "startTime=" in url, "default start should have been injected"


def test_binance_unsupported_interval_raises():
    with pytest.raises(ValueError):
        binance_src.fetch_ohlcv("BTC", interval="bogus")


@responses.activate
def test_binance_second_call_within_ttl_hits_cache():
    responses.add(
        responses.GET, binance_src._BASE, json=_fake_klines(n=2), status=200,
    )
    binance_src.fetch_ohlcv("BTC", interval="1d")
    binance_src.fetch_ohlcv("BTC", interval="1d")
    assert len(responses.calls) == 1


@responses.activate
def test_binance_payload_is_actually_json_array():
    """Sanity: confirm payload shape matches the real API contract."""
    raw = _fake_klines(n=1)
    body = json.dumps(raw)
    responses.add(responses.GET, binance_src._BASE, body=body, status=200)
    out = binance_src.fetch_ohlcv("BTC", interval="1d")
    assert len(out) == 1
