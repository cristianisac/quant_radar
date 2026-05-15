"""Catalog completeness + introspection tool tests."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from quant_radar import tools
from quant_radar.core import config as config_module
from quant_radar.sources import catalog
from quant_radar.tools import sources_meta


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    fake = config_module._build_paths(tmp_path)
    fake.ensure()
    monkeypatch.setattr(config_module, "paths", fake)
    import quant_radar.cache.store as store

    monkeypatch.setattr(store, "paths", fake)
    yield fake


# --------------- catalog coverage ---------------


def test_catalog_lists_every_source_in_sources_package():
    """If we add a source module, we must add its catalog entry."""
    from quant_radar import sources

    code_sources = {
        name[: -len("_src")] for name in sources.__all__ if name.endswith("_src")
    }
    catalog_sources = set(catalog.CATALOG.keys())
    missing = code_sources - catalog_sources
    extras = catalog_sources - code_sources
    assert not missing, f"sources missing catalog entry: {sorted(missing)}"
    assert not extras, f"catalog entries with no source module: {sorted(extras)}"


_REQUIRED_FIELDS = (
    "name", "kinds", "intervals", "history",
    "coverage", "auth", "rate_limit", "status",
)


def test_every_catalog_entry_has_required_fields():
    for name, cap in catalog.CATALOG.items():
        d = cap.to_dict()
        for field in _REQUIRED_FIELDS:
            assert field in d, f"{name} missing field {field}"
        assert d["name"] == name
        assert isinstance(d["kinds"], list) and d["kinds"]
        assert isinstance(d["intervals"], list)
        assert d["status"] in ("active", "deferred", "paid-only")


def test_coinpaprika_is_marked_deferred():
    assert catalog.CATALOG["coinpaprika"].status == "deferred"


# --------------- list / describe ---------------


def test_list_sources_returns_all_catalog_entries():
    out = tools.list_sources()
    names = {s["name"] for s in out}
    assert names == set(catalog.CATALOG.keys())


def test_describe_source_returns_dict_for_known_source():
    out = tools.describe_source("binance")
    assert out is not None
    assert out["name"] == "binance"
    assert "1d" in out["intervals"]


def test_describe_source_returns_none_for_unknown():
    assert tools.describe_source("doesnotexist") is None


# --------------- probe_history ---------------


def _fake_frame_for(symbol: str):
    idx = pd.date_range("2018-01-01", periods=2000, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": range(len(idx)),
            "high": range(len(idx)),
            "low": range(len(idx)),
            "close": range(len(idx)),
            "volume": [1] * len(idx),
        },
        index=idx,
    )


def test_probe_history_yfinance_returns_first_last_bars():
    raw = pd.DataFrame(
        {
            "Open": range(2000),
            "High": range(2000),
            "Low": range(2000),
            "Close": range(2000),
            "Adj Close": range(2000),
            "Volume": range(2000),
        },
        index=pd.date_range("2018-01-01", periods=2000, freq="D"),
    )
    with patch.object(sources_meta.yfinance_src.yf, "download", return_value=raw):
        out = tools.probe_history("AAPL", source="yfinance", kind="ohlcv")
    assert out["symbol"] == "AAPL"
    assert out["source"] == "yfinance"
    assert out["bars"] == 2000
    assert out["first"].startswith("2018-01-01")


def test_probe_history_binance_uses_paginated_klines():
    one_day_ms = 86_400_000
    start_ms = 1_577_836_800_000  # 2020-01-01 UTC
    payload = [
        [
            start_ms + i * one_day_ms,
            "100", "105", "99", "100",
            "1", start_ms + (i + 1) * one_day_ms - 1,
            "0", 0, "0", "0", "0",
        ]
        for i in range(50)
    ]
    with patch.object(sources_meta.binance_src, "_fetch_page", return_value=payload):
        out = tools.probe_history("BTC", source="binance", kind="ohlcv")
    assert out["bars"] == 50
    assert out["first"].startswith("2020-01-01")


def test_probe_history_unsupported_combination_raises():
    with pytest.raises(ValueError):
        tools.probe_history("BTC", source="binance", kind="news")


def test_probe_history_empty_frame_returns_zero_bars():
    raw = pd.DataFrame(
        {"Open": [], "High": [], "Low": [], "Close": [], "Adj Close": [], "Volume": []},
        index=pd.DatetimeIndex([]),
    )
    with patch.object(sources_meta.yfinance_src.yf, "download", return_value=raw):
        out = tools.probe_history("ZZZZ", source="yfinance", kind="ohlcv")
    assert out["bars"] == 0
    assert "first" not in out
