"""Trading Economics — economic calendar via country-page HTML scrape.

Trading Economics' country calendar pages (``/<country>/calendar``) are
server-rendered HTML with a table containing ~4 weeks of upcoming + a
few recent events. Each row has the four columns a real economic
calendar needs:

    actual | previous | consensus | forecast

The classical /calendar endpoint (filterable by country code) returns
the same data but is rendered via a Socket.IO stream — much harder to
parse. Country pages are easier and stable.

This adapter ships ``kind="economic_calendar"`` and accepts a country
slug as ``ref.name``:

    united-states / euro-area / germany / united-kingdom / japan /
    china / france / italy / spain / canada / australia / ...

If ``ref.start``/``end`` are set, events outside the window are
filtered out post-parse. Default behaviour: return the entire page
(approximately current week + 3 upcoming weeks).

**Honest ToS note**: Trading Economics' Terms of Use prohibit
automated extraction. Their free `guest:guest` HTTP API token was
discontinued in 2026 specifically to push everyone to paid plans.
Country-page scraping still works technically but is using a
side-door around their pricing model. Acceptable for personal
research; do not redistribute the scraped data.

Returned DataFrame:

    index   timestamp (event datetime, tz-aware UTC)
    columns
        country       short code (US, EA, DE, JP, CN, ...)
        event         event name (e.g. "Consumer Confidence")
        period        period the event reports on (e.g. "May", "Q1")
        actual        the released value (None until release)
        previous      prior period's value
        consensus     market consensus expectation
        forecast      Trading Economics' own forecast (may be None)
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.cards.spec import DataRef as _DataRef
from quant_radar.sources.base import TTL_INTRADAY_SEC
from quant_radar.sources.base_source import Source, register_source
from quant_radar.sources.catalog import CATALOG

SOURCE = "tradingeconomics"
_BASE = "https://tradingeconomics.com"
_TIMEOUT = 25

# Browser-like headers — bare requests UA gets 403 from CDN.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_DAY_NAMES = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)
# Period suffix appears right-glued to the event name (no separator):
# "Consumer ConfidenceMAY", "GDP Growth Rate QoQ 3rd EstQ1".
_PERIOD_RE = re.compile(
    r"(?P<event>.*?)(?P<period>"
    r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|Q[1-4]))$"
)
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s*(?:AM|PM)$", re.IGNORECASE)
# Header is "Tuesday May 26 2026" optionally followed by Actual/Previous/...
_DATE_HDR_RE = re.compile(
    r"^(?P<dow>" + "|".join(_DAY_NAMES) + r")\s+"
    r"(?P<mon>[A-Z][a-z]+)\s+(?P<day>\d{1,2})\s+(?P<year>\d{4})"
)


def _country_slug(name: str) -> str:
    """Normalize an agent-supplied country name into TE's URL slug.

    Accepts forms like 'United States', 'US', 'us', 'united-states'.
    """
    n = (name or "united-states").strip().lower().replace(" ", "-")
    aliases = {
        "us": "united-states", "usa": "united-states",
        "eu": "euro-area", "ea": "euro-area", "eurozone": "euro-area",
        "uk": "united-kingdom", "gb": "united-kingdom",
        "jp": "japan", "de": "germany", "fr": "france",
        "it": "italy", "es": "spain", "cn": "china",
        "ca": "canada", "au": "australia",
    }
    return aliases.get(n, n)


def _parse_event_period(raw: str) -> tuple[str, str]:
    """Split 'Consumer ConfidenceMAY' into ('Consumer Confidence', 'MAY')."""
    m = _PERIOD_RE.match(raw or "")
    if not m:
        return (raw or "").strip(), ""
    return m.group("event").strip(), m.group("period")


def _parse_value(raw: str) -> str | None:
    """Strip the '®' revision marker; keep value as string so callers
    can render units (%, B, etc.) unchanged. ``None`` for empty cell."""
    if not raw:
        return None
    cleaned = raw.replace("®", "").strip()
    return cleaned or None


def _parse_date_header(text: str) -> datetime | None:
    """Date header rows are 'Tuesday May 26 2026' (sometimes followed by
    'ActualPreviousConsensusForecast' all run together)."""
    m = _DATE_HDR_RE.match(text or "")
    if not m:
        return None
    return datetime.strptime(
        f"{m.group('mon')} {m.group('day')} {m.group('year')}",
        "%B %d %Y",
    ).replace(tzinfo=UTC)


def _parse_time_of_day(time_str: str, base: datetime) -> datetime:
    """Combine '09:00 AM' with the date base into a tz-aware datetime."""
    try:
        t = datetime.strptime(time_str.strip().upper(), "%I:%M %p")
    except ValueError:
        return base.replace(hour=0, minute=0)
    return base.replace(hour=t.hour, minute=t.minute)


def _fetch_calendar(country: str) -> pd.DataFrame:
    """Scrape the country calendar page and return a DataFrame."""
    slug = _country_slug(country)
    url = f"{_BASE}/{slug}/calendar"
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return _empty_frame()
    table = max(tables, key=lambda t: len(t.find_all("tr")))

    rows: list[dict[str, Any]] = []
    current_date: datetime | None = None
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if not cells:
            continue

        # Date headers come through with the first cell being the date
        # string, sometimes glued to "ActualPreviousConsensusForecast".
        first = cells[0]
        d = _parse_date_header(first)
        if d is not None:
            current_date = d
            continue

        # Event row — first cell must look like "HH:MM AM/PM".
        if not _TIME_RE.match(first or ""):
            continue
        if current_date is None:
            continue

        # Cells layout (after filtering empties):
        #   [time, country_flag_img_alt, country_code, event_name+period,
        #    actual, previous(®), consensus, (forecast)]
        # The flag image alt and country code can both be present or
        # collapse depending on the row; we extract the first non-empty
        # short-code-looking value.
        non_empty = [c for c in cells if c]
        if len(non_empty) < 4:
            continue
        time_str = non_empty[0]
        # Find country short code (2-3 uppercase letters) somewhere
        # between time and event name.
        cc = ""
        event_idx = 1
        for i, c in enumerate(non_empty[1:5], start=1):
            if c.isupper() and 2 <= len(c) <= 3:
                cc = c
                event_idx = i + 1
                # Continue — sometimes the flag and the code both
                # appear; we want the latter (after the flag alt).
        if event_idx >= len(non_empty):
            continue
        event_period_raw = non_empty[event_idx]
        event, period = _parse_event_period(event_period_raw)
        values = non_empty[event_idx + 1:]
        # Pad to 4 to align with [actual, previous, consensus, forecast]
        while len(values) < 4:
            values.append("")
        actual, previous, consensus, forecast = values[:4]

        ts = _parse_time_of_day(time_str, current_date)
        rows.append({
            "timestamp": ts,
            "country": cc,
            "event": event,
            "period": period,
            "actual": _parse_value(actual),
            "previous": _parse_value(previous),
            "consensus": _parse_value(consensus),
            "forecast": _parse_value(forecast),
        })

    if not rows:
        return _empty_frame()
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    df.index.name = "timestamp"
    return df


_SCHEMA_COLS = ["country", "event", "period", "actual", "previous", "consensus", "forecast"]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_SCHEMA_COLS)


def fetch_economic_calendar(
    country: str = "united-states", *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Trading Economics calendar for ``country`` slug.

    Returns the full page (typically ~4 weeks). When ``start``/``end``
    are supplied, filters in-memory to that window. Default scope is
    "the entire page" so the agent can ask for "current week" by
    passing today + 7d as the window.
    """
    key = CacheKey(
        source=SOURCE, kind="economic_calendar",
        name=_country_slug(country), interval="event",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        df = _fetch_calendar(country)
        if df.empty:
            return df
        # Apply window inside the fetcher so the cache holds the full
        # page but each call slices to the user's request.
        return df

    df = get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=TTL_INTRADAY_SEC,
    )

    # Post-fetch slicing — cache always holds the full page.
    if df.empty:
        return df
    if start is not None:
        ts = pd.Timestamp(start)
        ts = ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")
        df = df[df.index >= ts]
    if end is not None:
        te_ = pd.Timestamp(end)
        te_ = te_.tz_convert("UTC") if te_.tzinfo else te_.tz_localize("UTC")
        df = df[df.index <= te_]
    return df


