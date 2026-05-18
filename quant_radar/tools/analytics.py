"""Agent-facing analytics tools.

Design principle: tools are **column-agnostic**. They operate on whatever
price column the frame exposes — ``close`` for OHLCV, ``value`` for FRED
macro, or any explicitly named column. The agent decides what makes
sense; we don't gate by source. If the user asks for RSI on a treasury
yield, we compute it (RSI on a yield can be informative — the user is
allowed to ask).

For tools that genuinely need multiple OHLCV columns (e.g. ATR needs
high+low+close), we silently skip the offending indicator and continue
rather than aborting the whole call.
"""

from __future__ import annotations

from typing import cast

import pandas as pd

from quant_radar.analytics import indicators
from quant_radar.analytics.ma import analyze_moving_averages as _analyze_ma
from quant_radar.analytics.regime import classify_rsi, classify_volatility
from quant_radar.analytics.returns import DEFAULT_PERIODS
from quant_radar.analytics.returns import compute_returns as _compute_returns

# Priority order when no column is explicitly named: ``close`` (OHLCV
# convention), then ``value`` (FRED/macro convention), then the only
# numeric column if there's exactly one. Anything else and we raise.
_PRICE_COL_FALLBACKS = ("close", "value")


def _pick_price_column(df: pd.DataFrame, hint: str | None = None) -> str:
    """Resolve which column to treat as the price series.

    Used so the same tool works on yfinance OHLCV (``close``), FRED
    (``value``), or any single-column time series without the caller
    having to know the upstream's column convention.
    """
    if hint is not None:
        if hint in df.columns:
            return hint
        raise ValueError(
            f"requested column {hint!r} not in DataFrame (have: {list(df.columns)})"
        )
    for candidate in _PRICE_COL_FALLBACKS:
        if candidate in df.columns:
            return candidate
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(numeric_cols) == 1:
        return numeric_cols[0]
    raise ValueError(
        f"could not infer price column (have: {list(df.columns)}). "
        f"pass `price_col=` or `column=` explicitly."
    )


def compute_returns(
    df: pd.DataFrame,
    *,
    price_col: str | None = None,
    periods: tuple[str, ...] | list[str] = DEFAULT_PERIODS,
) -> dict[str, float | None]:
    """Period-over-period returns. Works on any single price column.

    ``price_col`` defaults to auto-detect (close → value → only numeric).
    """
    col = _pick_price_column(df, hint=price_col)
    return _compute_returns(cast(pd.Series, df[col]), periods=periods)


def compute_indicators(
    df: pd.DataFrame,
    *,
    which: tuple[str, ...] | list[str] = ("sma_50", "sma_200", "rsi", "atr", "macd"),
    price_col: str | None = None,
    # Back-compat alias: callers that previously passed `indicators=` keep working.
    indicators: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    """Append the requested indicator columns. Column-agnostic.

    Indicators that need OHLC columns (ATR needs high+low+close) are
    silently skipped if the required columns are absent — useful when
    the user asks for indicators on a non-OHLCV series like FRED macro.

    Accepts both ``which=`` and ``indicators=`` for the indicator list
    (the latter is the legacy name kept for back-compat).
    """
    from quant_radar.analytics.indicators import (
        atr as _atr,
        ema as _ema,
        macd as _macd,
        rsi as _rsi,
        sma as _sma,
    )

    requested = indicators if indicators is not None else which
    col = _pick_price_column(df, hint=price_col)
    price = cast(pd.Series, df[col])
    out = df.copy()
    for name in requested:
        if name == "macd":
            out = out.join(_macd(price), how="left")
        elif name == "sma_50":
            out[name] = _sma(price, 50)
        elif name == "sma_200":
            out[name] = _sma(price, 200)
        elif name == "ema_12":
            out[name] = _ema(price, 12)
        elif name == "ema_26":
            out[name] = _ema(price, 26)
        elif name in ("rsi", "rsi_14"):
            out[name] = _rsi(price, 14)
        elif name in ("atr", "atr_14"):
            # ATR is the only multi-column indicator we expose. Skip
            # silently when OHLC isn't there rather than aborting the call.
            if {"high", "low", "close"}.issubset(df.columns):
                out[name] = _atr(
                    cast(pd.Series, df["high"]),
                    cast(pd.Series, df["low"]),
                    cast(pd.Series, df["close"]),
                    14,
                )
        else:
            raise ValueError(f"unknown indicator: {name}")
    return out


def analyze_moving_averages(
    df: pd.DataFrame,
    *,
    price_col: str | None = None,
    fast_period: int = 50,
    slow_period: int = 200,
    asset: str | None = None,
) -> dict:
    """MA crossover state. Column-agnostic."""
    col = _pick_price_column(df, hint=price_col)
    return _analyze_ma(
        cast(pd.Series, df[col]),
        fast_period=fast_period,
        slow_period=slow_period,
        asset=asset,
    )


def rolling_zscore(
    df: pd.DataFrame,
    *,
    column: str | None = None,
    window: int = 30,
    min_obs: int = 30,
) -> pd.DataFrame:
    """Append a ``zscore_{window}`` column with rolling z-score.

    ``column`` defaults to auto-detect (close → value → only numeric).
    ``min_obs`` is the standard 30-observation guard against thin samples.
    """
    col = _pick_price_column(df, hint=column)
    out = df.copy()
    out[f"zscore_{window}"] = indicators.rolling_zscore(
        cast(pd.Series, df[col]), window=window, min_obs=min_obs
    )
    return out


def analyze_indicators(
    df: pd.DataFrame, *, price_col: str | None = None,
) -> dict[str, str | None]:
    """Return state labels for RSI and (when OHLC is available) volatility.

    ``volatility_regime`` is ``None`` on non-OHLCV frames (no ATR possible).
    """
    col = _pick_price_column(df, hint=price_col)
    rsi_series = indicators.rsi(cast(pd.Series, df[col]), 14)
    out: dict[str, str | None] = {"rsi_state": classify_rsi(rsi_series)}
    if {"high", "low", "close"}.issubset(df.columns):
        atr_series = indicators.atr(
            cast(pd.Series, df["high"]),
            cast(pd.Series, df["low"]),
            cast(pd.Series, df["close"]),
            14,
        )
        out["volatility_regime"] = classify_volatility(atr_series)
    else:
        out["volatility_regime"] = None
    return out
