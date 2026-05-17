"""Hydrate ``DataRef`` specs into DataFrames via the Source registry.

Single dispatch point that the API layer (``server.routes.data``) and
the agent's card-render path call. Cache-first via each adapter's
``get_or_fetch`` wiring — no network within TTL.

Importing the adapter modules below triggers their
``register_source(...)`` calls at module-load time; ``get_source`` then
resolves the right adapter by ``ref.source``.
"""

from __future__ import annotations

import pandas as pd

from quant_radar.cards.spec import DataRef

# Side-effect imports: each module calls register_source() at import time.
from quant_radar.sources import binance_src, fred_src, yfinance_src  # noqa: F401
from quant_radar.sources.base_source import get_source


def hydrate(ref: DataRef, *, refresh: bool = False) -> pd.DataFrame:
    """Return the DataFrame referenced by ``ref`` (cache-first)."""
    source = get_source(ref.source)
    if source is None or not source.supports(ref):
        raise ValueError(
            f"unsupported data ref: source={ref.source!r} kind={ref.kind!r}"
        )
    return source.fetch(ref, refresh=refresh)
