"""Finnhub news adapter — free tier with API key.

Requires ``FINNHUB_API_KEY`` in the environment. Without it,
``fetch_general_news`` raises ``RuntimeError`` so the caller can fall
back to GDELT.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import requests

SOURCE = "finnhub"
_BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 15


def _key() -> str:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        raise RuntimeError(
            "FINNHUB_API_KEY not set. Either export it before running "
            "`make docker-shell` (pass with -e FINNHUB_API_KEY=...) or "
            "use GDELT as the news source."
        )
    return key


def _normalize(item: dict) -> dict:
    ts = item.get("datetime")
    if isinstance(ts, int | float):
        published = datetime.fromtimestamp(ts, tz=UTC).isoformat()
    else:
        published = datetime.now(UTC).isoformat()
    return {
        "title": item.get("headline", "").strip(),
        "url": item.get("url", ""),
        "source": item.get("source", "finnhub"),
        "summary": item.get("summary", "").strip(),
        "category": item.get("category"),
        "related": item.get("related"),
        "published_at": published,
    }


def fetch_general_news(*, category: str = "general", max_items: int = 20) -> list[dict]:
    resp = requests.get(
        f"{_BASE}/news",
        params={"category": category, "token": _key()},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    items = resp.json()
    if not isinstance(items, list):
        return []
    return [_normalize(it) for it in items[:max_items]]


def fetch_company_news(
    symbol: str, *, start: datetime, end: datetime, max_items: int = 20
) -> list[dict]:
    resp = requests.get(
        f"{_BASE}/company-news",
        params={
            "symbol": symbol,
            "from": start.date().isoformat(),
            "to": end.date().isoformat(),
            "token": _key(),
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    items = resp.json()
    if not isinstance(items, list):
        return []
    return [_normalize(it) for it in items[:max_items]]
