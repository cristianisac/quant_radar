"""Marketaux — per-ticker news sentiment (fallback to Alpha Vantage).

Same kind contract as alphavantage_src (``kind="sentiment"``). Returns
a per-article DataFrame with the entity-specific sentiment score for
the requested symbol.

Free tier: 100 req/day, 1 req/sec. Wider symbol universe than AV
(better coverage for small caps + international tickers).

Shape mirrors Alpha Vantage's so a card built against AV "just works"
against Marketaux without UI changes:

    index: timestamp (article published_at, tz-aware UTC)
    columns:
        sentiment_score   entity sentiment [-1, 1]
        relevance_score   match_score normalized to [0, 1]
        overall_score     not provided by Marketaux; copied from sentiment_score
        sentiment_label   derived from sentiment_score sign
        title             article title
        url               article url
        article_source    publisher domain
        topics            comma-joined topic list (when available)
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.cards.spec import DataRef as _DataRef
from quant_radar.sources.base import TTL_DAILY_SEC
from quant_radar.sources.base_source import Source, register_source
from quant_radar.sources.catalog import CATALOG

SOURCE = "marketaux"
_BASE = "https://api.marketaux.com/v1/news/all"
_TIMEOUT = 25
_LIMIT = 3  # max per call on free tier


def _key() -> str:
    k = os.environ.get("MARKETAUX_API_KEY")
    if not k:
        raise RuntimeError(
            "MARKETAUX_API_KEY not set in .env "
            "(free signup at marketaux.com/account/dashboard)"
        )
    return k


def _label_from_score(score: float) -> str:
    """Crude labeling so cards have a categorical badge like AV's."""
    if score >= 0.35:
        return "Bullish"
    if score >= 0.10:
        return "Somewhat-Bullish"
    if score > -0.10:
        return "Neutral"
    if score > -0.35:
        return "Somewhat-Bearish"
    return "Bearish"


def _fetch_news_sentiment(
    ticker: str, start: datetime | None, end: datetime | None,
) -> pd.DataFrame:
    target = ticker.upper()
    params: dict[str, Any] = {
        "symbols": target,
        "filter_entities": "true",
        "language": "en",
        "api_token": _key(),
        "limit": _LIMIT,
        "sort": "published_desc",
    }
    if start is not None:
        params["published_after"] = start.strftime("%Y-%m-%dT%H:%M:%S")
    if end is not None:
        params["published_before"] = end.strftime("%Y-%m-%dT%H:%M:%S")

    resp = requests.get(_BASE, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    body = resp.json() or {}
    if "error" in body:
        raise RuntimeError(f"Marketaux error: {body['error']}")

    rows: list[dict[str, Any]] = []
    for art in body.get("data", []) or []:
        # Pull the entity record for the requested symbol.
        entity: dict[str, Any] = {}
        for e in art.get("entities") or []:
            if (e.get("symbol") or "").upper() == target:
                entity = e
                break
        if not entity:
            continue

        try:
            ts = pd.to_datetime(art.get("published_at"), utc=True)
        except Exception:
            continue

        score = float(entity.get("sentiment_score") or 0.0)
        # match_score is 0..10 on Marketaux; normalize to 0..1 for parity
        # with AV's relevance_score.
        match = float(entity.get("match_score") or 0.0)
        relevance = min(match / 10.0, 1.0)

        rows.append({
            "timestamp": ts,
            "sentiment_score": score,
            "relevance_score": relevance,
            "overall_score": score,
            "sentiment_label": _label_from_score(score),
            "title": (art.get("title") or "")[:200],
            "url": art.get("url") or "",
            "article_source": art.get("source") or "",
            "topics": "",  # Marketaux doesn't expose topics in the free response
        })

    if not rows:
        return pd.DataFrame(columns=[
            "sentiment_score", "relevance_score", "overall_score",
            "sentiment_label", "title", "url", "article_source", "topics",
        ])

    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    return df


def fetch_sentiment(
    ticker: str, *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    key = CacheKey(
        source=SOURCE, kind="sentiment", name=ticker.upper(), interval="event",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        return _fetch_news_sentiment(ticker, start, end)

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=TTL_DAILY_SEC,
    )


class _MarketauxSource(Source):
    capability = CATALOG["marketaux"]

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind == "sentiment"

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        return fetch_sentiment(
            ref.name, start=ref.start, end=ref.end, refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        # Marketaux has /v1/entity/search but only on paid plans.
        # Defer to yfinance / polygon for symbol discovery.
        return []

    def describe(self, name: str) -> dict | None:
        return None


register_source(_MarketauxSource())
