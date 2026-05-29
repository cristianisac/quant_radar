"""ETF AUM (Assets Under Management) via yfinance Ticker.info.

yfinance exposes ``totalAssets`` on its ``Ticker(sym).info`` payload.
For US-listed ETFs this is populated cleanly. For European ETPs / ETCs
the field is null even when yfinance knows the ticker — that's a
yfinance product-type limitation, not a missing-data one. Our probe
of 536 Bloomberg-style tickers (data/etf_yfinance_coverage.csv)
verified ~44% by ticker count, but ~80-90% by dollar AUM, because the
US Bitcoin spot ETFs (IBIT $61.9B, FBTC $14.2B, GBTC $11.5B, etc.)
dominate the asset class.

This adapter accepts Bloomberg-style tickers (``IBIT US``,
``BITC SW``, ``BTCC/B CN``) AND raw Yahoo symbols (``IBIT``,
``BITC.SW``, ``BTCC-B.TO``). Conversion is done via
``BLOOMBERG_TO_YAHOO_SUFFIX``. Returns the latest AUM snapshot —
yfinance only exposes the current-day value, not a history.

Returned DataFrame for ``kind="etf_aum"`` (``name`` = one ticker):

    index   timestamp (now, UTC; fund snapshots are point-in-time)
    columns
        bloomberg     normalized Bloomberg ticker (or "" if direct Yahoo)
        yahoo         the Yahoo symbol used
        longname      from yfinance Ticker.info.longName/shortName
        aum           USD; None if yfinance has the ticker but not AUM
        nav           NAV price; None if not exposed
        category      fund category (e.g., "Digital Assets")
        currency      base currency
        status        ok | no_aum | not_found
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import yfinance as yf

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.sources.base import TTL_DAILY_SEC

# Bloomberg exchange suffix → Yahoo Finance suffix.
# Validated 2026-05-28 against a 536-ticker probe — see
# data/etf_yfinance_coverage.csv for per-exchange hit rates.
BLOOMBERG_TO_YAHOO_SUFFIX: dict[str, str | None] = {
    "US": "",       # NYSE / Nasdaq — no suffix on Yahoo
    "GR": ".DE",    # Xetra
    "SW": ".SW",    # SIX Swiss
    "CN": ".TO",    # Toronto Stock Exchange
    "BZ": ".SA",    # B3 (Brazil)
    "AU": ".AX",    # ASX
    "HK": ".HK",    # HKEX (numeric tickers padded to 4 digits)
    "IT": ".MI",    # Borsa Italiana
    "NA": ".AS",    # Euronext Amsterdam
    "FP": ".PA",    # Euronext Paris
    "SS": ".ST",    # Nasdaq Stockholm
    "PW": ".WA",    # WSE Warsaw
    "LN": ".L",     # LSE London
    "NZ": ".NZ",
    "AV": ".VI",    # Vienna
    "KZ": None,     # Yahoo doesn't list Kazakhstan
}

_SCHEMA_COLS = [
    "bloomberg", "yahoo", "longname", "aum", "nav",
    "category", "currency", "status",
]


def bloomberg_to_yahoo(bbg: str) -> str | None:
    """Normalize a Bloomberg-style ticker to a Yahoo symbol.

    Accepts forms like ``IBIT US``, ``BITC SW``, ``BTCC/B CN``.
    Strings without a trailing space-exchange (e.g. ``IBIT``,
    ``BITC.SW``) are assumed to already be Yahoo symbols and returned
    verbatim.

    Returns ``None`` when the exchange isn't in our conversion table
    (e.g. Kazakhstan).
    """
    s = (bbg or "").strip()
    if not s:
        return None
    parts = s.split()
    if len(parts) == 1:
        # No space → assume already a Yahoo symbol.
        return s
    root, exchange = parts[0], parts[-1]
    suffix = BLOOMBERG_TO_YAHOO_SUFFIX.get(exchange)
    if suffix is None:
        return None
    root_y = root.replace("/", "-")
    if exchange == "HK" and root_y.isdigit():
        root_y = root_y.zfill(4)
    return f"{root_y}{suffix}"


def _lookup_one(ticker: str) -> dict[str, Any]:
    """Return one row's worth of metadata for ``ticker``."""
    bbg = ticker if " " in ticker else ""
    yahoo = bloomberg_to_yahoo(ticker) or ticker
    if not yahoo:
        return {
            "bloomberg": bbg, "yahoo": "", "longname": None,
            "aum": None, "nav": None, "category": None, "currency": None,
            "status": "unmapped",
        }
    try:
        info = yf.Ticker(yahoo).info or {}
    except Exception:  # noqa: BLE001
        info = {}
    aum = info.get("totalAssets")
    longname = info.get("longName") or info.get("shortName")
    if aum:
        status = "ok"
    elif longname:
        status = "no_aum"  # yfinance knows the ticker; AUM field null
    else:
        status = "not_found"
    return {
        "bloomberg": bbg,
        "yahoo": yahoo,
        "longname": longname,
        "aum": float(aum) if aum else None,
        "nav": info.get("navPrice"),
        "category": info.get("category"),
        "currency": info.get("currency"),
        "status": status,
    }


