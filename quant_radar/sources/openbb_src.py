"""OpenBB-backed adapters for FMP + Tiingo.

Both providers are in the OpenBB Platform's bundled equity coverage, so
the adapter is a thin parametric wrapper around
``obb.equity.price.historical(provider="<name>")`` + ``obb.equity.search``
+ ``obb.equity.profile``. One ~30-line subclass per provider — adding
Intrinio, Alpha Vantage, etc. later is the same pattern.

Polygon lives in ``polygon_src.py`` (raw HTTP) — OpenBB removed Polygon
from its bundled providers due to licensing, so the waterfall picks
step 3 (existing client / raw HTTP) for it.

API keys flow via the standard .env → docker --env-file → OPENBB
credentials store wiring below. Idempotent at module import.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import cast

import pandas as pd

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.cards.spec import DataRef as _DataRef
from quant_radar.sources.base import ttl_for_interval
from quant_radar.sources.base_source import Source, register_source
from quant_radar.sources.catalog import CATALOG


def _wire_openbb_credentials() -> None:
    """Map our .env keys into OpenBB's credentials store.

    Our env vars are ``<PROVIDER>_API_KEY`` (FMP_API_KEY, TIINGO_API_KEY,
    POLYGON_API_KEY). OpenBB uses slightly different names per provider
    (e.g. ``tiingo_token`` not ``tiingo_api_key``). Map them once at
    import time so the rest of the adapter can call ``obb.*`` without
    worrying about credentials.
    """
    from openbb import obb

    mapping = {
        "fmp_api_key": "FMP_API_KEY",
        "tiingo_token": "TIINGO_API_KEY",
        "polygon_api_key": "POLYGON_API_KEY",  # honored if/when openbb-polygon is installed
        "fred_api_key": "FRED_API_KEY",
        "finnhub_api_key": "FINNHUB_API_KEY",
    }
    for openbb_name, env_var in mapping.items():
        value = os.environ.get(env_var)
        if value:
            try:
                setattr(obb.user.credentials, openbb_name, value)
            except Exception:
                # Credential name unsupported in installed version — skip silently.
                pass


_wire_openbb_credentials()


# OpenBB ships canonical OHLCV columns plus per-provider extras (vwap,
# adj_open, etc.). Normalize to the schema we declared in the catalog.
_CANONICAL = ("open", "high", "low", "close", "volume")


# Schema columns kept per kind. For fundamentals we keep *everything*
# OpenBB returns (typically 30-50 financial fields) — the schema in the
# catalog declares the minimum we promise; the audit checks
# declared⊆actual which allows extras. The agent / UI use the full
# payload.
_KEEP_BY_KIND: dict[str, tuple[str, ...]] = {
    "ohlcv": _CANONICAL,
    "forex": ("open", "high", "low", "close"),
    "crypto": _CANONICAL,
}

_FUNDAMENTAL_KINDS = {"income", "balance", "cash"}
_DIVIDEND_KINDS = {"dividends", "splits"}
_ESTIMATE_KINDS = {"estimates"}


def _fetch_corporate_event(
    obb_module, provider: str, kind: str, symbol: str,
) -> pd.DataFrame:
    """Fetch dividends or splits — corporate-action events.

    Both endpoints return per-event rows. We anchor the index on the
    most semantic timestamp per kind:
    - dividends: ex_dividend_date
    - splits: the upstream date column (string in some providers)
    """
    if kind == "dividends":
        # FMP free tier caps dividends limit at 5.
        result = obb_module.equity.fundamental.dividends(
            symbol=symbol, provider=provider, limit=5,
        )
        df = result.to_df()
        if df.empty:
            return df
        df["ex_dividend_date"] = pd.to_datetime(df["ex_dividend_date"], utc=True)
        df = df.set_index("ex_dividend_date").sort_index(ascending=False)
    else:  # splits
        # historical_splits doesn't have a documented free-tier cap;
        # 20 worked in the live probe but mirror the conservative
        # limit=5 anyway to stay under tier-paranoia.
        result = obb_module.equity.fundamental.historical_splits(
            symbol=symbol, provider=provider, limit=5,
        )
        df = result.to_df()
        if df.empty:
            return df
        # historical_splits returns a string date index; coerce + lift to col.
        df = df.reset_index()
        # The reset column is "index" containing date strings.
        date_col = "index" if "index" in df.columns else df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col], utc=True)
        df = df.rename(columns={date_col: "split_date"}).set_index("split_date")
        df = df.sort_index(ascending=False)
    df.index.name = "timestamp"
    return df


def _fetch_estimates(
    obb_module, provider: str, symbol: str,
) -> pd.DataFrame:
    """Forward analyst estimates — revenue / EPS / EBITDA ranges.

    Indexed by the estimated fiscal-period-end date so estimates align
    naturally on the same time axis as actual fundamentals.
    """
    # FMP free tier caps estimates limit at 10.
    result = obb_module.equity.estimates.historical(
        symbol=symbol, provider=provider, limit=10,
    )
    df = result.to_df()
    if df.empty:
        return df
    # OpenBB returns a string-date index; lift + coerce.
    df = df.reset_index()
    date_col = "index" if "index" in df.columns else df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], utc=True)
    df = df.rename(columns={date_col: "estimate_date"}).set_index("estimate_date")
    df = df.sort_index(ascending=False)
    df.index.name = "timestamp"
    return df


def _fetch_fundamentals(
    obb_module, provider: str, kind: str, symbol: str, interval: str,
) -> pd.DataFrame:
    """Fetch one statement type (income/balance/cash) for ``symbol``.

    ``interval`` carries the period selector ("quarter" or "annual").
    Defaults to quarter when interval is anything else (1d, etc.) since
    fundamentals aren't truly daily.
    """
    period = "annual" if interval in ("annual", "yearly", "1y") else "quarter"
    method = getattr(obb_module.equity.fundamental, kind)
    # FMP free tier caps ``limit`` at 5; respect the lowest common
    # denominator across providers we wrap here. ~5 quarters or 5
    # years of history is enough for a card-view preview, and the
    # user always has the option to upgrade if more history matters.
    result = method(symbol=symbol, provider=provider, period=period, limit=5)
    df = result.to_df()
    if df.empty:
        return df
    # OpenBB returns RangeIndex with `period_ending` as a column.
    # Anchor each row to its fiscal-period-end date so the cache layer
    # + the chart card's DatetimeIndex assumption hold.
    df["period_ending"] = pd.to_datetime(df["period_ending"], utc=True)
    df = df.set_index("period_ending").sort_index()
    df.index.name = "timestamp"
    return df


def _fetch_via_openbb(
    provider: str, kind: str, symbol: str,
    start: datetime | None, end: datetime | None, interval: str,
) -> pd.DataFrame:
    from openbb import obb

    if kind in _FUNDAMENTAL_KINDS:
        df = _fetch_fundamentals(obb, provider, kind, symbol, interval)
    elif kind in _DIVIDEND_KINDS:
        df = _fetch_corporate_event(obb, provider, kind, symbol)
    elif kind in _ESTIMATE_KINDS:
        df = _fetch_estimates(obb, provider, symbol)
    else:
        df = None

    if df is not None:
        if not df.empty and (start is not None or end is not None):
            if start is not None:
                df = df[df.index >= pd.Timestamp(start, tz="UTC")]
            if end is not None:
                df = df[df.index <= pd.Timestamp(end, tz="UTC")]
        return df

    kwargs: dict[str, object] = {
        "symbol": symbol, "provider": provider, "interval": interval,
    }
    if start is not None:
        kwargs["start_date"] = start.strftime("%Y-%m-%d")
    if end is not None:
        kwargs["end_date"] = end.strftime("%Y-%m-%d")

    if kind == "ohlcv":
        result = obb.equity.price.historical(**kwargs)  # type: ignore[arg-type]
    elif kind == "forex":
        result = obb.currency.price.historical(**kwargs)  # type: ignore[arg-type]
    elif kind == "crypto":
        result = obb.crypto.price.historical(**kwargs)  # type: ignore[arg-type]
    else:
        raise ValueError(f"unsupported kind for OpenBB adapter: {kind!r}")

    df = result.to_df()
    if df.empty:
        return df
    df.columns = [str(c).lower() for c in df.columns]
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "timestamp"
    keep = _KEEP_BY_KIND.get(kind, _CANONICAL)
    return df[[c for c in keep if c in df.columns]]


def _search_via_openbb(provider: str, query: str, limit: int) -> list[dict]:
    from openbb import obb

    try:
        result = obb.equity.search(query=query, provider=provider)
        df = result.to_df()
        if df.empty:
            return []
    except Exception:
        return []
    out: list[dict] = []
    for _, row in df.head(limit).iterrows():
        d = row.to_dict()
        out.append({
            "symbol": d.get("symbol") or d.get("ticker"),
            "longname": d.get("name") or d.get("longname") or d.get("long_name"),
            "exchange": d.get("exchange") or d.get("exchange_short_name"),
        })
    return [h for h in out if h.get("symbol")]


def _describe_via_openbb(provider: str, symbol: str) -> dict | None:
    from openbb import obb

    try:
        result = obb.equity.profile(symbol=symbol, provider=provider)
        df = result.to_df()
        if df.empty:
            return None
    except Exception:
        return None
    row = df.iloc[0].to_dict()
    return {
        "symbol": symbol,
        "longname": row.get("name") or row.get("longname") or row.get("long_name"),
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "exchange": row.get("exchange"),
        "summary": (row.get("description") or row.get("long_description") or "")[:400],
    }


class _OpenBBOHLCVSource(Source):
    """Parametric base. Concrete subclasses set PROVIDER + capability.

    Supports OHLCV equity historical (``kind="ohlcv"``) and forex
    historical (``kind="forex"``). Forex uses OpenBB's currency
    namespace; equity uses equity.price.historical.
    """

    # Each concrete subclass overrides PROVIDER + KINDS based on what
    # their provider actually serves on the free tier.
    PROVIDER: str = ""
    KINDS: tuple[str, ...] = ("ohlcv", "forex")

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == self.PROVIDER and ref.kind in self.KINDS

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        key = CacheKey(
            source=self.PROVIDER, kind=ref.kind,
            name=ref.name, interval=ref.interval,
        )

        def fetcher(start, end):
            return _fetch_via_openbb(
                self.PROVIDER, ref.kind, ref.name, start, end, ref.interval,
            )

        return get_or_fetch(
            key, fetcher, start=ref.start, end=ref.end,
            refresh=refresh, ttl_seconds=ttl_for_interval(ref.interval),
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        # Search hits equity.search regardless of kind. For forex
        # discovery, the agent should reach for `list_all` / `examples`
        # in the catalog — FX universes are bounded and well-known.
        return _search_via_openbb(self.PROVIDER, query, limit)

    def describe(self, name: str) -> dict | None:
        return _describe_via_openbb(self.PROVIDER, name)


class _FMPSource(_OpenBBOHLCVSource):
    PROVIDER = "fmp"
    capability = CATALOG["fmp"]
    # FMP free tier coverage (live-verified): OHLCV + forex + fundamentals
    # trio + dividends + splits + forward analyst estimates. Insider
    # trading + ETF holdings are 402 paid on free tier — see Finnhub
    # adapter for insider trading; ETF holdings deferred entirely.
    KINDS = (
        "ohlcv", "forex", "crypto",
        "income", "balance", "cash",
        "dividends", "splits", "estimates",
    )


class _TiingoSource(_OpenBBOHLCVSource):
    PROVIDER = "tiingo"
    capability = CATALOG["tiingo"]
    # Tiingo free tier: OHLCV + forex + crypto. Fundamentals are paid.
    KINDS = ("ohlcv", "forex", "crypto")


register_source(_FMPSource())
register_source(_TiingoSource())
