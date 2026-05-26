"""Apewisdom — Reddit-driven social sentiment / mention-velocity.

Aggregates ticker mentions across r/wallstreetbets, r/stocks,
r/investing, r/cryptocurrency, etc. and publishes a ranked list with
24h-prior comparison. The public endpoint is unauthenticated:

    https://apewisdom.io/api/v1.0/filter/<filter>/page/<n>

We expose this as ``kind="social_sentiment"``. One DataRef call returns
the current snapshot row for one ticker (mention count, 24h-prior
mention count, upvotes, rank, 24h-prior rank) anchored to the fetch
timestamp.

Entity-theme coverage (per user's listed buckets):
- stocks / ETFs / listed companies → ``all-stocks`` filter (~870 tickers)
- crypto → ``all-crypto`` filter (~160 tickers, suffix ``.X``)
- commodities / bonds → only surface insofar as a listed proxy exists
  (e.g. GLD, TLT). Pure-commodity / pure-bond social sentiment is not
  meaningful on Reddit-aggregator data — Apewisdom only tracks named
  tickers. ``describe(name)`` returns a best-effort match.

Returned DataFrame shape (one row, the current snapshot — Apewisdom
publishes a rolling window, not a time-series, so each refresh
overwrites with the latest values):

    index: timestamp (the fetch time, tz-aware UTC)
    columns:
        ticker, name
        mentions, mentions_24h_ago, mentions_change_pct
        upvotes, rank, rank_24h_ago
        filter (which Apewisdom filter the ticker came from)

If the ticker is not currently in either filter's leaderboard (i.e.
nobody on the tracked subreddits is talking about it right now), an
empty DataFrame is returned — that's a real signal, not an error.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.cards.spec import DataRef as _DataRef
from quant_radar.sources.base import TTL_INTRADAY_SEC
from quant_radar.sources.base_source import Source, register_source
from quant_radar.sources.catalog import CATALOG

SOURCE = "apewisdom"
_BASE = "https://apewisdom.io/api/v1.0/filter"
_TIMEOUT = 25

# Filters that cover the entity-themes the agent should reach for:
# - all-stocks: stocks + ETFs + listed companies (incl. bond/commodity ETFs)
# - all-crypto: every crypto ticker tracked, suffix .X
_ENTITY_FILTERS = ("all-stocks", "all-crypto")

_COLUMNS = [
    "ticker", "name",
    "mentions", "mentions_24h_ago", "mentions_change_pct",
    "upvotes", "rank", "rank_24h_ago", "filter",
]


def _fetch_filter(filter_name: str) -> list[dict[str, Any]]:
    """Walk every page of one Apewisdom filter and return the full leaderboard."""
    page = 1
    out: list[dict[str, Any]] = []
    while True:
        url = f"{_BASE}/{filter_name}/page/{page}"
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        body = resp.json() or {}
        results = body.get("results") or []
        if not results:
            break
        for row in results:
            row["_filter"] = filter_name
            out.append(row)
        pages = int(body.get("pages") or 1)
        if page >= pages:
            break
        page += 1
    return out


def _change_pct(now: int, prior: int) -> float:
    if prior <= 0:
        # New entry — no prior baseline; surface as a very large positive number
        # rather than NaN so the UI can flag it as a fresh-viral signal.
        return float(now) * 100.0 if now > 0 else 0.0
    return ((now - prior) / prior) * 100.0


def _normalize_ticker(t: str) -> str:
    """Match user-supplied tickers against Apewisdom's storage convention.

    Apewisdom stores crypto tickers with a ``.X`` suffix (BTC.X, ETH.X)
    and stocks bare (AAPL). We accept either shape from the caller and
    match leniently.
    """
    return t.strip().upper().removesuffix(".X")


def _fetch_snapshot(ticker: str) -> pd.DataFrame:
    target = _normalize_ticker(ticker)
    rows: list[dict[str, Any]] = []
    for f in _ENTITY_FILTERS:
        try:
            rows.extend(_fetch_filter(f))
        except Exception:  # noqa: BLE001 — try the next filter; partial data > none
            continue

    now = pd.Timestamp.now(tz=UTC)
    matched: list[dict[str, Any]] = []
    for r in rows:
        t = (r.get("ticker") or "").upper()
        if _normalize_ticker(t) != target:
            continue
        mentions = int(r.get("mentions") or 0)
        prior = int(r.get("mentions_24h_ago") or 0)
        matched.append({
            "timestamp": now,
            "ticker": t,
            "name": r.get("name") or "",
            "mentions": mentions,
            "mentions_24h_ago": prior,
            "mentions_change_pct": round(_change_pct(mentions, prior), 1),
            "upvotes": int(r.get("upvotes") or 0),
            "rank": int(r.get("rank") or 0),
            "rank_24h_ago": int(r.get("rank_24h_ago") or 0),
            "filter": r.get("_filter") or "",
        })

    if not matched:
        return pd.DataFrame(columns=_COLUMNS)

    # If the same symbol appears in both filters (unusual but possible for
    # ambiguous tickers), keep the row with the higher mention count.
    df = pd.DataFrame(matched).set_index("timestamp")
    df = df.sort_values("mentions", ascending=False).head(1)
    return df[_COLUMNS]


def fetch_social_sentiment(
    ticker: str, *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Cache-first wrapper around the snapshot fetch.

    ``start``/``end`` are accepted to satisfy the DataRef contract but
    ignored — Apewisdom's API only serves the current rolling-24h
    window. TTL is intraday (5 min) since the leaderboard updates
    continuously throughout the day.
    """
    key = CacheKey(
        source=SOURCE, kind="social_sentiment",
        name=_normalize_ticker(ticker), interval="snapshot",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        return _fetch_snapshot(ticker)

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=TTL_INTRADAY_SEC,
    )