def fetch_etf_aum_single(
    ticker: str, *, refresh: bool = False,
) -> pd.DataFrame:
    """One-row DataFrame for ``ticker``. ``timestamp`` index = fetch time.

    Accepts a comma-separated list of tickers too — dispatched to the
    scorecard fetcher so a single DataRef can hydrate a multi-row
    TableCard. Each row is stamped with a synthetic 1-second-apart
    timestamp so the DatetimeIndex stays unique (some downstream code
    expects monotonic indexing).
    """
    if "," in ticker:
        return fetch_etf_aum_scorecard(
            [t.strip() for t in ticker.split(",") if t.strip()],
            refresh=refresh,
        )
    key = CacheKey(
        source="yfinance", kind="etf_aum",
        name=ticker, interval="snapshot",
    )

    def fetcher(start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        ts = pd.Timestamp.now(tz=UTC)
        row = _lookup_one(ticker)
        return pd.DataFrame([row], index=[ts])[_SCHEMA_COLS].rename_axis("timestamp")

    return get_or_fetch(
        key, fetcher, start=None, end=None, refresh=refresh,
        ttl_seconds=TTL_DAILY_SEC,
    )


def fetch_etf_aum_scorecard(
    tickers: list[str], *, refresh: bool = False,
) -> pd.DataFrame:
    """Multi-row scorecard DataFrame for a list of tickers.

    Sorted by ``aum`` descending. Indexed by a synthetic DatetimeIndex
    (UTC ``now`` + 1-second stride per row) so it round-trips through
    the /data endpoint, which requires a DatetimeIndex.
    """
    key = CacheKey(
        source="yfinance", kind="etf_aum",
        name=",".join(tickers), interval="scorecard",
    )

    def fetcher(start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        rows = [_lookup_one(t) for t in tickers]
        df = pd.DataFrame(rows)[_SCHEMA_COLS]
        # TableCard reverses rows ("most-recent first" — financial-
        # statement convention). For a scorecard we want the biggest
        # row shown first after that reverse, so we sort ASC here and
        # give the biggest the LATEST synthetic timestamp. NaN AUM rows
        # land at the top of the ASC sort and end up at the bottom of
        # the rendered table — which matches user expectation (real
        # numbers first, missing-data rows pushed to the end).
        df = df.sort_values("aum", ascending=True, na_position="first")
        base = pd.Timestamp.now(tz=UTC)
        df.index = pd.DatetimeIndex(
            [base + pd.Timedelta(seconds=i) for i in range(len(df))],
            name="timestamp",
        )
        return df

    return get_or_fetch(
        key, fetcher, start=None, end=None, refresh=refresh,
        ttl_seconds=TTL_DAILY_SEC,
    )


def fetch_etf_aum_batch(
    tickers: list[str], *, refresh: bool = False,
) -> pd.DataFrame:
    """Multi-ticker AUM scorecard.

    Returns a DataFrame indexed by Bloomberg-or-Yahoo ticker (one row
    each) with the same columns as ``fetch_etf_aum_single``. Sorted by
    ``aum`` descending so the scorecard shows the biggest funds first.

    No timestamp index — this is a scorecard, not a time series.
    """
    rows: list[dict[str, Any]] = []
    for t in tickers:
        rows.append({"ticker": t, **_lookup_one(t)})
    if not rows:
        return pd.DataFrame(columns=["ticker", *_SCHEMA_COLS])
    df = pd.DataFrame(rows).set_index("ticker")
    df = df.sort_values("aum", ascending=False, na_position="last")
    return df
