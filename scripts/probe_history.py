"""Probe how far back each source actually returns data.

Forces ``refresh=True`` so the cache doesn't hide real API history.
"""

from __future__ import annotations

from datetime import UTC, datetime

from quant_radar.sources import binance_src, fred_src, yfinance_src

FAR_BACK = datetime(2000, 1, 1, tzinfo=UTC)

print("=" * 72)
print("BINANCE — earliest available daily candle (refresh=True)")
print("=" * 72)
for sym in ("BTC", "ETH", "SOL", "BNB", "XRP"):
    try:
        df = binance_src.fetch_ohlcv(sym, interval="1d", start=FAR_BACK, refresh=True)
        print(
            f"  {sym:6s} → first={df.index[0].date()}  "
            f"last={df.index[-1].date()}  bars={len(df)}"
        )
    except Exception as e:
        print(f"  {sym:6s} → error: {type(e).__name__}: {e}")

print("\n" + "=" * 72)
print("YFINANCE — earliest available daily bar (refresh=True)")
print("=" * 72)
for sym in ("AAPL", "SPY", "MSFT", "TSLA", "NVDA", "BTC-USD"):
    try:
        df = yfinance_src.fetch_ohlcv(sym, interval="1d", start=FAR_BACK, refresh=True)
        print(
            f"  {sym:8s} → first={df.index[0].date()}  "
            f"last={df.index[-1].date()}  bars={len(df)}"
        )
    except Exception as e:
        print(f"  {sym:8s} → error: {type(e).__name__}: {e}")

print("\n" + "=" * 72)
print("FRED — earliest available observation per series")
print("=" * 72)
for series in ("DGS10", "CPIAUCSL", "UNRATE", "GDP", "FEDFUNDS", "DEXUSEU"):
    try:
        df = fred_src.fetch_macro_series(series, start=FAR_BACK)
        # Native frequency: infer from row count vs span
        span_days = (df.index[-1] - df.index[0]).days
        freq = "daily" if span_days < len(df) * 5 else (
            "weekly" if span_days < len(df) * 10 else "monthly+"
        )
        print(
            f"  {series:9s} → first={df.index[0].date()}  last={df.index[-1].date()}  "
            f"bars={len(df)}  ~{freq}"
        )
    except Exception as e:
        print(f"  {series:9s} → error: {type(e).__name__}: {e}")
