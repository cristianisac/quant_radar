"""Technical indicator primitives.

Pure functions over pandas Series/DataFrames. No state, no caching, no
external dependencies beyond pandas. Higher-level analysis (MA state,
RSI regime, etc.) lives in sibling modules.
"""

from __future__ import annotations

from typing import cast

import pandas as pd


def sma(s: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return cast(pd.Series, s.rolling(window=period, min_periods=period).mean())


def ema(s: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (standard span-based)."""
    return cast(pd.Series, s.ewm(span=period, adjust=False, min_periods=period).mean())


def rolling_zscore(s: pd.Series, window: int = 30, min_obs: int = 30) -> pd.Series:
    """(x - rolling mean) / rolling std over a trailing ``window``.

    Returns NaN for any position with fewer than ``min_obs`` observations
    so early-period values don't produce spurious z-scores from tiny
    samples. ``window`` and ``min_obs`` are independent — pass a smaller
    ``min_obs`` to start emitting values earlier, but ≥ 30 is the
    standard guard against thin samples.
    """
    if window < 2:
        raise ValueError(f"window must be >= 2 (got {window})")
    if min_obs < 2:
        raise ValueError(f"min_obs must be >= 2 (got {min_obs})")
    mean = s.rolling(window=window, min_periods=min_obs).mean()
    std = s.rolling(window=window, min_periods=min_obs).std()
    return cast(pd.Series, (s - mean) / std)


def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = cast(
        pd.Series, gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    )
    avg_loss = cast(
        pd.Series, loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    )
    rs = avg_gain / avg_loss
    out = cast(pd.Series, 100 - 100 / (1 + rs))
    return cast(pd.Series, out.where(avg_loss != 0, 100.0))


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average True Range using Wilder's smoothing."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return cast(pd.Series, tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean())


def macd(
    s: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> pd.DataFrame:
    """MACD line, signal line, and histogram."""
    macd_line = ema(s, fast_period) - ema(s, slow_period)
    signal_line = macd_line.ewm(
        span=signal_period, adjust=False, min_periods=signal_period
    ).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist}
    )
