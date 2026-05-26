"""GDELT news adapter — free, no API key.

Endpoint: ``https://api.gdeltproject.org/api/v2/doc/doc`` with
``mode=artlist&format=json``. We default to the last 24h when no
``start``/``end`` is given.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pandas as pd
import requests

SOURCE = "gdelt"
_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT = 30
_USER_AGENT = "quant_radar/0.1 (research)"
_RETRY_DELAYS = (1.0, 3.0, 8.0)  # back-off on 429 / 5xx / timeout


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
    last_exc: Exception | None = None
    for delay in (*_RETRY_DELAYS, None):
        try:
            resp = requests.get(
                _BASE, params=params, timeout=_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
            )
        except (
            requests.ReadTimeout, requests.ConnectTimeout,
            requests.exceptions.SSLError, requests.ConnectionError,
        ) as e:
            last_exc = e
            if delay is None:
                raise
            time.sleep(delay)
            continue
        if resp.status_code < 500 and resp.status_code != 429:
            break
        if delay is None:
            break
        time.sleep(delay)
    if resp is None:
        # All attempts timed out
        raise last_exc if last_exc else RuntimeError("gdelt: no response")
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        return []
    return [_normalize(a) for a in data.get("articles", [])]


# --- News tone time-series (mode=timelinetone) ---------------------------
#
# Per-article tone isn't exposed on `mode=artlist`. What GDELT *does*
# expose is `mode=timelinetone` — average article tone for a query
# across time, with hourly resolution on short windows. That's actually
# more useful than per-article tone for macro-mood reads ("how has the
# tone of crypto coverage shifted over the past week?").
#
# Returned DataFrame:
#   index   timestamp (tz-aware UTC, hourly on ≤7d windows, daily beyond)
#   tone    average article tone for the query at that timestamp,
#           roughly in [-10, +10] (GDELT tone is a centered metric;
#           negative = pessimistic / conflict, positive = optimistic)


def fetch_tone_timeline(
    query: str, *,
    start: datetime | None = None,
    end: datetime | None = None,
    timespan: str = "7d",
) -> pd.DataFrame:
    """Fetch GDELT average-tone timeline for ``query``.

    ``start``+``end`` take precedence over ``timespan`` when both set.
    ``timespan`` accepts GDELT's notation: "1d", "7d", "1w", "1m", "3m".
    """
    params: dict[str, str] = {
        "query": query,
        "mode": "timelinetone",
        "format": "json",
    }
    if start is not None and end is not None:
        params["startdatetime"] = _to_gdelt_dt(start)
        params["enddatetime"] = _to_gdelt_dt(end)
    else:
        params["timespan"] = timespan

    resp: requests.Response | None = None
    last_exc: Exception | None = None
    for delay in (*_RETRY_DELAYS, None):
        try:
            resp = requests.get(
                _BASE, params=params, timeout=_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
            )
        except (
            requests.ReadTimeout, requests.ConnectTimeout,
            requests.exceptions.SSLError, requests.ConnectionError,
        ) as e:
            last_exc = e
            if delay is None:
                raise
            time.sleep(delay)
            continue
        if resp.status_code < 500 and resp.status_code != 429:
            break
        if delay is None:
            break
        time.sleep(delay)
    if resp is None:
        raise last_exc if last_exc else RuntimeError("gdelt: no response")
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        return pd.DataFrame(columns=["tone"])

    rows: list[dict] = []
    for series in data.get("timeline", []) or []:
        if series.get("series") != "Average Tone":
            continue
        for point in series.get("data", []) or []:
            ts = _parse_seendate(point.get("date") or "")
            if ts is None:
                continue
            try:
                rows.append({"timestamp": ts, "tone": float(point.get("value", 0))})
            except (TypeError, ValueError):
                continue
        break

    if not rows:
        return pd.DataFrame(columns=["tone"])
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    df.index.name = "timestamp"
    return df


# --- Source ABC adapter for kind="news_tone" -----------------------------
#
# GDELT also has a separate news-article surface (`fetch_news` above) which
# returns list[dict] and intentionally does not conform to the time-series
# Source ABC. The Source subclass below is scoped to news_tone only.


def _fetch_news_tone_for_ref(ref):  # type: ignore[no-untyped-def]
    """Cache-first hydrator for kind='news_tone'."""
    from quant_radar.cache import CacheKey, get_or_fetch
    from quant_radar.sources.base import TTL_INTRADAY_SEC

    key = CacheKey(
        source=SOURCE, kind="news_tone",
        name=ref.name, interval=ref.interval or "1h",
    )

    def fetcher(start=None, end=None):
        return fetch_tone_timeline(ref.name, start=start, end=end)

    return get_or_fetch(
        key, fetcher, start=ref.start, end=ref.end,
        ttl_seconds=TTL_INTRADAY_SEC,
    )


def _register() -> None:  # pragma: no cover — side effect at import time
    from quant_radar.cards.spec import DataRef as _DataRef
    from quant_radar.sources.base_source import Source, register_source
    from quant_radar.sources.catalog import CATALOG

    class _GdeltSource(Source):
        capability = CATALOG["gdelt"]

        def supports(self, ref: _DataRef) -> bool:
            return ref.source == SOURCE and ref.kind == "news_tone"

        def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
            return _fetch_news_tone_for_ref(ref)

        def search(self, query: str, *, limit: int = 20) -> list[dict]:
            # GDELT has no symbol search — queries are Lucene strings.
            return []

        def describe(self, name: str) -> dict | None:
            return None

    register_source(_GdeltSource())


_register()
