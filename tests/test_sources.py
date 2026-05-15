"""Source adapter tests with mocked HTTP / yfinance."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd
import pytest
import requests
import responses

from quant_radar.core import config as config_module


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    fake = config_module._build_paths(tmp_path)
    fake.ensure()
    monkeypatch.setattr(config_module, "paths", fake)
    import quant_radar.cache.store as store

    monkeypatch.setattr(store, "paths", fake)
    yield fake


# ---------- yfinance ----------


def _fake_yf_frame() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Adj Close": [100.5, 101.5, 102.5],
            "Volume": [1000, 1100, 1200],
        },
        index=idx,
    )


def test_yfinance_fetch_ohlcv_caches_and_normalizes():
    from quant_radar.sources import yfinance_src

    with patch.object(yfinance_src.yf, "download", return_value=_fake_yf_frame()) as dl:
        out = yfinance_src.fetch_ohlcv("BTC-USD", interval="1d")

    assert dl.call_count == 1
    assert list(out.columns) == ["open", "high", "low", "close", "adj_close", "volume"]
    assert isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None
    assert len(out) == 3


def test_yfinance_second_call_hits_cache():
    from quant_radar.sources import yfinance_src

    with patch.object(yfinance_src.yf, "download", return_value=_fake_yf_frame()) as dl:
        yfinance_src.fetch_ohlcv("BTC-USD", interval="1d")
        yfinance_src.fetch_ohlcv("BTC-USD", interval="1d")

    assert dl.call_count == 1


def test_yfinance_refresh_forces_call():
    from quant_radar.sources import yfinance_src

    with patch.object(yfinance_src.yf, "download", return_value=_fake_yf_frame()) as dl:
        yfinance_src.fetch_ohlcv("BTC-USD", interval="1d")
        yfinance_src.fetch_ohlcv("BTC-USD", interval="1d", refresh=True)

    assert dl.call_count == 2


def test_yfinance_unsupported_interval_raises():
    from quant_radar.sources import yfinance_src

    with pytest.raises(ValueError):
        yfinance_src.fetch_ohlcv("BTC-USD", interval="bogus")


def test_yfinance_default_start_is_far_enough_back_for_sma_200():
    """Regression: yfinance.download defaults to 1mo when start=None,
    which is not enough bars for an SMA_200. Adapter must set start."""
    from datetime import UTC, datetime, timedelta

    from quant_radar.sources import yfinance_src

    captured: dict = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return _fake_yf_frame()

    with patch.object(yfinance_src.yf, "download", side_effect=capture):
        yfinance_src.fetch_ohlcv("BTC-USD", interval="1d")

    assert captured["start"] is not None
    delta = datetime.now(UTC) - captured["start"]
    assert delta > timedelta(days=365 * 4), (
        f"daily default lookback should be ≥4y, got {delta.days} days"
    )


# ---------- FRED ----------


_FRED_CSV = (
    "observation_date,DGS10\n"
    "2025-01-01,4.10\n"
    "2025-01-02,4.15\n"
    "2025-01-03,4.20\n"
    "2025-01-04,4.18\n"
)


@responses.activate
def test_fred_fetch_macro_caches_and_normalizes():
    from quant_radar.sources import fred_src

    responses.add(
        responses.GET, fred_src._CSV_URL, body=_FRED_CSV, status=200,
        content_type="text/csv",
    )
    out = fred_src.fetch_macro_series("DGS10")

    assert list(out.columns) == ["value"]
    assert isinstance(out.index, pd.DatetimeIndex)
    assert isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None
    assert len(out) == 4


@responses.activate
def test_fred_warm_cache_skips_call():
    from quant_radar.sources import fred_src

    responses.add(
        responses.GET, fred_src._CSV_URL, body=_FRED_CSV, status=200,
        content_type="text/csv",
    )
    fred_src.fetch_macro_series("DGS10")
    fred_src.fetch_macro_series("DGS10")

    assert len(responses.calls) == 1


# ---------- CoinPaprika ----------


def _fake_coinpaprika_payload() -> list[dict]:
    return [
        {
            "time_open": "2025-01-01T00:00:00Z",
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 104.0,
            "volume": 12345.0,
            "market_cap": 0.0,
        },
        {
            "time_open": "2025-01-02T00:00:00Z",
            "open": 104.0,
            "high": 108.0,
            "low": 103.0,
            "close": 107.0,
            "volume": 12000.0,
            "market_cap": 0.0,
        },
    ]


@responses.activate
def test_coinpaprika_fetch_ohlcv_normalizes_payload():
    from quant_radar.sources import coinpaprika_src

    responses.add(
        responses.GET,
        f"{coinpaprika_src._BASE}/coins/btc-bitcoin/ohlcv/historical",
        json=_fake_coinpaprika_payload(),
        status=200,
    )

    out = coinpaprika_src.fetch_ohlcv(
        "btc-bitcoin",
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 5, tzinfo=UTC),
    )

    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert len(out) == 2
    assert isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None


@responses.activate
def test_coinpaprika_second_call_hits_cache():
    from quant_radar.sources import coinpaprika_src

    responses.add(
        responses.GET,
        f"{coinpaprika_src._BASE}/coins/btc-bitcoin/ohlcv/historical",
        json=_fake_coinpaprika_payload(),
        status=200,
    )

    coinpaprika_src.fetch_ohlcv(
        "btc-bitcoin",
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 5, tzinfo=UTC),
    )
    coinpaprika_src.fetch_ohlcv(
        "btc-bitcoin",
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 5, tzinfo=UTC),
    )
    assert len(responses.calls) == 1


@responses.activate
def test_coinpaprika_http_error_propagates():
    from quant_radar.sources import coinpaprika_src

    responses.add(
        responses.GET,
        f"{coinpaprika_src._BASE}/coins/btc-bitcoin/ohlcv/historical",
        json={"error": "rate limited"},
        status=429,
    )

    with pytest.raises(requests.HTTPError):
        coinpaprika_src.fetch_ohlcv("btc-bitcoin")
