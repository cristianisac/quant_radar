"""Finnhub adapter — news + insider transactions on the free tier.

Requires ``FINNHUB_API_KEY`` in the environment. The news surface
returns ``list[dict]`` (intentionally non-conforming to the Source
ABC). The insider-transactions surface returns a DataFrame and DOES
conform via the ``_FinnhubInsiderSource`` class below.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import pandas as pd
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


# --- Insider transactions (kind="insider") -------------------------------
#
# Finnhub free tier exposes /stock/insider-transactions with full per-trade
# detail (transaction price, share count, code, derivative flag, source).
# Returns a DataFrame indexed by transactionDate.


def fetch_insider_transactions(
    symbol: str, *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Per-filing insider transactions for ``symbol``."""
    from quant_radar.cache import CacheKey, get_or_fetch
    from quant_radar.sources.base import TTL_DAILY_SEC

    key = CacheKey(
        source=SOURCE, kind="insider", name=symbol.upper(), interval="event",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        resp = requests.get(
            f"{_BASE}/stock/insider-transactions",
            params={"symbol": symbol.upper(), "token": _key()},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json() or {}
        items = body.get("data") or []
        rows: list[dict[str, Any]] = []
        for it in items:
            ts_raw = it.get("transactionDate") or it.get("filingDate")
            if not ts_raw:
                continue
            try:
                ts = pd.to_datetime(ts_raw, utc=True)
            except Exception:
                continue
            rows.append({
                "timestamp": ts,
                "transaction_price": float(it.get("transactionPrice") or 0.0),
                "share": int(it.get("share") or 0),
                "change": int(it.get("change") or 0),
                "transaction_code": it.get("transactionCode") or "",
                "insider_name": it.get("name") or "",
                "filing_date": str(it.get("filingDate") or ""),
                "is_derivative": bool(it.get("isDerivative") or False),
                "source": it.get("source") or "",
            })
        if not rows:
            return pd.DataFrame(columns=[
                "transaction_price", "share", "change", "transaction_code",
                "insider_name", "filing_date", "is_derivative", "source",
            ])
        df = pd.DataFrame(rows).set_index("timestamp").sort_index(ascending=False)
        df.index.name = "timestamp"
        return df

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=TTL_DAILY_SEC,
    )


# --- Earnings + IPO calendars -------------------------------------------
#
# Both endpoints return per-event rows. ``ref.name`` accepts a window
# literal like "30d" (default), "7d", "60d", "90d". Anything else falls
# back to "30d". ``ref.start/end`` if both set override the window.


def _window_to_dates(name: str) -> tuple[datetime, datetime]:
    from datetime import timedelta
    name_norm = (name or "30d").strip().lower()
    days = 30
    if name_norm.endswith("d"):
        try:
            days = int(name_norm[:-1])
        except ValueError:
            days = 30
    start = datetime.now(UTC)
    end = start + timedelta(days=max(1, min(days, 90)))
    return start, end


def fetch_earnings_calendar(
    name: str = "30d", *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Earnings calendar for the next ``name``-day window."""
    from quant_radar.cache import CacheKey, get_or_fetch
    from quant_radar.sources.base import TTL_INTRADAY_SEC

    if start is None or end is None:
        start, end = _window_to_dates(name)

    key = CacheKey(
        source=SOURCE, kind="earnings_calendar", name=name, interval="event",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        if start is None or end is None:
            start, end = _window_to_dates(name)
        resp = requests.get(
            f"{_BASE}/calendar/earnings",
            params={
                "from": start.date().isoformat(),
                "to": end.date().isoformat(),
                "token": _key(),
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json() or {}
        items = body.get("earningsCalendar") or []
        rows: list[dict[str, Any]] = []
        for it in items:
            try:
                ts = pd.to_datetime(it.get("date"), utc=True)
            except Exception:
                continue

            def _f(v: Any) -> float | None:
                if v is None or v == "":
                    return None
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None

            rows.append({
                "timestamp": ts,
                "symbol": it.get("symbol") or "",
                "eps_estimate": _f(it.get("epsEstimate")),
                "eps_actual": _f(it.get("epsActual")),
                "revenue_estimate": _f(it.get("revenueEstimate")),
                "revenue_actual": _f(it.get("revenueActual")),
                "hour": it.get("hour") or "",
                "quarter": int(it.get("quarter") or 0),
                "year": int(it.get("year") or 0),
            })
        if not rows:
            return pd.DataFrame(columns=[
                "symbol", "eps_estimate", "eps_actual",
                "revenue_estimate", "revenue_actual",
                "hour", "quarter", "year",
            ])
        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        df.index.name = "timestamp"
        return df

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=TTL_INTRADAY_SEC,
    )


def fetch_ipo_calendar(
    name: str = "30d", *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """IPO calendar for the next ``name``-day window."""
    from quant_radar.cache import CacheKey, get_or_fetch
    from quant_radar.sources.base import TTL_INTRADAY_SEC

    if start is None or end is None:
        start, end = _window_to_dates(name)

    key = CacheKey(
        source=SOURCE, kind="ipo_calendar", name=name, interval="event",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        if start is None or end is None:
            start, end = _window_to_dates(name)
        resp = requests.get(
            f"{_BASE}/calendar/ipo",
            params={
                "from": start.date().isoformat(),
                "to": end.date().isoformat(),
                "token": _key(),
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json() or {}
        items = body.get("ipoCalendar") or []
        rows: list[dict[str, Any]] = []
        for it in items:
            try:
                ts = pd.to_datetime(it.get("date"), utc=True)
            except Exception:
                continue
            rows.append({
                "timestamp": ts,
                "symbol": it.get("symbol") or "",
                "company_name": it.get("name") or "",
                "exchange": it.get("exchange") or "",
                "number_of_shares": int(it.get("numberOfShares") or 0),
                "price": str(it.get("price") or ""),
                "status": it.get("status") or "",
                "total_shares_value": int(it.get("totalSharesValue") or 0),
            })
        if not rows:
            return pd.DataFrame(columns=[
                "symbol", "company_name", "exchange", "number_of_shares",
                "price", "status", "total_shares_value",
            ])
        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        df.index.name = "timestamp"
        return df

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=TTL_INTRADAY_SEC,
    )


def _register() -> None:  # pragma: no cover
    from quant_radar.cards.spec import DataRef as _DataRef
    from quant_radar.sources.base_source import Source, register_source
    from quant_radar.sources.catalog import CATALOG

    _ABC_KINDS = {"insider", "earnings_calendar", "ipo_calendar"}

    class _FinnhubSource(Source):
        """Single ABC adapter dispatching across all DataFrame kinds.

        ``news`` is intentionally NOT routed here — it returns
        ``list[dict]`` and goes through ``tools.news`` callers directly.
        """
        capability = CATALOG["finnhub"]

        def supports(self, ref: _DataRef) -> bool:
            return ref.source == SOURCE and ref.kind in _ABC_KINDS

        def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
            if ref.kind == "insider":
                return fetch_insider_transactions(
                    ref.name, start=ref.start, end=ref.end, refresh=refresh,
                )
            if ref.kind == "earnings_calendar":
                return fetch_earnings_calendar(
                    ref.name or "30d", start=ref.start, end=ref.end, refresh=refresh,
                )
            if ref.kind == "ipo_calendar":
                return fetch_ipo_calendar(
                    ref.name or "30d", start=ref.start, end=ref.end, refresh=refresh,
                )
            raise ValueError(f"finnhub: unsupported kind {ref.kind!r}")

        def search(self, query: str, *, limit: int = 20) -> list[dict]:
            return []

        def describe(self, name: str) -> dict | None:
            return None

    register_source(_FinnhubSource())


_register()
