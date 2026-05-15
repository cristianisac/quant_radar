"""Hydrate ``DataRef``s into DataFrames using the source adapters.

This module is what turns saved card specs into live data on the screen.
It calls source-level ``fetch_*`` functions which themselves read from
the disk cache — within TTL no network is touched.
"""

from __future__ import annotations

import pandas as pd

from quant_radar.cards.spec import DataRef
from quant_radar.sources import coinpaprika_src, fred_src, yfinance_src


def hydrate(ref: DataRef, *, refresh: bool = False) -> pd.DataFrame:
    """Return the DataFrame referenced by ``ref`` (cache-first)."""
    if ref.source == "yfinance" and ref.kind == "ohlcv":
        return yfinance_src.fetch_ohlcv(
            ref.name,
            interval=ref.interval,
            start=ref.start,
            end=ref.end,
            refresh=refresh,
        )
    if ref.source == "fred" and ref.kind == "macro":
        return fred_src.fetch_macro_series(
            ref.name, start=ref.start, end=ref.end, refresh=refresh
        )
    if ref.source == "coinpaprika" and ref.kind == "ohlcv":
        return coinpaprika_src.fetch_ohlcv(
            ref.name, start=ref.start, end=ref.end, refresh=refresh
        )
    raise ValueError(f"unsupported data ref: source={ref.source!r} kind={ref.kind!r}")
