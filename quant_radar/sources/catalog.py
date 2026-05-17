"""Static metadata describing what each data source supports.

Two layers of capability discovery:
1. **Static** (this catalog): intervals, history concept, coverage, auth,
   rate limits. Read by the chat agent at the start of a session so it
   knows which source to reach for.
2. **Dynamic** (``tools.probe_history``): hit the API itself to ask
   "what's the earliest bar you have for ``X``?". Use when the user
   asks about a specific symbol's history.

Keep this file in sync with the source modules. The
``tests.test_catalog`` suite asserts every source listed under
``quant_radar.sources.__all__`` has a catalog entry (and vice versa).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class SourceCapability:
    name: str
    kinds: list[str]
    intervals: list[str]
    history: str
    coverage: str
    auth: str
    rate_limit: str
    status: str = "active"  # "active" | "limited" | "deferred" | "paid-only"
    # "active"    — full coverage, sufficient history for TA (≥250 daily bars)
    # "limited"   — works, but insufficient history / coverage for trend analysis;
    #               agent should use for current-value queries only, not for SMAs
    # "deferred"  — code present but currently unusable (e.g., went paywalled)
    # "paid-only" — requires a paid plan; key must be supplied externally
    notes: str = ""
    examples: list[str] = field(default_factory=list)
    # Output schema per ``kind``. The DataFrame returned for
    # ``(source, kind)`` is guaranteed to expose these columns. News and
    # event sources use ``record`` to signal a non-tabular payload.
    # Other code (tool compatibility, agent guidance) reads this rather
    # than re-deriving from convention.
    schema: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


CATALOG: dict[str, SourceCapability] = {
    "yfinance": SourceCapability(
        name="yfinance",
        kinds=["ohlcv"],
        intervals=["1m", "5m", "15m", "1h", "1d", "1w", "1mo"],
        history=(
            "Daily/weekly/monthly: from the asset's listing date. Verified "
            "live (with start=2000-01-01): AAPL/MSFT/SPY/NVDA from "
            "2000-01-03 (and earlier — AAPL actually goes back to 1980). "
            "TSLA from 2010-06-29 (IPO). BTC-USD from 2014-09-17. "
            "Intraday limits: 1m last 7 days, 5m/15m last 60 days, "
            "1h last 730 days. Adapter defaults to a 5y window for daily "
            "when no `start` is given."
        ),
        coverage=(
            "equities, ETFs, indices (^GSPC, ^IXIC), FX (EURUSD=X), "
            "major crypto-USD pairs (BTC-USD, ETH-USD, SOL-USD)"
        ),
        auth="none",
        rate_limit="aggressive — cache-first; only use refresh=True deliberately",
        examples=["AAPL", "SPY", "MSFT", "TSLA", "NVDA", "BTC-USD", "EURUSD=X", "^GSPC"],
        schema={"ohlcv": ["open", "high", "low", "close", "volume"]},
    ),
    "binance": SourceCapability(
        name="binance",
        kinds=["ohlcv"],
        intervals=["1m", "5m", "15m", "1h", "1d", "1w", "1mo"],
        history=(
            "From the pair's first trade on Binance. Verified live: "
            "BTCUSDT/ETHUSDT from 2017-08-17 (exchange launch), BNBUSDT "
            "from 2017-11-06, XRPUSDT from 2018-05-04, SOLUSDT from "
            "2020-08-11. Newer pairs from their listing date. Adapter "
            "paginates klines so any window can be fetched."
        ),
        coverage=(
            "1500+ spot pairs (USDT, USDC, BUSD, FDUSD, TUSD, BTC, ETH, "
            "BNB, EUR, GBP quotes). Bare base symbols ('BTC', 'ETH', "
            "'SOL') are auto-mapped to '*USDT'."
        ),
        auth="none",
        rate_limit="1200 request-weight/min per IP — practically unlimited for cached use",
        examples=["BTC", "ETH", "SOL", "BNB", "XRP", "BTCUSDT", "ETHBTC", "SOLUSDC"],
        schema={"ohlcv": ["open", "high", "low", "close", "volume"]},
    ),
    "fred": SourceCapability(
        name="fred",
        kinds=["macro"],
        intervals=["native frequency per series (daily / weekly / monthly / quarterly / annual)"],
        history=(
            "Very long. DGS10 from 1962-01-02 (daily). CPIAUCSL from "
            "1947-01-01 (monthly). UNRATE from 1948-01-01 (monthly). "
            "GDP from 1947-01-01 (quarterly). FEDFUNDS from 1954-07-01 "
            "(monthly). DEXUSEU from 1999-01-04 (daily). Each series "
            "has its own native frequency — many are not daily, do not "
            "assume daily granularity."
        ),
        coverage=(
            "800k+ US & international macroeconomic series via the "
            "public fredgraph.csv endpoint"
        ),
        auth="none",
        rate_limit="lenient",
        examples=["DGS10", "CPIAUCSL", "UNRATE", "GDP", "FEDFUNDS", "DEXUSEU", "M2SL"],
        schema={"macro": ["value"]},
    ),
    "coinpaprika": SourceCapability(
        name="coinpaprika",
        kinds=["ohlcv"],
        intervals=["1d"],
        history="—",
        coverage="—",
        auth="paid plan required",
        rate_limit="—",
        status="deferred",
        notes=(
            "CoinPaprika moved historical OHLCV behind a paid plan in 2025 "
            "(returns 402 Payment Required on the free tier). Use "
            "binance_src for crypto OHLCV. Code kept for callers with a "
            "paid plan."
        ),
        schema={"ohlcv": ["open", "high", "low", "close", "volume"]},
    ),
    "gdelt": SourceCapability(
        name="gdelt",
        kinds=["news"],
        intervals=["events; query windows from 1 hour up to several years"],
        history=(
            "GDELT 2.0 covers events from early 2015 onward. The DOC API "
            "serves rolling content — default 24h timespan if no explicit "
            "start/end."
        ),
        coverage=(
            "global news (many languages), Lucene-style query syntax. "
            "Live-tested: single terms, AND, and quoted phrases work; "
            "OR queries returned 0 items in every test combination — "
            "prefer AND or single terms until investigated."
        ),
        auth="none",
        rate_limit=(
            "tight; ~83% success rate on free public access; latency "
            "7–87s; adapter retries 429/timeouts with 1s/3s back-off"
        ),
        notes=(
            "Treat as opportunistic background news, not a critical path. "
            "For reliable news use finnhub (requires free key)."
        ),
        examples=['Bitcoin', '"AI stocks"', 'Fed AND rates', 'Nvidia earnings'],
        schema={"news": ["title", "url", "source", "published_at"]},
    ),
    "finnhub": SourceCapability(
        name="finnhub",
        kinds=["news"],
        intervals=["general news (real-time); company news (explicit date range)"],
        history=(
            "Free tier: company news ~1 year back per call; general news "
            "is rolling real-time."
        ),
        coverage="curated finance news plus company-specific (US tickers)",
        auth="FINNHUB_API_KEY env var (free signup at finnhub.io)",
        rate_limit="60 calls/min on the free tier",
        examples=["AAPL", "MSFT", "TSLA"],
        schema={"news": ["title", "url", "source", "published_at", "summary"]},
    ),
}


def list_sources() -> list[dict]:
    """Return every source's capability as a plain dict (JSON-serializable)."""
    return [cap.to_dict() for cap in CATALOG.values()]


def describe_source(name: str) -> dict | None:
    """Look up one source's capability by name. Returns None if unknown."""
    cap = CATALOG.get(name)
    return cap.to_dict() if cap else None
