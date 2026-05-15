"""GDELT news adapter — free, no API key.

Endpoint: ``https://api.gdeltproject.org/api/v2/doc/doc`` with
``mode=artlist&format=json``. We default to the last 24h when no
``start``/``end`` is given.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import requests

SOURCE = "gdelt"
_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT = 15
_USER_AGENT = "quant_radar/0.1 (research)"
_RETRY_DELAYS = (1.0, 3.0)  # back-off on 429 / 5xx


def _to_gdelt_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S")


def _parse_seendate(s: str) -> datetime | None:
    # GDELT returns e.g. "20250508T120000Z" — strict but predictable.
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None


def _normalize(article: dict) -> dict:
    return {
        "title": article.get("title", "").strip(),
        "url": article.get("url", ""),
        "source": article.get("domain", ""),
        "language": article.get("language"),
        "country": article.get("sourcecountry"),
        "published_at": (
            (_parse_seendate(article.get("seendate", "")) or datetime.now(UTC)).isoformat()
        ),
    }


def fetch_news(
    query: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_records: int = 20,
) -> list[dict]:
    params: dict[str, str] = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(min(max(max_records, 1), 250)),
        "sort": "datedesc",
    }
    if start is not None and end is not None:
        params["startdatetime"] = _to_gdelt_dt(start)
        params["enddatetime"] = _to_gdelt_dt(end)
    else:
        params["timespan"] = "1d"

    resp: requests.Response | None = None
    for delay in (*_RETRY_DELAYS, None):
        resp = requests.get(
            _BASE, params=params, timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        if resp.status_code < 500 and resp.status_code != 429:
            break
        if delay is None:
            break
        time.sleep(delay)
    assert resp is not None
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        return []
    return [_normalize(a) for a in data.get("articles", [])]
