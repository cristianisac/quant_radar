"""Agent-facing analytics tools.

These functions are the public API the chat agent calls. They accept a
DataFrame (OHLCV from a source adapter) plus simple kwargs, validate
their inputs, and return either an enriched DataFrame or a dict.
"""

from __future__ import annotations

from typing import cast

import pandas as pd

from quant_radar.analytics import indicators
from quant_radar.analytics.ma import analyze_moving_averages as _analyze_ma
from quant_radar.analytics.regime import classify_rsi, classify_volatility
from quant_radar.analytics.returns import DEFAULT_PERIODS
from quant_radar.analytics.returns import compute_returns as _compute_returns

_INDICATOR_SPECS = {
    "sma_50": lambda df: indicators.sma(df["close"], 50),
    "sma_200": lambda df: indicators.sma(df["close"], 200),
    "ema_12": lambda df: indicators.ema(df["close"], 12),
    "ema_26": lambda df: indicators.ema(df["close"], 26),
    "rsi": lambda df: indicators.rsi(df["close"], 14),
    "rsi_14": lambda df: indicators.rsi(df["close"], 14),
    "atr": lambda df: indicators.atr(df["high"], df["low"], df["close"], 14),
    "atr_14": lambda df: indicators.atr(df["high"], df["low"], df["close"], 14),
}

DEFAULT_INDICATORS: tuple[str, ...] = (
    "sma_50",
    "sma_200",
    "rsi",
    "atr",
    "macd",
)


def compute_returns(
    df: pd.DataFrame,
    *,
    price_col: str = "close",
    periods: tuple[str, ...] | list[str] = DEFAULT_PERIODS,
) -> dict[str, float | None]:
    """Period-over-period returns from a price DataFrame."""
    if price_col not in df.columns:
        raise ValueError(f"price column '{price_col}' not in DataFrame")
    return _compute_returns(cast(pd.Series, df[price_col]), periods=periods)


def compute_indicators(
    df: pd.DataFrame,
    *,
    indicators: tuple[str, ...] | list[str] = DEFAULT_INDICATORS,
) -> pd.DataFrame:
    """Return ``df`` with the requested indicator columns appended."""
    if "close" not in df.columns:
        raise ValueError("DataFrame must contain a 'close' column")
    out = df.copy()
    for name in indicators:
        if name == "macd":
            macd_df = _macd_columns(df)
            out = out.join(macd_df, how="left")
            continue
        if name not in _INDICATOR_SPECS:
            raise ValueError(f"unknown indicator: {name}")
        out[name] = _INDICATOR_SPECS[name](df)
    return out


def _macd_columns(df: pd.DataFrame) -> pd.DataFrame:
    from quant_radar.analytics.indicators import macd

    return macd(cast(pd.Series, df["close"]))


def analyze_moving_averages(
    df: pd.DataFrame,
    *,
    price_col: str = "close",
    fast_period: int = 50,
    slow_period: int = 200,
    asset: str | None = None,
) -> dict:
    if price_col not in df.columns:
        raise ValueError(f"price column '{price_col}' not in DataFrame")
    return _analyze_ma(
        cast(pd.Series, df[price_col]),
        fast_period=fast_period,
        slow_period=slow_period,
        asset=asset,
    )


def analyze_indicators(df: pd.DataFrame) -> dict[str, str]:
    """Return state labels for RSI and volatility based on the last bar."""
    enriched = compute_indicators(df, indicators=("rsi", "atr"))
    return {
        "rsi_state": classify_rsi(cast(pd.Series, enriched["rsi"])),
        "volatility_regime": classify_volatility(cast(pd.Series, enriched["atr"])),
    }
