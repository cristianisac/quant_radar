"""Alpha Vantage NEWS_SENTIMENT — per-ticker news sentiment scores.

Primary source for ``kind="sentiment"``. The free tier has a tight
25 req/day quota; cache aggressively. For per-ticker sentiment we
hit ``function=NEWS_SENTIMENT`` and extract the row matching the
requested ticker from each article's ``ticker_sentiment`` array.

Returned DataFrame shape (one row per article that mentions the
requested ticker):

    index: timestamp (article published_at, tz-aware UTC)
    columns:
        sentiment_score   ticker-specific score in [-1, 1]
        relevance_score   how relevant the article is to this ticker [0, 1]
        overall_score     article overall sentiment [-1, 1]
        sentiment_label   string label (Bullish / Somewhat-Bullish / Neutral / ...)
        title             article title
        url               article url
        article_source    source domain (e.g. "Reuters", "CNBC")
        topics            comma-joined topic list (e.g. "Earnings, Technology")

The agent layer then aggregates as it needs (daily mean, rolling
average, latest only).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, cast

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.cards.spec import DataRef as _DataRef
from quant_radar.sources.base import TTL_DAILY_SEC
from quant_radar.sources.base_source import Source, register_source
from quant_radar.sources.catalog import CATALOG

SOURCE = "alphavantage"
_BASE = "https://www.alphavantage.co/query"
_TIMEOUT = 25
_LIMIT = 50  # max per call on free tier


def _key() -> str:
    k = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not k:
        raise RuntimeError(
            "ALPHAVANTAGE_API_KEY not set in .env "
            "(free signup at alphavantage.co/support/#api-key)"
        )
    return k


def _av_date(dt: datetime) -> str:
    # AV expects YYYYMMDDTHHMM
    return dt.strftime("%Y%m%dT%H%M")


def _parse_published(s: str) -> pd.Timestamp:
    # AV format: "20260524T143000"
    return pd.to_datetime(s, format="%Y%m%dT%H%M%S", utc=True)


def _fetch_news_sentiment(
    ticker: str, start: datetime | None, end: datetime | None,
) -> pd.DataFrame:
    """Pull NEWS_SENTIMENT for one ticker, return per-article rows for that ticker."""
    params: dict[str, str] = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker.upper(),
        "apikey": _key(),
        "limit": str(_LIMIT),
        "sort": "LATEST",
    }
    if start is not None:
        params["time_from"] = _av_date(start)
    if end is not None:
        params["time_to"] = _av_date(end)

    resp = requests.get(_BASE, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    body = resp.json() or {}

    # Quota / informational messages come back as 200 OK with a Note/Information field.
    if "Note" in body or "Information" in body:
        msg = body.get("Note") or body.get("Information") or ""
        raise RuntimeError(f"Alpha Vantage quota/notice: {msg[:200]}")

    rows: list[dict[str, Any]] = []
    target = ticker.upper()
    for art in body.get("feed", []) or []:
        # Find this article's per-ticker sentiment for the requested symbol.
        ticker_row: dict[str, Any] = {}
        for ts in art.get("ticker_sentiment", []) or []:
            if (ts.get("ticker") or "").upper() == target:
                ticker_row = ts
                break
        if not ticker_row:
            # Article was returned because AV matched the ticker filter but the
            # ticker_sentiment array doesn't include it (rare). Skip rather than
            # invent a score.
            continue

        try:
            ts_ts = _parse_published(art.get("time_published", ""))
        except Exception:
            continue

        topics = ", ".join(
            (t.get("topic") or "") for t in (art.get("topics") or [])
        )

        rows.append({
            "timestamp": ts_ts,
            "sentiment_score": float(ticker_row.get("ticker_sentiment_score", 0.0)),
            "relevance_score": float(ticker_row.get("relevance_score", 0.0)),
            "overall_score": float(art.get("overall_sentiment_score", 0.0)),
            "sentiment_label": ticker_row.get("ticker_sentiment_label", ""),
            "title": (art.get("title") or "")[:200],
            "url": art.get("url") or "",
            "article_source": art.get("source") or "",
            "topics": topics,
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


# --- Source ABC adapter ---------------------------------------------------


class _AlphaVantageSource(Source):
    capability = CATALOG["alphavantage"]

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind == "sentiment"

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        return fetch_sentiment(
            ref.name, start=ref.start, end=ref.end, refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        # AV doesn't have a free public symbol-search endpoint; the agent
        # should use yfinance/polygon search and pass the resolved ticker
        # to AV directly. Returning [] keeps the contract honest.
        return []

    def describe(self, name: str) -> dict | None:
        # No describe endpoint on free tier. Caller can use yfinance describe.
        return None


register_source(_AlphaVantageSource())
