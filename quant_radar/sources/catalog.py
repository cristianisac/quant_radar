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
        kinds=["ohlcv", "futures_aggregate", "etf_aum"],
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
        examples=[
            "AAPL", "SPY", "MSFT", "TSLA", "NVDA",
            "BTC-USD", "EURUSD=X", "^GSPC",
            # CME crypto futures (continuous front-month via =F suffix):
            "BTC=F", "MBT=F", "ETH=F", "MET=F", "SOL=F", "MSL=F",
            "XRP=F", "LNK=F", "MLN=F", "ADA=F", "XLM=F", "MXL=F",
            # Specific contracts also work (e.g. "BTCM26.CME" = Jun 2026):
            "BTCM26.CME",
            # Asset roots for kind=futures_aggregate (sum across all months):
            "BTC", "ETH", "SOL", "XRP", "LINK", "ADA", "XLM",
        ],
        schema={
            "ohlcv": ["open", "high", "low", "close", "volume"],
            # CME futures aggregate: enumerates every active contract
            # month per asset root + variant (standard / micro) and sums
            # daily volume + notional. ref.name accepts BTC / ETH / SOL
            # / XRP / LINK / ADA / XLM (case-insensitive). See
            # cme_futures_src.ASSET_REGISTRY for contract sizes and
            # which variants exist on yfinance.
            # standard_contracts is the headline ("total contracts"
            # conventionally refers to the standard count — institutional
            # benchmark). Micro is reported separately because its
            # contract size differs by ~50x, so summing the counts would
            # be meaningless in any unit. USD notional CAN be summed
            # since dollars are dollars regardless of contract size.
            # Order matters — column-agnostic ChartCard picks the first
            # numeric column for the y-axis.
            "futures_aggregate": [
                "standard_contracts", "micro_contracts",
                "total_notional", "standard_notional", "micro_notional",
                "active_months_std", "active_months_micro",
            ],
            # ETF AUM snapshot. ref.name accepts Bloomberg-style
            # ('IBIT US', 'BITC SW', 'BTCC/B CN') or raw Yahoo
            # ('IBIT', 'BITC.SW', 'BTCC-B.TO'). Returns one row per
            # call — point-in-time, no history. yfinance covers ~44%
            # of the user-supplied 536-ticker crypto ETF universe by
            # count, but ~80-90% by USD AUM (US Bitcoin spot ETFs
            # dominate). European ETPs / ETCs typically return name
            # but null AUM — yfinance product-type limitation.
            "etf_aum": [
                "bloomberg", "yahoo", "longname",
                "aum", "nav", "category", "currency", "status",
            ],
        },
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
    "fmp": SourceCapability(
        name="fmp",
        kinds=[
            "ohlcv", "forex", "crypto",
            "income", "balance", "cash",
            "dividends", "splits", "estimates",
            "sec_filings",
        ],
        intervals=["1m", "5m", "15m", "1h", "1d", "1w", "1mo", "quarter", "annual"],
        history="Equities from listing date (1985+ for major US tickers). Fundamentals from 1985+. Daily EOD reliable. Intraday + forex on free tier with rate limits.",
        coverage="US equities + global ADRs + ETFs (~40k). Forex majors. Income statement / balance sheet / cash flow for ~30k tickers, quarterly + annual. Major US indices (^GSPC, ^DJI, ^IXIC, ^VIX) via the same OHLCV endpoint. Crypto USD majors. Futures NOT supported on free tier (use yfinance =F suffix for those). Adapter wraps OpenBB Platform's `fmp` provider.",
        auth="FMP_API_KEY env var (free signup at financialmodelingprep.com)",
        rate_limit="250 req/day on free tier — modest; cache-first is essential",
        examples=[
            "AAPL", "MSFT", "SPY", "TSLA", "NVDA",
            "EURUSD", "GBPUSD",
            "BTCUSD", "ETHUSD",
            # Major US indices — verified live (2026-05-27): all four
            # serve via obb.equity.price.historical on free tier.
            "^GSPC", "^DJI", "^IXIC", "^VIX",
        ],
        schema={
            "ohlcv": ["open", "high", "low", "close", "volume"],
            "forex": ["open", "high", "low", "close"],
            "crypto": ["open", "high", "low", "close", "volume"],
            # Fundamentals schemas use FMP's column names verbatim (e.g.
            # `bottom_line_net_income` not `net_income`). When we add a
            # second provider for fundamentals (Polygon), we'll normalize
            # at that point; for now honesty about the upstream shape
            # beats premature aliasing.
            "income": ["fiscal_period", "fiscal_year", "revenue", "gross_profit", "bottom_line_net_income"],
            "balance": ["fiscal_period", "fiscal_year", "total_assets", "total_liabilities", "total_debt"],
            "cash": ["fiscal_period", "fiscal_year", "operating_cash_flow", "free_cash_flow"],
            # Dividends + splits are event tables (one row per event,
            # indexed by event date). Schema names follow FMP/OpenBB's
            # upstream naming.
            "dividends": ["amount", "dividend_yield", "frequency", "payment_date", "record_date"],
            "splits": ["numerator", "denominator", "splitType"],
            # Forward analyst estimates — quarterly + annual ranges.
            "estimates": [
                "estimated_revenue_avg", "estimated_eps_avg",
                "estimated_ebitda_avg", "number_analysts_eps",
            ],
            # SEC filings (Form 4, 10-K, 10-Q, 8-K, etc.) via FMP. Less
            # rich than the direct SEC provider but easier on rate limit.
            "sec_filings": [
                "report_type", "report_url", "filing_url",
                "symbol", "cik", "accepted_date",
            ],
        },
        notes="OHLCV via obb.equity.price.historical; forex via obb.currency.price.historical. Fundamentals via obb.equity.fundamental.income/balance/cash with period='quarter'|'annual'. Adapter sets the DataFrame index to period_ending so each row is anchored to its fiscal period end-date.",
    ),
    "tiingo": SourceCapability(
        name="tiingo",
        kinds=["ohlcv", "forex", "crypto"],
        intervals=["1d", "1h", "5m", "1m"],
        history="Equities from listing date. Daily EOD comprehensive. IEX intraday + forex free on the basic tier.",
        coverage="US equities + ETFs + select global ADRs (~30k). Forex majors. Adapter wraps OpenBB Platform's `tiingo` provider.",
        auth="TIINGO_API_KEY env var (free signup at tiingo.com — header is Token auth)",
        rate_limit="1000 req/hr on free tier — generous",
        examples=["AAPL", "MSFT", "SPY", "QQQ", "EURUSD", "USDJPY", "BTCUSD", "ETHUSD"],
        schema={
            "ohlcv": ["open", "high", "low", "close", "volume"],
            "forex": ["open", "high", "low", "close"],
            "crypto": ["open", "high", "low", "close", "volume"],
        },
        notes="OpenBB-backed. Provides adjusted prices via adj_* columns (stripped by adapter — we keep canonical OHLCV). Crypto symbols use `<base><quote>` (BTCUSD, ETHUSD).",
    ),
    "polygon": SourceCapability(
        name="polygon",
        kinds=["ohlcv", "forex", "ticker_news", "options_chain"],
        intervals=["1m", "5m", "15m", "1h", "1d", "1w", "1mo", "event (ticker_news + options_chain)"],
        history="Free tier: ~2 years EOD daily for stocks. Forex + options reference data free. Futures require paid plans. Per-ticker news is rolling.",
        coverage="US equities + ETFs + indices + crypto + FX (~70k tickers). Per-ticker news with LLM-derived sentiment + reasoning + keywords. Options chain reference data (strike/expiration/CP) — historical per-contract aggregates also free. Hand-written REST adapter (Polygon not in OpenBB Platform's bundled providers).",
        auth="POLYGON_API_KEY env var (free signup at polygon.io)",
        rate_limit="5 calls/min on free tier — tight; cache aggressively",
        examples=["AAPL", "MSFT", "SPY", "EURUSD", "GBPUSD"],
        schema={
            "ohlcv": ["open", "high", "low", "close", "volume"],
            "forex": ["open", "high", "low", "close"],
            "ticker_news": [
                "title", "author", "publisher", "article_url",
                "sentiment", "sentiment_reasoning", "keywords",
            ],
            # Options chain — one row per available contract.
            # contract_ticker is Polygon's OCC-format symbol (e.g.
            # O:AAPL260620C00200000) that can be fed straight into
            # /v2/aggs to get historical pricing for THAT specific
            # contract.
            "options_chain": [
                "contract_type", "strike_price", "contract_ticker",
                "primary_exchange", "shares_per_contract", "exercise_style",
            ],
        },
        notes="Equity aggregates use bare ticker; forex aggregates use `C:<pair>` prefix (e.g. C:EURUSD). Adapter handles the prefix internally.",
    ),
    "alphavantage": SourceCapability(
        name="alphavantage",
        kinds=["sentiment"],
        intervals=["event"],
        history="Rolling ~30 days of scored news articles.",
        coverage="Global stocks + ETFs + crypto + FX. ML-based per-ticker sentiment scoring (overall + per-symbol relevance + label).",
        auth="ALPHAVANTAGE_API_KEY env var (free signup at alphavantage.co/support/#api-key)",
        rate_limit="25 req/day, 5 req/min — TIGHT. Cache aggressively.",
        examples=["AAPL", "MSFT", "TSLA", "NVDA", "BTC-USD", "EURUSD"],
        schema={
            "sentiment": [
                "sentiment_score", "relevance_score", "overall_score",
                "sentiment_label", "title", "url", "article_source", "topics",
            ],
        },
        notes=(
            "Best-quality per-ticker news sentiment scoring. Primary source "
            "in kind_coverage for kind='sentiment'. Falls back to marketaux "
            "when daily quota exhausted. See quant_radar/sources/"
            "kind_coverage.py for the full multi-source routing logic."
        ),
    ),
    "marketaux": SourceCapability(
        name="marketaux",
        kinds=["sentiment"],
        intervals=["event"],
        history="Rolling articles, 30+ days back.",
        coverage="Global incl. small caps + international. Wider symbol universe than Alpha Vantage but less rich per-article scoring.",
        auth="MARKETAUX_API_KEY env var (free signup at marketaux.com/account/dashboard)",
        rate_limit="100 req/day, 1 req/sec — more generous than AV.",
        examples=["AAPL", "MSFT", "TSLA"],
        schema={
            "sentiment": [
                "sentiment_score", "relevance_score", "overall_score",
                "sentiment_label", "title", "url", "article_source", "topics",
            ],
        },
        notes=(
            "Fallback for kind='sentiment' when Alpha Vantage's 25/day quota "
            "is exhausted, OR for tickers AV doesn't cover. Returns "
            "per-entity sentiment_score; we derive a label heuristically "
            "(>=0.35 Bullish, ..., <-0.35 Bearish) for UI parity with AV."
        ),
    ),
    "apewisdom": SourceCapability(
        name="apewisdom",
        kinds=["social_sentiment"],
        intervals=["snapshot"],
        history=(
            "Rolling 24h window only. Apewisdom publishes the current "
            "leaderboard plus a 24h-prior comparison per ticker — there "
            "is no historical archive. Each refresh overwrites with the "
            "latest snapshot."
        ),
        coverage=(
            "Tickers being discussed on tracked subreddits (WSB, "
            "wallstreetbetsELITE, stocks, investing, cryptocurrency, "
            "satoshistreetbets, ...). ~870 stocks/ETFs in `all-stocks`, "
            "~160 crypto in `all-crypto`. Commodities/bonds surface only "
            "via listed proxies (GLD, TLT, USO)."
        ),
        auth="none",
        rate_limit=(
            "no documented limit; unauthenticated public endpoint. Cache "
            "intraday (5 min) — leaderboard rotates throughout the day."
        ),
        examples=["MU", "SPY", "ASTS", "TSLA", "NVDA", "BTC", "ETH"],
        schema={
            "social_sentiment": [
                "ticker", "name",
                "mentions", "mentions_24h_ago", "mentions_change_pct",
                "upvotes", "rank", "rank_24h_ago", "filter",
            ],
        },
        notes=(
            "Mention-velocity signal (not classical -1..1 sentiment). "
            "Most useful as a *viral-attention* indicator: a 5×–10× "
            "spike in mentions_change_pct typically precedes meme-driven "
            "price moves. Pair with AV/Marketaux for actual sentiment "
            "polarity. Crypto tickers stored with .X suffix (BTC.X); "
            "adapter accepts either shape."
        ),
    ),
    "gdelt": SourceCapability(
        name="gdelt",
        kinds=["news", "news_tone"],
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
        schema={
            "news": ["title", "url", "source", "published_at"],
            # `tone` is GDELT's centered article-tone metric, typically
            # in [-10, +10]. Negative = pessimistic / conflict-framing,
            # positive = optimistic. Aggregated per timestamp by GDELT's
            # `mode=timelinetone` (hourly on short windows, daily beyond).
            "news_tone": ["tone"],
        },
    ),
    "tradingeconomics": SourceCapability(
        name="tradingeconomics",
        kinds=["economic_calendar"],
        intervals=["event (~4 weeks rolling)"],
        history=(
            "Country calendar pages serve the current week + ~3 upcoming "
            "weeks. No history or far-future support — ToS reserves "
            "that for paid plans."
        ),
        coverage=(
            "Per-country pages: united-states, euro-area, united-kingdom, "
            "germany, france, italy, spain, japan, china, canada, "
            "australia, plus ~20 others. Covers all major releases for "
            "the country incl. proprietary indicators (PMIs, Consumer "
            "Confidence, ECB/Fed speakers, central-bank rate decisions)."
        ),
        auth="none (scraped from public HTML)",
        rate_limit=(
            "No documented limit. Be polite — once per few minutes; the "
            "underlying data only changes when events tick off."
        ),
        examples=["united-states", "euro-area", "united-kingdom", "germany", "japan", "china"],
        schema={
            "economic_calendar": [
                "country", "event", "period",
                "actual", "previous", "consensus", "forecast",
            ],
        },
        notes=(
            "**Default window**: when no start/end is passed on the "
            "DataRef, the adapter returns the current calendar week "
            "(Monday→Sunday UTC). Pass explicit start/end to widen — "
            "still bounded by the ~4 weeks TE renders. "
            "**ToS gray area.** Trading Economics' Terms of Use prohibit "
            "automated extraction. Their public `guest:guest` HTTP API "
            "token was discontinued in 2026 to push everyone to paid "
            "plans. Country-page scraping still works technically but "
            "is a side-door around their pricing — acceptable for "
            "personal research, not for redistribution. The OpenBB "
            "`tradingeconomics` provider for `obb.economy.calendar` "
            "needs a paid key and is the clean licensed path; this "
            "adapter scrapes country pages with no auth."
        ),
    ),
    "finnhub": SourceCapability(
        name="finnhub",
        kinds=[
            "news", "insider", "earnings_calendar", "ipo_calendar",
            "recommendation", "insider_sentiment",
        ],
        intervals=["news: real-time / per-window; insider: rolling 12mo; calendars: forward-window scoped; recommendation/insider_sentiment: monthly"],
        history=(
            "Free tier: company news ~1 year back per call; general news "
            "rolling real-time; insider-transactions rolling 12 months."
        ),
        coverage=(
            "curated finance news plus company-specific (US tickers). "
            "Insider transactions cover US-listed equities, one row per "
            "Form-4 filing."
        ),
        auth="FINNHUB_API_KEY env var (free signup at finnhub.io)",
        rate_limit="60 calls/min on the free tier",
        # `30d`/`7d`/`60d`/`90d` are window literals interpreted by the
        # calendar adapters as forward-looking windows from now. AAPL etc.
        # are used by news + insider.
        examples=["AAPL", "MSFT", "TSLA", "NVDA", "30d"],
        schema={
            "news": ["title", "url", "source", "published_at", "summary"],
            "insider": [
                "transaction_price", "share", "change", "transaction_code",
                "insider_name", "filing_date", "is_derivative", "source",
            ],
            "earnings_calendar": [
                "symbol", "eps_estimate", "eps_actual",
                "revenue_estimate", "revenue_actual",
                "hour", "quarter", "year",
            ],
            "ipo_calendar": [
                "symbol", "company_name", "exchange",
                "number_of_shares", "price", "status",
                "total_shares_value",
            ],
            # Analyst rating snapshot, one row per month. Counts in each
            # bucket; sum of all five = total analysts covering the name.
            "recommendation": [
                "strong_buy", "buy", "hold", "sell", "strong_sell", "symbol",
            ],
            # Monthly insider-sentiment via MSPR (Monthly Share Purchase
            # Ratio). Positive = net buying, negative = net selling. Raw
            # `change` is net shares-traded sign.
            "insider_sentiment": ["change", "mspr", "symbol"],
        },
        notes=(
            "Calendars are window-scoped — ref.name accepts '7d' / '30d' "
            "/ '60d' / '90d' (default 30d). Economic calendar is paid on "
            "every free provider we have keys for (FMP 402, "
            "tradingeconomics requires paid key) — deferred. ETF "
            "holdings + analyst recommendation time-series also free on "
            "Finnhub, but ETF holdings is paywalled (verified 2026-05-26). "
            "Recommendation trends + insider-sentiment MSPR ship in "
            "phase 2b.4. News-sentiment + price-target endpoints are "
            "403 on the free tier (verified 2026-05-27)."
        ),
    ),
}


def list_sources() -> list[dict]:
    """Return every source's capability as a plain dict (JSON-serializable)."""
    return [cap.to_dict() for cap in CATALOG.values()]


def describe_source(name: str) -> dict | None:
    """Look up one source's capability by name. Returns None if unknown."""
    cap = CATALOG.get(name)
    return cap.to_dict() if cap else None
