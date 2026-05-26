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
