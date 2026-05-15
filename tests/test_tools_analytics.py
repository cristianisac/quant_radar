"""Tests for the agent-facing analytics tool wrappers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_radar import tools


def _ohlcv(n: int) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC")
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


def test_compute_indicators_returns_expected_columns():
    df = _ohlcv(300)
    out = tools.compute_indicators(df, indicators=("sma_50", "sma_200", "rsi", "atr", "macd"))
    for col in (
        "sma_50",
        "sma_200",
        "rsi",
        "atr",
        "macd",
        "macd_signal",
        "macd_hist",
    ):
        assert col in out.columns
    assert len(out) == len(df)
    assert not pd.isna(out["sma_50"].iloc[-1])


def test_compute_indicators_unknown_raises():
    df = _ohlcv(10)
    with pytest.raises(ValueError):
        tools.compute_indicators(df, indicators=("bogus",))


def test_compute_indicators_missing_close_raises():
    df = pd.DataFrame({"open": [1.0]})
    with pytest.raises(ValueError):
        tools.compute_indicators(df)


def test_compute_returns_wraps_close_column():
    df = _ohlcv(60)
    out = tools.compute_returns(df, periods=("1d", "1w"))
    assert out["1d"] is not None
    assert out["1w"] is not None


def test_analyze_moving_averages_wraps_close():
    df = _ohlcv(300)
    out = tools.analyze_moving_averages(df, asset="TEST")
    assert out["insufficient_data"] is False
    assert "TEST" in out["summary"]


def test_analyze_indicators_returns_labels():
    df = _ohlcv(150)
    out = tools.analyze_indicators(df)
    assert out["rsi_state"] in ("overbought", "oversold", "neutral", "unknown")
    assert out["volatility_regime"] in ("high", "elevated", "normal", "low", "unknown")
