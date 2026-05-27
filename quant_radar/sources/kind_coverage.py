"""Per-data-type multi-source coverage matrix.

The catalog (``catalog.py``) describes each source individually. When
the agent needs a specific data type and multiple sources serve it,
we also need to know **how they relate** — which is best, which is a
fallback, which is complementary (different signal type), how rate
limits interact, what coverage gaps exist.

This file is that cross-cutting knowledge. For every ``kind`` with
multiple sources, an entry here declares:

- ``providers``: each source that serves this kind, with its
  per-source notes (rate limit, history depth, coverage breadth,
  signal quality, granularity).
- ``tier`` per provider: ``primary`` | ``fallback`` | ``complementary``.
- ``default_chain``: the routing order an agent should walk when
  asked for this kind without an explicit source preference.
- ``routing_logic``: prose explaining when to switch / combine.

The agent reads this at session start (via ``tools.kind_coverage(kind)``)
so it can make informed source choices rather than guessing. SKILL.md
points the agent here when the user asks for a kind we serve from
multiple sources.

When you add a new source for an existing kind: add it here AND to
the source's catalog entry. Both must agree.
"""

from __future__ import annotations

from typing import Any

KIND_COVERAGE: dict[str, dict[str, Any]] = {
    "crypto": {
        "description": (
            "Crypto OHLCV — open/high/low/close/volume per bar. "
            "Binance is the primary path (full exchange-native data, "
            "no auth, ~2k spot pairs); FMP and Tiingo are fallbacks for "
            "when binance is rate-limited or doesn't list the pair."
        ),
        "providers": {
            "binance": {
                "tier": "primary",
                "rate_limit": "1200 request-weight/min/IP — effectively unlimited",
                "history": "From the pair's first trade on Binance (2017-08-17 for BTC/ETH)",
                "coverage": (
                    "1500+ spot pairs in every major quote (USDT, USDC, "
                    "BUSD, FDUSD, TUSD, BTC, ETH, BNB, EUR, GBP). Bare "
                    "symbols auto-mapped to *USDT (BTC → BTCUSDT)."
                ),
                "signal_quality": (
                    "Exchange-native — same data the matching engine "
                    "uses. Tick precision; volume is real exchange volume."
                ),
                "granularity": "1m/5m/15m/1h/1d/1w/1mo with full pagination",
                "notes": (
                    "Default for any crypto OHLCV request. Try binance "
                    "first; fall back to FMP/Tiingo only on rate-limit "
                    "or missing pair."
                ),
            },
            "fmp": {
                "tier": "fallback",
                "rate_limit": "250 req/day on free tier — modest",
                "history": "Multi-year for major pairs",
                "coverage": (
                    "BTCUSD/ETHUSD and other USD-quoted majors. Symbol "
                    "format is `<base><quote>` (BTCUSD, not BTC-USD)."
                ),
                "signal_quality": (
                    "Aggregated cross-exchange. Volume is a composite, "
                    "not single-venue."
                ),
                "granularity": "1d primarily; intraday with limits",
                "notes": "Use when binance is rate-limited or for a USD cross-check.",
            },
            "tiingo": {
                "tier": "fallback",
                "rate_limit": "1000 req/hr on free tier — generous",
                "history": "Multi-year",
                "coverage": (
                    "USD-quoted majors (BTCUSD, ETHUSD, ...). Same "
                    "naming convention as FMP."
                ),
                "signal_quality": (
                    "Cross-exchange composite. Provides volume_notional "
                    "in USD on top of base-volume."
                ),
                "granularity": "1d / 1h / intraday",
                "notes": "Generous quota makes this the better fallback for batch backfills.",
            },
        },
        "default_chain": ["binance", "fmp", "tiingo"],
        "routing_logic": (
            "Binance first for any crypto request. When binance is "
            "rate-limited (HTTP 429 / weight exhausted) or the pair "
            "isn't listed, fall back to FMP, then Tiingo. The three "
            "agree closely on price but disagree on volume (binance = "
            "single-venue; FMP/Tiingo = composite). For volume-driven "
            "analysis, prefer binance."
        ),
    },
    "social_sentiment": {
        "description": (
            "Reddit-driven mention-velocity per ticker. NOT classical "
            "polarity sentiment (-1..1) — this is a count of how many "
            "times a ticker is being talked about right now vs. 24h ago. "
            "Best as a viral-attention signal that often precedes "
            "meme-driven moves. Pair with `kind='sentiment'` (AV/"
            "Marketaux) for actual polarity."
        ),
        "providers": {
            "apewisdom": {
                "tier": "primary",
                "rate_limit": "no documented limit; cache intraday (5 min)",
                "history": "Rolling 24h window only — no archive",
                "coverage": (
                    "Stocks/ETFs/listed companies (~870 via all-stocks) + "
                    "crypto (~160 via all-crypto). Commodities/bonds only "
                    "via listed proxies (GLD, TLT, USO)."
                ),
                "signal_quality": (
                    "mentions + mentions_24h_ago + rank + rank_24h_ago "
                    "+ upvotes. Spike detection: mentions_change_pct > "
                    "5×–10× is the viral-attention threshold."
                ),
                "granularity": "per-ticker snapshot",
                "notes": (
                    "Crypto tickers stored with .X suffix (BTC.X, ETH.X); "
                    "adapter accepts either shape. No auth, public endpoint."
                ),
            },
        },
        "default_chain": ["apewisdom"],
        "complementary_signals": ["alphavantage", "marketaux"],
        "routing_logic": (
            "Apewisdom is the only free social-sentiment source we've "
            "kept after Stocktwits went Cloudflare-protected and Reddit "
            "PRAW app registration proved unreliable. For 'is anyone "
            "talking about X right now?' → apewisdom. For polarity of "
            "what's being said in news → kind='sentiment' (AV/Marketaux). "
            "The two are orthogonal — a ticker can be high-mention with "
            "neutral sentiment (mixed coverage) or low-mention with "
            "strong positive sentiment (analyst upgrade, no chatter yet)."
        ),
    },
    "sentiment": {
        "description": (
            "Per-ticker news sentiment scores. Returned as a time-series "
            "DataFrame: each row is one article with timestamp = published_at, "
            "columns include sentiment_score (-1..1), relevance_score (0..1), "
            "title, url, article_source."
        ),
        "providers": {
            "alphavantage": {
                "tier": "primary",
                "rate_limit": "25 req/day, 5 req/min — TIGHT, cache aggressively",
                "history": "Rolling ~30 days of news",
                "coverage": "Global stocks + ETFs + crypto + FX",
                "signal_quality": (
                    "ML-based scoring; returns overall_sentiment_score per "
                    "article AND ticker_sentiment array with per-symbol "
                    "relevance + score + label (Bullish/Bearish/Neutral)"
                ),
                "granularity": "per-article + per-ticker",
                "notes": (
                    "Highest scoring quality. Limit=50 articles per call. "
                    "If quota exhausted, fall back to marketaux."
                ),
            },
            "marketaux": {
                "tier": "fallback",
                "rate_limit": "100 req/day, 1 req/sec — more generous than AV",
                "history": "Rolling articles, 30+ days back",
                "coverage": (
                    "Global incl. small caps + international tickers; "
                    "wider universe than AV"
                ),
                "signal_quality": (
                    "Per-entity sentiment_score (-1..1) + match_score that "
                    "indicates how strongly the entity is referenced"
                ),
                "granularity": "per-article + per-entity",
                "notes": (
                    "Use when AV's 25 req/day quota is exhausted, or for "
                    "tickers AV doesn't cover (smaller caps, international)."
                ),
            },
            "finnhub": {
                "tier": "complementary",
                "endpoint": "stock/insider-sentiment + stock/recommendation",
                "rate_limit": "60 req/min — generous",
                "history": "Last 12 months MSPR (insider) + analyst rec history",
                "coverage": "US stocks only",
                "signal_quality": (
                    "Different signal types: insider-sentiment is MSPR "
                    "(Monthly Stock Purchase Ratio) — aggregated insider "
                    "trading sentiment. recommendation is analyst counts "
                    "(buy/hold/sell/strongBuy/strongSell)"
                ),
                "granularity": "monthly (insider) / per-period (recommendation)",
                "notes": (
                    "NOT a news-sentiment source. Use as ORTHOGONAL signal "
                    "to news sentiment — captures internal-actor sentiment + "
                    "analyst-consensus sentiment, which often diverges from "
                    "news mood. Best used alongside AV/Marketaux, not "
                    "instead of."
                ),
            },
            "gdelt": {
                "tier": "article-level",
                "endpoint": "DOC API tone field",
                "rate_limit": "Public, no auth, but ~83% reliability + flaky latency",
                "history": "2015+",
                "coverage": "Global news (all topics, not just finance)",
                "signal_quality": (
                    "Single tone score per article (-100..100). NOT per-entity. "
                    "If an article mentions multiple tickers, you get one "
                    "aggregated score for the whole piece."
                ),
                "granularity": "per-article (NOT per-ticker)",
                "notes": (
                    "Use for general market mood / topic-level sentiment "
                    "where article-level is fine. NOT a substitute for "
                    "AV/Marketaux per-ticker sentiment."
                ),
            },
        },
        "default_chain": ["alphavantage", "marketaux"],
        "complementary_signals": ["finnhub", "gdelt"],
        "routing_logic": (
            "For per-ticker sentiment: try alphavantage first (best scoring "
            "quality, per-ticker granularity). If AV daily quota exhausted "
            "(error: 'Thank you for using Alpha Vantage! Our standard API "
            "rate limit is 25 requests per day'), fall back to marketaux "
            "(100 req/day). For richer signal: also pull finnhub "
            "insider-sentiment + recommendation as an ORTHOGONAL signal "
            "(insider activity vs news mood often diverges). GDELT tone is "
            "article-level only — use for general mood, NOT per-ticker."
        ),
    },
}


def get_coverage(kind: str) -> dict[str, Any] | None:
    """Return the multi-source coverage record for ``kind``, or None.

    Returns ``None`` for kinds served by a single source — the agent can
    just use that source directly. Returns a structured dict when
    multiple sources serve the kind, so the agent can route intelligently.
    """
    return KIND_COVERAGE.get(kind)


def list_covered_kinds() -> list[str]:
    """Kinds with documented multi-source relationships."""
    return list(KIND_COVERAGE.keys())