# --- Source ABC adapter ---------------------------------------------------


class _ApewisdomSource(Source):
    capability = CATALOG["apewisdom"]

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind == "social_sentiment"

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        return fetch_social_sentiment(
            ref.name, start=ref.start, end=ref.end, refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        """Return top tickers whose name/symbol matches ``query``.

        Walks the current leaderboards once. Useful for the agent when
        the user asks "who's being talked about right now?".
        """
        q = query.strip().upper()
        if not q:
            return []
        out: list[dict] = []
        seen: set[str] = set()
        for f in _ENTITY_FILTERS:
            try:
                rows = _fetch_filter(f)
            except Exception:  # noqa: BLE001
                continue
            for r in rows:
                t = (r.get("ticker") or "").upper()
                name = (r.get("name") or "").upper()
                if q not in t and q not in name:
                    continue
                if t in seen:
                    continue
                seen.add(t)
                out.append({
                    "symbol": t,
                    "longname": r.get("name") or "",
                    "mentions": int(r.get("mentions") or 0),
                    "rank": int(r.get("rank") or 0),
                    "filter": f,
                })
                if len(out) >= limit:
                    return out
        return out

    def describe(self, name: str) -> dict | None:
        df = _fetch_snapshot(name)
        if df.empty:
            return None
        row = df.iloc[0].to_dict()
        return {
            "symbol": row["ticker"],
            "longname": row["name"],
            "mentions": row["mentions"],
            "mentions_24h_ago": row["mentions_24h_ago"],
            "mentions_change_pct": row["mentions_change_pct"],
            "rank": row["rank"],
            "filter": row["filter"],
        }

    def list_all(self, *, limit: int | None = None) -> list[dict]:
        """Enumerate the current full leaderboard across both filters."""
        out: list[dict] = []
        for f in _ENTITY_FILTERS:
            try:
                rows = _fetch_filter(f)
            except Exception:  # noqa: BLE001
                continue
            for r in rows:
                out.append({
                    "symbol": (r.get("ticker") or "").upper(),
                    "longname": r.get("name") or "",
                    "mentions": int(r.get("mentions") or 0),
                    "rank": int(r.get("rank") or 0),
                    "filter": f,
                })
                if limit is not None and len(out) >= limit:
                    return out
        return out


register_source(_ApewisdomSource())
