"""Phase 0 smoke tests — package imports cleanly and config paths are wired up."""

from datetime import datetime

import quant_radar
from quant_radar.core import OHLCV, NewsItem, TimeSeries, paths


def test_package_version() -> None:
    assert quant_radar.__version__ == "0.1.0"


def test_paths_under_repo() -> None:
    assert paths.repo_root.exists()
    assert paths.data == paths.repo_root / "data"
    assert paths.cache == paths.data / "cache"
    assert paths.cards == paths.data / "cards"
    assert paths.main_db.parent == paths.cards
    assert paths.working_json.parent == paths.cards


def test_paths_ensure_creates_dirs(tmp_path, monkeypatch) -> None:
    from quant_radar.core import config

    fake = config._build_paths(tmp_path)
    fake.ensure()
    assert fake.cache.is_dir()
    assert fake.cards.is_dir()


def test_timeseries_roundtrip() -> None:
    ts = TimeSeries(
        name="BTC",
        source="test",
        interval="1d",
        timestamps=[datetime(2025, 1, 1), datetime(2025, 1, 2)],
        values=[100.0, 101.5],
    )
    assert len(ts) == 2
    dumped = ts.model_dump()
    assert TimeSeries.model_validate(dumped) == ts


def test_ohlcv_lengths_align() -> None:
    bars = OHLCV(
        symbol="ETH",
        source="test",
        interval="1h",
        timestamps=[datetime(2025, 1, 1)],
        open=[1.0],
        high=[2.0],
        low=[0.5],
        close=[1.5],
        volume=[100.0],
    )
    assert len(bars) == 1


def test_newsitem_minimum() -> None:
    item = NewsItem(
        title="t",
        url="https://example.com",
        source="test",
        published_at=datetime(2025, 1, 1),
    )
    assert item.tickers == []
