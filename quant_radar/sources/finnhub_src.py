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


def _register() -> None:  # pragma: no cover
    from quant_radar.cards.spec import DataRef as _DataRef
    from quant_radar.sources.base_source import Source, register_source
    from quant_radar.sources.catalog import CATALOG

    class _FinnhubInsiderSource(Source):
        capability = CATALOG["finnhub"]

        def supports(self, ref: _DataRef) -> bool:
            return ref.source == SOURCE and ref.kind == "insider"

        def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
            return fetch_insider_transactions(
                ref.name, start=ref.start, end=ref.end, refresh=refresh,
            )

        def search(self, query: str, *, limit: int = 20) -> list[dict]:
            return []

        def describe(self, name: str) -> dict | None:
            return None

    register_source(_FinnhubInsiderSource())


_register()
