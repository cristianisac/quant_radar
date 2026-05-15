"""Definitive GDELT reliability check.

Runs a few query shapes (single term, AND, OR, quoted phrase) over a
day and a week, prints success rate, latency, and item counts. The
adapter's retry-with-back-off is in play.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from quant_radar.sources import gdelt_src

QUERIES = [
    "Bitcoin",
    '"AI stocks"',
    "Fed AND rates",
    "Bitcoin OR Ethereum",
    "stocks",
    "Nvidia earnings",
]

WINDOWS = [
    ("24h", None, None),  # default timespan=1d
    ("7d", datetime.now(UTC) - timedelta(days=7), datetime.now(UTC)),
]

for label, start, end in WINDOWS:
    print(f"\n=== Window: {label} ===")
    for q in QUERIES:
        t0 = time.perf_counter()
        try:
            items = gdelt_src.fetch_news(q, start=start, end=end, max_records=20)
            dt = time.perf_counter() - t0
            print(f"  {q!r:30s} → {len(items):3d} items in {dt:5.2f}s")
        except Exception as e:
            dt = time.perf_counter() - t0
            print(
                f"  {q!r:30s} → {type(e).__name__} in {dt:5.2f}s: {str(e)[:80]}"
            )
