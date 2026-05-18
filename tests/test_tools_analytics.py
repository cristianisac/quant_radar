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


def test_compute_indicators_ambiguous_columns_raises():
    """When no `close`/`value` and multiple numeric columns, the tool
    can't auto-pick a price column and must raise asking for `price_col`.
    """
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    with pytest.raises(ValueError, match="could not infer price column"):
        tools.compute_indicators(df)


def test_compute_indicators_parametric_sma_ema_any_period():
    """Agent can request sma_137 or ema_42 without touching code."""
    df = _ohlcv(300)
    out = tools.compute_indicators(df, which=("sma_137", "ema_42", "sma_5"))
    assert "sma_137" in out.columns
    assert "ema_42" in out.columns
    assert "sma_5" in out.columns
    # Sanity: sma_5 should warm up by row 4, sma_137 by row 136.
    assert pd.isna(out["sma_5"].iloc[3])
    assert not pd.isna(out["sma_5"].iloc[10])
    assert pd.isna(out["sma_137"].iloc[135])
    assert not pd.isna(out["sma_137"].iloc[200])


def test_compute_indicators_rsi_and_atr_take_period_suffix():
    df = _ohlcv(60)
    out = tools.compute_indicators(df, which=("rsi_21", "atr_28"))
    assert "rsi_21" in out.columns
    assert "atr_28" in out.columns


def test_compute_indicators_auto_picks_value_on_fred_like_frame():
    """Column-agnostic: tools transparently use `value` when there's no
    `close` (the FRED macro convention).
    """
    idx = pd.date_range("2024-01-01", periods=300, freq="D", tz="UTC")
    df = pd.DataFrame({"value": np.linspace(1.0, 3.0, 300)}, index=idx)
    out = tools.compute_indicators(df, which=("sma_50", "rsi"))
    assert "sma_50" in out.columns
    assert "rsi" in out.columns
    # ATR is silently skipped (no high/low/close) rather than erroring.
    out2 = tools.compute_indicators(df, which=("atr",))
    assert "atr" not in out2.columns


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
