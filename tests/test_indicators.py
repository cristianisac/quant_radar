"""Tests for indicator primitives on synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_radar.analytics import indicators


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")


def test_rolling_zscore_basic():
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(0, 1, size=100), index=_index(100))
    z = indicators.rolling_zscore(s, window=30, min_obs=30)
    # Early positions guarded by min_obs.
    assert z.iloc[:29].isna().all()
    # Once warmed, output is finite and roughly bounded.
    tail = z.iloc[40:]
    assert tail.notna().all()
    assert tail.abs().mean() < 3


def test_rolling_zscore_constant_series_yields_zero_or_nan():
    s = pd.Series([5.0] * 50, index=_index(50))
    z = indicators.rolling_zscore(s, window=10, min_obs=10)
    # Constant series has std == 0 → z-score is NaN or inf, never finite non-zero.
    after_warmup = z.iloc[9:]
    assert (after_warmup.isna() | (after_warmup == 0)).all()


def test_rolling_zscore_min_obs_guard():
    rng = np.random.default_rng(1)
    s = pd.Series(rng.normal(0, 1, size=20), index=_index(20))
    z = indicators.rolling_zscore(s, window=30, min_obs=30)
    # 20 observations, window/min_obs 30 → entirely NaN.
    assert z.isna().all()


def test_rolling_zscore_rejects_bad_window():
    s = pd.Series([1.0, 2.0, 3.0], index=_index(3))
    with pytest.raises(ValueError, match="window must be >= 2"):
        indicators.rolling_zscore(s, window=1)
    with pytest.raises(ValueError, match="min_obs must be >= 2"):
        indicators.rolling_zscore(s, window=10, min_obs=1)


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
