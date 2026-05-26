"""Agent-facing sentiment tools.

Implements the multi-source routing described in
``quant_radar/sources/kind_coverage.py`` for ``kind="sentiment"``:

- ``fetch_sentiment(ticker)`` tries the primary source (Alpha Vantage)
  first and silently falls back to Marketaux when AV's daily quota is
  exhausted. The agent never needs to know which source ultimately
  served the data unless it asks.

- ``describe_sentiment_routing(kind="sentiment")`` returns the
  structured comparison from kind_coverage.py so the agent can read
  it at session start and make informed choices when the user asks
  about *which* source to use or *why*.

Per-ticker sentiment cards should reach for this rather than calling
the source adapters directly — it bakes the routing logic in one
place instead of pushing it onto every caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from quant_radar.cards.spec import DataRef
from quant_radar.sources import kind_coverage
from quant_radar.sources.hydrate import hydrate


def fetch_sentiment(
    ticker: str, *,
    source: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Fetch per-ticker news sentiment with automatic provider fallback.

    Returns ``(df, source_used)`` so the caller can show which provider
    actually served the data (useful in the UI when displaying scoped
    sentiment over time).

    If ``source`` is set, only that source is tried (no fallback).
    Otherwise walks the chain declared in kind_coverage.sentiment.

    Each row in the returned DataFrame is one article that mentions the
    ticker, with columns: sentiment_score, relevance_score,
    overall_score, sentiment_label, title, url, article_source, topics.
    """
    cov = kind_coverage.get_coverage("sentiment")
    if cov is None:
        raise RuntimeError("kind_coverage missing 'sentiment' entry")

    chain = [source] if source else cov.get("default_chain", [])
    if not chain:
        raise RuntimeError("no providers configured for kind='sentiment'")

    last_err: Exception | None = None
    for src in chain:
        try:
            df = hydrate(
                DataRef(
                    source=src, kind="sentiment",
                    name=ticker.upper(), interval="event",
                    start=start, end=end,
                ),
                refresh=refresh,
            )
            return df, src
        except Exception as e:  # noqa: BLE001 — try next provider
            last_err = e
            continue

    raise RuntimeError(
        f"All sentiment providers in {chain} failed for {ticker}. "
        f"Last error: {type(last_err).__name__}: {last_err}"
    )


def describe_sentiment_routing() -> dict[str, Any]:
    """Return the multi-source routing record for kind='sentiment'.

    The agent should call this once per session (or whenever the user
    asks about sentiment sources) to understand the relationship
    between providers — which is primary, which is fallback, which is
    complementary, and what each one's coverage/limits look like.
    """
    cov = kind_coverage.get_coverage("sentiment")
    return cov or {}
