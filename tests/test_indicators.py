"""Tests for indicator primitives on synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_radar.analytics import indicators


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")


def test_sma_matches_manual_mean():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=_index(5))
    out = indicators.sma(s, period=3)
    assert pd.isna(out.iloc[0])
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[3] == pytest.approx(3.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_first_valid_at_period():
    s = pd.Series(np.arange(1, 11, dtype=float), index=_index(10))
    out = indicators.ema(s, period=3)
    assert pd.isna(out.iloc[0])
    assert pd.isna(out.iloc[1])
    assert not pd.isna(out.iloc[2])


def test_rsi_steadily_rising_series_approaches_100():
    s = pd.Series(np.arange(1, 31, dtype=float), index=_index(30))
    out = indicators.rsi(s, period=14)
    assert out.iloc[-1] > 95


def test_rsi_steadily_falling_series_approaches_0():
    s = pd.Series(np.arange(30, 0, -1, dtype=float), index=_index(30))
    out = indicators.rsi(s, period=14)
    assert out.iloc[-1] < 5


def test_atr_handles_simple_range():
    n = 20
    idx = _index(n)
    high = pd.Series(np.full(n, 105.0), index=idx)
    low = pd.Series(np.full(n, 95.0), index=idx)
    close = pd.Series(np.full(n, 100.0), index=idx)
    out = indicators.atr(high, low, close, period=14)
    assert out.iloc[-1] == pytest.approx(10.0, abs=0.1)


def test_macd_columns_and_finite():
    n = 60
    s = pd.Series(np.cumsum(np.sin(np.linspace(0, 12, n))) + 100, index=_index(n))
    out = indicators.macd(s, fast_period=12, slow_period=26, signal_period=9)
    assert list(out.columns) == ["macd", "macd_signal", "macd_hist"]
    assert np.isfinite(out.iloc[-1]).all()
