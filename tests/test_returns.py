"""Tests for compute_returns."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_radar.analytics.returns import compute_returns


def _daily_series(n: int, start: str = "2023-06-01") -> pd.Series:
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    return pd.Series(100.0 + np.arange(n), index=idx)


def test_returns_basic_periods():
    s = _daily_series(400)
    out = compute_returns(s, periods=["1d", "1w", "1m"])

    # day-over-day: last is 100+399=499, prev is 498 → 1/498
    assert out["1d"] == pytest.approx((499 - 498) / 498)
    # week: last vs 7 days earlier
    assert out["1w"] == pytest.approx((499 - 492) / 492)
    # 1m: last vs ~1 month ago — use DateOffset semantics
    assert out["1m"] is not None and out["1m"] > 0


def test_returns_yoy_and_ytd():
    s = _daily_series(400)
    out = compute_returns(s, periods=["1y", "yoy", "ytd"])
    assert out["1y"] == out["yoy"]
    assert out["ytd"] is not None and out["ytd"] > 0


def test_returns_insufficient_history():
    s = _daily_series(5)
    out = compute_returns(s, periods=["1d", "1m", "1y"])
    assert out["1d"] is not None
    assert out["1m"] is None
    assert out["1y"] is None


def test_returns_empty_series():
    out = compute_returns(pd.Series(dtype=float), periods=["1d", "1w"])
    assert out == {"1d": None, "1w": None}


def test_returns_unknown_period_is_none():
    s = _daily_series(50)
    out = compute_returns(s, periods=["1d", "bogus"])
    assert out["bogus"] is None
