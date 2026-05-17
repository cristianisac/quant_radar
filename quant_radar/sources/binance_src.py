"""Binance public spot API adapter — free, no key, no signup.

Endpoint: ``GET https://api.binance.com/api/v3/klines``. Free tier
allows up to 1200 weight/min from one IP, and OHLCV requests cost 1-2
each, so realistic use never hits the limit.

Symbol convention: case-insensitive. Pre-formed pairs are passed
through (``BTCUSDT``, ``ETHBTC``). Bare base symbols ('BTC', 'ETH',
'SOL') are mapped to '<base>USDT' since that's almost always what the
user means.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import cast

import pandas as pd
import requests

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.sources.base import ttl_for_interval

SOURCE = "binance"
_BASE = "https://api.binance.com/api/v3/klines"
_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"
_COINGECKO_LIST_URL = "https://api.coingecko.com/api/v3/coins/list"
_TIMEOUT = 15
_LIMIT_MAX = 1000

# Cached at first use. Binance doesn't return asset long names, so we
# enrich from CoinGecko's free /coins/list endpoint (no key required).
_EXCHANGE_INFO_CACHE: list[dict] | None = None
_ASSET_NAME_CACHE: dict[str, str] = {}

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1w",
    "1mo": "1M",
}

_DEFAULT_LOOKBACK = {
    "1m": timedelta(days=2),
    "5m": timedelta(days=30),
    "15m": timedelta(days=60),
    "1h": timedelta(days=365),
    "1d": timedelta(days=5 * 365),
    "1w": timedelta(days=10 * 365),
    "1mo": timedelta(days=25 * 365),
}

_QUOTE_SUFFIXES = ("USDT", "BUSD", "USDC", "FDUSD", "TUSD", "BTC", "ETH", "BNB", "EUR", "GBP")


def to_binance_symbol(s: str) -> str:
    """Normalize a user-supplied symbol to a Binance spot pair.

    Bare base symbols ("BTC", "ETH", "SOL") map to ``<base>USDT``. The
    input must be strictly longer than a quote suffix for that suffix to
    count — otherwise "BTC" alone would match the "BTC" quote and be
    passed through as a degenerate pair.
    """
    norm = s.upper().replace("-", "").replace("/", "").replace("_", "")
    for suffix in _QUOTE_SUFFIXES:
        if len(norm) > len(suffix) and norm.endswith(suffix):
            return norm
    return norm + "USDT"


def _to_binance_interval(interval: str) -> str:
    if interval not in _INTERVAL_MAP:
        raise ValueError(f"unsupported interval for binance: {interval}")
    return _INTERVAL_MAP[interval]


def _ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.astimezone(UTC).timestamp() * 1000)


def _default_start(interval: str) -> datetime:
    return datetime.now(UTC) - _DEFAULT_LOOKBACK.get(interval, timedelta(days=5 * 365))


def _fetch_page(
    symbol: str, interval: str, start_ms: int, end_ms: int
) -> list[list]:
    params: dict[str, str | int] = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": _LIMIT_MAX,
    }
    resp = requests.get(_BASE, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _fetch(
    symbol: str, interval: str, start: datetime | None, end: datetime | None
) -> pd.DataFrame:
    sym = to_binance_symbol(symbol)
    bin_interval = _to_binance_interval(interval)
    if start is None:
        start = _default_start(interval)
    if end is None:
        end = datetime.now(UTC)

    start_ms = _ms(start)
    end_ms = _ms(end)

    rows: list[list] = []
    cursor = start_ms
    while cursor < end_ms:
        page = _fetch_page(sym, bin_interval, cursor, end_ms)
        if not page:
            break
        rows.extend(page)
        last_close_ms = int(page[-1][6])
        if last_close_ms <= cursor or len(page) < _LIMIT_MAX:
            break
        cursor = last_close_ms + 1
        time.sleep(0.05)  # be polite

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    out = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col])
    out = out.set_index("timestamp").sort_index()
    return cast(pd.DataFrame, out)


def fetch_ohlcv(
    symbol: str,
    *,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch OHLCV bars for ``symbol`` from Binance, cached on disk.

    Examples:
        >>> fetch_ohlcv("BTC")        # → BTCUSDT
        >>> fetch_ohlcv("ETHUSDT")    # passthrough
        >>> fetch_ohlcv("SOL", interval="1h", start=...)
    """
    sym = to_binance_symbol(symbol)
    key = CacheKey(source=SOURCE, kind="ohlcv", name=sym, interval=interval)

    def fetcher(start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        return _fetch(symbol, interval, start, end)

    return get_or_fetch(
        key,
        fetcher,
        start=start,
        end=end,
        refresh=refresh,
        ttl_seconds=ttl_for_interval(interval),
    )


# --- Source-ABC adapter ---------------------------------------------------

from quant_radar.cards.spec import DataRef as _DataRef  # noqa: E402
from quant_radar.sources.base_source import Source, register_source  # noqa: E402
from quant_radar.sources.catalog import CATALOG  # noqa: E402


def _load_exchange_info() -> list[dict]:
    """Cached list of every spot pair from /api/v3/exchangeInfo.

    Each entry: ``{symbol, baseAsset, quoteAsset, status}``. Cached for
    the process lifetime; the agent rarely sees new listings within a
    session.
    """
    global _EXCHANGE_INFO_CACHE
    if _EXCHANGE_INFO_CACHE is not None:
        return _EXCHANGE_INFO_CACHE
    try:
        resp = requests.get(_EXCHANGE_INFO_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
        symbols = resp.json().get("symbols", []) or []
    except (requests.RequestException, ValueError):
        _EXCHANGE_INFO_CACHE = []
        return _EXCHANGE_INFO_CACHE
    _EXCHANGE_INFO_CACHE = [
        {
            "symbol": s.get("symbol"),
            "baseAsset": s.get("baseAsset"),
            "quoteAsset": s.get("quoteAsset"),
            "status": s.get("status"),
        }
        for s in symbols
        if s.get("symbol")
    ]
    return _EXCHANGE_INFO_CACHE


# Canonical mapping for major assets. CoinGecko's /coins/list contains
# thousands of memecoins squatting on the same symbol codes (a coin
# called "batcat" with symbol "BTC", an "Abstract Bridged USDT" with
# symbol "USDT"), so we override the top assets explicitly and use
# CoinGecko only for the long tail.
_CANONICAL_ASSET_NAMES: dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "USDT": "Tether",
    "USDC": "USD Coin",
    "BUSD": "Binance USD",
    "FDUSD": "First Digital USD",
    "TUSD": "TrueUSD",
    "DAI": "Dai",
    "BNB": "BNB",
    "XRP": "XRP",
    "ADA": "Cardano",
    "SOL": "Solana",
    "DOGE": "Dogecoin",
    "TRX": "TRON",
    "DOT": "Polkadot",
    "MATIC": "Polygon",
    "POL": "Polygon",
    "LTC": "Litecoin",
    "BCH": "Bitcoin Cash",
    "AVAX": "Avalanche",
    "LINK": "Chainlink",
    "SHIB": "Shiba Inu",
    "UNI": "Uniswap",
    "ATOM": "Cosmos",
    "ETC": "Ethereum Classic",
    "XLM": "Stellar",
    "NEAR": "NEAR Protocol",
    "APT": "Aptos",
    "ARB": "Arbitrum",
    "OP": "Optimism",
    "INJ": "Injective",
    "SUI": "Sui",
    "TIA": "Celestia",
    "TON": "Toncoin",
    "PEPE": "Pepe",
    "WIF": "dogwifhat",
    "ETH2": "Ethereum 2.0",
    "EUR": "Euro",
    "GBP": "British Pound",
}


def _load_asset_names() -> dict[str, str]:
    """Map asset symbol (uppercase) -> long name.

    Returns the canonical mapping for top assets merged with CoinGecko's
    /coins/list for the long tail. Cached for the process lifetime.
    Returns the canonical-only map silently if CoinGecko fails.
    """
    if _ASSET_NAME_CACHE:
        return _ASSET_NAME_CACHE
    # Canonical entries always win.
    _ASSET_NAME_CACHE.update(_CANONICAL_ASSET_NAMES)
    try:
        resp = requests.get(_COINGECKO_LIST_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
        for c in resp.json() or []:
            sym = (c.get("symbol") or "").upper()
            name = c.get("name")
            # Skip if canonical already covers it; otherwise take the
            # first CoinGecko hit for the long tail.
            if sym and name and sym not in _ASSET_NAME_CACHE:
                _ASSET_NAME_CACHE[sym] = name
    except (requests.RequestException, ValueError):
        pass
    return _ASSET_NAME_CACHE


def _pair_longname(base: str, quote: str) -> str:
    """E.g. ('BTC','USDT') -> 'Bitcoin / Tether (USDT)'."""
    names = _load_asset_names()
    base_name = names.get(base.upper(), base)
    quote_name = names.get(quote.upper(), quote)
    return f"{base_name} / {quote_name} ({quote})"


def list_pairs(*, quote: str | None = None, status: str = "TRADING") -> list[dict]:
    """Enumerate Binance spot pairs, optionally filtered by quote currency.

    Returns ``[{symbol, base, quote, base_longname, longname, status}, ...]``.
    Long names come from CoinGecko (free, no key); unmapped assets fall
    back to the asset code.
    """
    names = _load_asset_names()
    out: list[dict] = []
    for p in _load_exchange_info():
        if status and p["status"] != status:
            continue
        if quote and p["quoteAsset"] != quote.upper():
            continue
        base = p["baseAsset"]
        q = p["quoteAsset"]
        base_name = names.get(base.upper(), base) if base else None
        out.append({
            "symbol": p["symbol"],
            "base": base,
            "quote": q,
            "base_longname": base_name,
            "longname": _pair_longname(base, q) if base and q else None,
            "status": p["status"],
        })
    return out


def search_pairs(query: str, *, limit: int = 20) -> list[dict]:
    """Substring search over Binance pair symbols + base-asset long names.

    Matches case-insensitively against the raw pair (BTCUSDT) and the
    base long name (Bitcoin), so the user can say "Bitcoin" or "BTC"
    or "BTCUSDT".
    """
    if not query.strip():
        return []
    q = query.upper().strip()
    pairs = list_pairs()
    # Rank: exact symbol > base match > longname contains.
    scored: list[tuple[int, dict]] = []
    for p in pairs:
        sym = (p.get("symbol") or "").upper()
        base = (p.get("base") or "").upper()
        ln = (p.get("base_longname") or "").upper()
        if sym == q:
            scored.append((3, p))
        elif base == q:
            scored.append((2, p))
        elif q in sym or q in ln:
            scored.append((1, p))
    scored.sort(key=lambda t: -t[0])
    return [p for _, p in scored[:limit]]


def describe_pair(pair: str) -> dict | None:
    """Return metadata for one Binance spot pair (case-insensitive)."""
    target = to_binance_symbol(pair).upper()
    for p in list_pairs():
        if p["symbol"] == target:
            return p
    return None


class _BinanceSource(Source):
    capability = CATALOG["binance"]

    def supports(self, ref: _DataRef) -> bool:
        return ref.source == SOURCE and ref.kind == "ohlcv"

    def fetch(self, ref: _DataRef, *, refresh: bool = False) -> pd.DataFrame:
        return fetch_ohlcv(
            ref.name,
            interval=ref.interval,
            start=ref.start,
            end=ref.end,
            refresh=refresh,
        )

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        return search_pairs(query, limit=limit)

    def describe(self, name: str) -> dict | None:
        return describe_pair(name)


register_source(_BinanceSource())
