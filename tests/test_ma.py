"""Tests for analyze_moving_averages."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_radar.analytics.ma import analyze_moving_averages


def _series(values: np.ndarray, start: str = "2023-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="D", tz="UTC")
    return pd.Series(values, index=idx)


def test_insufficient_data_returns_flag():
    s = _series(np.arange(50, dtype=float))
    out = analyze_moving_averages(s, fast_period=50, slow_period=200)
    assert out["insufficient_data"] is True
    assert "Not enough data" in out["summary"]


def test_uptrend_price_above_both_mas_and_fast_above_slow():
    n = 300
    s = _series(np.arange(n, dtype=float) * 1.0 + 100.0)
    out = analyze_moving_averages(s, fast_period=50, slow_period=200, asset="X")
    assert out["insufficient_data"] is False
    assert out["price_vs_fast"] == "above"
    assert out["price_vs_slow"] == "above"
    assert out["fast_vs_slow"] == "above"
    assert out["fast_slope"] is not None and out["fast_slope"] > 0
    assert "X is above" in out["summary"]


def test_downtrend_price_below_both_mas_and_fast_below_slow():
    n = 300
    s = _series(np.linspace(400, 100, n))
    out = analyze_moving_averages(s, fast_period=50, slow_period=200)
    assert out["price_vs_fast"] == "below"
    assert out["price_vs_slow"] == "below"
    assert out["fast_vs_slow"] == "below"


def test_catching_up_from_below_detected():
    """Construct a path where fast < slow but fast has just started turning up."""
    decline = np.linspace(400, 200, 250)
    rebound = np.linspace(200, 290, 50)
    s = _series(np.concatenate([decline, rebound]))
    out = analyze_moving_averages(s, fast_period=50, slow_period=200)
    assert out["fast_vs_slow"] == "below"
    assert out["fast_catching_up_from_below"] is True


def test_golden_cross_recent_detected():
    """Long decline then a sharp rally that pulls the 50d above the 200d."""
    decline = np.linspace(400, 100, 220)
    rally = np.linspace(100, 600, 80)
    s = _series(np.concatenate([decline, rally]))
    out = analyze_moving_averages(s, fast_period=50, slow_period=200, cross_lookback=80)
    assert out["golden_cross_recent"] is True
    assert out["death_cross_recent"] is False


def test_death_cross_recent_detected():
    rally = np.linspace(100, 400, 220)
    crash = np.linspace(400, 50, 80)
    s = _series(np.concatenate([rally, crash]))
    out = analyze_moving_averages(s, fast_period=50, slow_period=200, cross_lookback=80)
    assert out["death_cross_recent"] is True
    assert out["golden_cross_recent"] is False