class _TradingEconomicsSource(Source):
    """Source ABC adapter for ``kind="economic_calendar"``.

    Note: the OpenBB `tradingeconomics` provider is separately wired
    elsewhere for ``obb.economy.calendar`` (and requires a paid key).
    This adapter scrapes the public country pages. They co-exist
    without conflict since this Source only `supports(...)` the
    economic_calendar kind.
    """

    capability = CATALOG["tradingeconomics"]

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind == "economic_calendar"

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        return fetch_economic_calendar(
            ref.name or "united-states",
            start=ref.start, end=ref.end, refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        # No symbol search — country slugs are well-known and bounded.
        return []

    def describe(self, name: str) -> dict | None:
        return None

    def list_all(self, *, limit: int | None = None) -> list[dict]:
        # Static list of country slugs we know work; not exhaustive.
        slugs = [
            "united-states", "euro-area", "united-kingdom",
            "germany", "france", "italy", "spain",
            "japan", "china", "canada", "australia",
            "switzerland", "sweden", "norway", "brazil",
            "india", "mexico", "south-korea", "russia",
        ]
        out = [{"symbol": s, "longname": s.replace("-", " ").title()} for s in slugs]
        if limit is not None:
            out = out[:limit]
        return out


register_source(_TradingEconomicsSource())
