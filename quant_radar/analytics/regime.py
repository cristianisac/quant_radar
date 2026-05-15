"""Single-bar interpretations for indicator state.

These tiny helpers turn a numeric indicator series into a short label the
agent can quote: ``overbought``, ``high_volatility``, etc. They're
intentionally simple — the LLM does any nuanced narrative on top.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

RSIState = Literal["overbought", "oversold", "neutral", "unknown"]
VolRegime = Literal["high", "elevated", "normal", "low", "unknown"]


def classify_rsi(
    rsi_series: pd.Series, oversold: float = 30.0, overbought: float = 70.0
) -> RSIState:
    if len(rsi_series) == 0 or pd.isna(rsi_series.iloc[-1]):
        return "unknown"
    v = float(rsi_series.iloc[-1])
    if v >= overbought:
        return "overbought"
    if v <= oversold:
        return "oversold"
    return "neutral"


def classify_volatility(atr_series: pd.Series, lookback: int = 90) -> VolRegime:
    """Compare last ATR to its own recent distribution (percentile-based)."""
    clean = atr_series.dropna()
    if len(clean) < lookback:
        return "unknown"
    last = float(clean.iloc[-1])
    window = clean.iloc[-lookback:]
    q25, q50, q75 = (float(window.quantile(q)) for q in (0.25, 0.5, 0.75))
    if last >= q75 * 1.25:
        return "high"
    if last >= q75:
        return "elevated"
    if last <= q25:
        return "low"
    if last <= q50 * 1.1:
        return "normal"
    return "normal"
