"""Tests for algorithmic pattern detection and vision rendering."""

# pandas / numpy stubs return ambiguous types for Index arithmetic and
# ArrayLike ops; the runtime is fine — suppress at the file level.
# pyright: reportOperatorIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_radar import tools
from quant_radar.analytics import patterns
from quant_radar.core import config as config_module


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    fake = config_module._build_paths(tmp_path)
    fake.ensure()
    monkeypatch.setattr(config_module, "paths", fake)
    import quant_radar.analytics.vision as vision_mod

    monkeypatch.setattr(vision_mod, "paths", fake)
    yield fake


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")


def _ascending_channel(n: int = 80, slope: float = 0.5, half_width: float = 5.0) -> pd.Series:
    """Synthetic price oscillating tightly inside an ascending channel."""
    rng = np.random.default_rng(7)
    idx = _index(n)
    base = 100.0 + slope * np.arange(n)
    # alternate touches of upper and lower with mild noise
    cycle = np.tile([half_width, 0.0, -half_width, 0.0], int(np.ceil(n / 4)))[:n]
    noise = rng.normal(0, 0.3, n)
    return pd.Series(base + cycle + noise, index=idx)


def _flat_random_walk(n: int = 80, seed: int = 11) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 + np.cumsum(rng.normal(0, 1.0, n)), index=_index(n))


# --------------- detect_channel ---------------


def test_detect_channel_finds_ascending_channel():
    s = _ascending_channel()
    out = patterns.detect_channel(s, lookback=60)
    assert out["found"] is True
    assert out["confidence"] >= 0.6
    assert out["direction"] == "ascending"
    assert out["slope_upper"] > 0
    assert out["slope_lower"] > 0


def test_detect_channel_insufficient_bars():
    s = pd.Series([1.0, 2.0, 3.0], index=_index(3))
    out = patterns.detect_channel(s, lookback=60)
    assert out["found"] is False
    assert "insufficient" in (out["reason"] or "")


def test_detect_channel_random_walk_has_low_confidence_or_no_find():
    s = _flat_random_walk()
    out = patterns.detect_channel(s, lookback=60)
    # A genuinely random walk should not be a high-confidence channel.
    assert out["found"] is False or out["confidence"] < 0.7


def test_detect_channel_r2_gate_blocks_loose_fits():
    """High composite confidence isn't enough — both lines must fit individually."""
    s = _flat_random_walk()
    out = patterns.detect_channel(s, lookback=60, min_r2=0.9)
    assert out["found"] is False


def test_channel_to_annotation_points_returns_endpoints():
    s = _ascending_channel()
    ch = patterns.detect_channel(s, lookback=60)
    pts = patterns.channel_to_annotation_points(s, ch)
    assert pts is not None
    upper, lower = pts
    assert len(upper) == 2 and len(lower) == 2
    # Endpoints span the window: first ts < last ts
    assert upper[0][0] < upper[1][0]


def test_channel_to_annotation_points_none_when_not_found():
    out = {"found": False}
    assert patterns.channel_to_annotation_points(pd.Series([1.0]), out) is None


# --------------- detect_breakout ---------------


def test_detect_breakout_upward_when_close_exceeds_upper():
    s = _ascending_channel(n=80)
    ch = patterns.detect_channel(s, lookback=60)
    assert ch["found"] is True
    # synthesize a clear breakout by appending a value well above the upper line
    last_x = ch["lookback"] - 1
    upper_at_last = ch["slope_upper"] * last_x + ch["intercept_upper"]
    new_idx = pd.date_range(s.index[-1] + pd.Timedelta(days=1), periods=1, freq="D", tz="UTC")
    spike = pd.Series([upper_at_last + 20.0], index=new_idx)
    s2 = pd.concat([s, spike])
    out = patterns.detect_breakout(s2, ch)
    assert out["found"] is True
    assert out["direction"] == "up"


def test_detect_breakout_no_channel_returns_not_found():
    out = patterns.detect_breakout(pd.Series([1.0, 2.0]), {"found": False})
    assert out["found"] is False
    assert "no channel" in out["reason"]


def test_detect_breakout_within_channel():
    s = _ascending_channel(n=80)
    ch = patterns.detect_channel(s, lookback=60)
    out = patterns.detect_breakout(s, ch)
    # last bar still inside the channel
    assert out["found"] is False


# --------------- agent-facing tool wrappers ---------------


def _ohlcv_from_close(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": close.values,
            "high": close.values + 0.5,
            "low": close.values - 0.5,
            "close": close.values,
            "volume": np.full(len(close), 1000.0),
        },
        index=close.index,
    )


def test_tools_detect_channels_wraps_close_column():
    df = _ohlcv_from_close(_ascending_channel())
    out = tools.detect_channels(df, lookback=60)
    assert out["found"] is True
    assert out["confidence"] >= 0.6


def test_tools_detect_channels_missing_close_raises():
    with pytest.raises(ValueError):
        tools.detect_channels(pd.DataFrame({"open": [1.0]}))


def test_tools_detect_breakouts_runs_channel_for_you():
    df = _ohlcv_from_close(_ascending_channel())
    out = tools.detect_breakouts(df, lookback=60)
    assert "found" in out


def test_tools_channel_annotations_returns_two_trendlines():
    df = _ohlcv_from_close(_ascending_channel())
    ch = tools.detect_channels(df, lookback=60)
    anns = tools.channel_annotations(df, ch)
    assert anns is not None and len(anns) == 2
    assert {a["label"] for a in anns} == {"channel upper", "channel lower"}
    assert all(a["kind"] == "trendline" for a in anns)


# --------------- vision rendering ---------------


def test_detect_patterns_vision_creates_png():
    df = _ohlcv_from_close(_ascending_channel())
    out = tools.detect_patterns_vision(df, asset_name="TEST-USD")
    from pathlib import Path

    path = Path(out["image_path"])
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 0
    assert "image_path" in out and "instructions" in out


def test_detect_patterns_vision_close_only_frame():
    df = pd.DataFrame({"close": _ascending_channel().values}, index=_ascending_channel().index)
    out = tools.detect_patterns_vision(df, asset_name="close-only")
    from pathlib import Path

    assert Path(out["image_path"]).exists()


def test_detect_patterns_vision_empty_raises():
    with pytest.raises(ValueError):
        tools.detect_patterns_vision(pd.DataFrame({"close": []}), asset_name="x")
