"""Tests for the chart figure builder and DataRef hydration."""

# Plotly's type stubs are incomplete (fig.data is typed as Literal['data']
# instead of a tuple of traces). Suppress per-attribute errors here.
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false

from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import responses

from quant_radar.cards.spec import Annotation, Card, ChartSpec, DataRef
from quant_radar.core import config as config_module
from quant_radar.ui import data as ui_data
from quant_radar.ui.render import build_chart_figure


def _traces(fig: Any) -> tuple[Any, ...]:
    return cast(tuple[Any, ...], fig.data)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    fake = config_module._build_paths(tmp_path)
    fake.ensure()
    monkeypatch.setattr(config_module, "paths", fake)
    import quant_radar.cache.store as store

    monkeypatch.setattr(store, "paths", fake)
    yield fake


def _ohlcv_frame(n: int = 250) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    base = 100.0 + np.arange(n)
    return pd.DataFrame(
        {
            "open": base,
            "high": base + 1,
            "low": base - 1,
            "close": base + 0.5,
            "volume": np.full(n, 1000.0),
        },
        index=idx,
    )


def _chart_card(overlays=None, subplots=None, annotations=None) -> Card:
    return Card(
        type="chart",
        title="BTC daily",
        data_refs=[DataRef(source="yfinance", kind="ohlcv", name="BTC-USD")],
        chart_spec=ChartSpec(
            overlays=overlays or [],
            subplots=subplots or [],
            annotations=annotations or [],
        ),
    )


def test_build_chart_figure_basic_ohlcv():
    card = _chart_card()
    fig = build_chart_figure(card, [_ohlcv_frame()])
    traces = _traces(fig)
    assert len(traces) == 1
    assert traces[0].type == "candlestick"


def test_build_chart_figure_with_overlays():
    card = _chart_card(overlays=["sma_50", "sma_200"])
    fig = build_chart_figure(card, [_ohlcv_frame()])
    overlay_names = [t.name for t in _traces(fig) if t.type == "scatter"]
    assert "sma_50" in overlay_names
    assert "sma_200" in overlay_names


def test_build_chart_figure_with_subplots_rsi_and_volume():
    card = _chart_card(subplots=["rsi", "volume"])
    fig = build_chart_figure(card, [_ohlcv_frame()])
    rows = {trace.yaxis for trace in _traces(fig)}
    assert len(rows) >= 2  # at least price + one subplot


def test_build_chart_figure_unknown_subplot_silently_skipped():
    card = _chart_card(subplots=["bogus"])
    fig = build_chart_figure(card, [_ohlcv_frame()])
    assert len(_traces(fig)) == 1


def test_build_chart_figure_trendline_annotation_added_as_trace():
    ann = Annotation(
        kind="trendline",
        points=[(1.0, 100.0), (2.0, 110.0)],
        label="up",
    )
    card = _chart_card(annotations=[ann])
    fig = build_chart_figure(card, [_ohlcv_frame()])
    assert any(t.name == "up" for t in _traces(fig))


def test_build_chart_figure_close_only_uses_line():
    full = _ohlcv_frame()
    df = pd.DataFrame({"close": full["close"]}, index=full.index)
    card = _chart_card()
    fig = build_chart_figure(card, [df])
    assert _traces(fig)[0].type == "scatter"


# --------------- hydrate() ---------------


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


def test_hydrate_yfinance():
    ref = DataRef(source="yfinance", kind="ohlcv", name="BTC-USD")
    with patch.object(ui_data.yfinance_src.yf, "download", return_value=_fake_yf_frame()):
        out = ui_data.hydrate(ref)
    assert len(out) == 3
    assert "close" in out.columns


@responses.activate
def test_hydrate_fred():
    responses.add(
        responses.GET,
        ui_data.fred_src._CSV_URL,
        body="observation_date,DGS10\n2025-01-01,4.1\n2025-01-02,4.2\n",
        status=200,
        content_type="text/csv",
    )
    ref = DataRef(source="fred", kind="macro", name="DGS10")
    out = ui_data.hydrate(ref)
    assert list(out.columns) == ["value"]
    assert len(out) == 2


def test_hydrate_unsupported_raises():
    ref = DataRef(source="nope", kind="ohlcv", name="x")
    with pytest.raises(ValueError):
        ui_data.hydrate(ref)
