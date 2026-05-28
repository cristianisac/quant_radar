from quant_radar.sources import (
    alphavantage_src,
    apewisdom_src,
    binance_src,
    cme_futures_src,  # noqa: F401 — registry data for kind=futures_aggregate
    finnhub_src,  # noqa: F401 — already imported, kept for explicit registration
    fred_src,
    gdelt_src,
    marketaux_src,
    openbb_src,
    polygon_src,
    tradingeconomics_src,
    yfinance_src,
)

__all__ = [
    "alphavantage_src",
    "apewisdom_src",
    "binance_src",
    "cme_futures_src",
    "finnhub_src",
    "fred_src",
    "gdelt_src",
    "marketaux_src",
    "openbb_src",
    "polygon_src",
    "tradingeconomics_src",
    "yfinance_src",
]
