"""Cross-kind relationships — which data types inform each other.

Three different views of the data landscape coexist:

1. **`catalog.py`** — *per-source* capability: "what does Polygon serve?"
2. **`kind_coverage.py`** — *cross-source for one kind*: "Alpha Vantage AND Marketaux both serve sentiment, how do they relate?"
3. **`kind_relationships.py`** *(this file)* — *cross-kind*: "Apewisdom's `social_sentiment` and AV's `sentiment` are orthogonal axes for the same ticker; pull both for a richer read."

The agent reads this at session start so it knows which combinations
strengthen a read. When the user asks for sentiment on a ticker, the
agent should also reach for social_sentiment — not because either
contains the other, but because together they distinguish meme-spikes
from news-driven moves.

Each entry declares:

- ``description`` — what the relationship gives you
- ``kinds`` — the kinds involved
- ``relationship`` — one of:
  - ``orthogonal``: different axes, neither replaces the other (social_sentiment ↔ sentiment)
  - ``siblings``: distinct frames that compose a fuller picture (income + balance + cash = full fundamentals)
  - ``primary_plus_context``: a primary signal that gains meaning when paired with context (ohlcv + news for a price move)
  - ``alternative_views``: same underlying phenomenon, different lens (algorithmic patterns vs vision patterns)
- ``combo_tool`` — the agent-facing tool that bundles the call (if any)
- ``rationale`` — when/why to actually combine
"""

from __future__ import annotations

from typing import Any

KIND_RELATIONSHIPS: dict[str, dict[str, Any]] = {
    "attention_and_polarity": {
        "description": (
            "Reddit mention-velocity AND news polarity for the same "
            "ticker. The two are orthogonal axes — a ticker can be loud "
            "with neutral news (meme) or quiet with positive news "
            "(undiscovered upgrade). Combining catches both."
        ),
        "kinds": ["social_sentiment", "sentiment"],
        "relationship": "orthogonal",
        "combo_tool": "fetch_attention_and_polarity",
        "rationale": (
            "Always combine when the user asks about sentiment for a "
            "specific ticker. Either axis alone can mislead: pure "
            "social-sentiment misses the news direction; pure news "
            "polarity misses retail attention spikes."
        ),
    },
    "fundamentals_triplet": {
        "description": (
            "Income statement + balance sheet + cash flow for a ticker. "
            "Three views of the same firm's financials; none is complete "
            "alone. Income shows profitability, balance shows leverage / "
            "asset base, cash flow shows actual cash generation vs "
            "accounting profit."
        ),
        "kinds": ["income", "balance", "cash"],
        "relationship": "siblings",
        "combo_tool": None,
        "rationale": (
            "When the user asks for 'fundamentals' or 'how is company X "
            "doing financially', create three cards (one per kind) "
            "anchored on the same ticker + period. Comparing net income "
            "(income) against operating cash flow (cash) catches "
            "earnings quality issues that either statement alone hides."
        ),
    },
    "price_in_context": {
        "description": (
            "OHLCV anchored to either news polarity, social attention, "
            "or pattern annotations to give a price move its 'why'. "
            "Price tells you what happened; news/social/patterns tell "
            "you why."
        ),
        "kinds": ["ohlcv", "sentiment", "social_sentiment", "news"],
        "relationship": "primary_plus_context",
        "combo_tool": None,
        "rationale": (
            "When the user asks 'why did X move' or 'what's behind this "
            "spike', pair the price chart with whichever context kind "
            "the data supports. For US equities/ETFs: sentiment + news. "
            "For meme tickers (MU, GME, TSLA): also social_sentiment. "
            "For crypto: social_sentiment + news (sentiment via AV "
            "covers crypto too)."
        ),
    },
    "macro_with_asset": {
        "description": (
            "A FRED macro series anchored alongside an asset's OHLCV "
            "to ask 'how does this asset respond to this macro driver?'. "
            "Rate-sensitive equities vs DGS10, gold vs M2SL, BTC vs DXY."
        ),
        "kinds": ["macro", "ohlcv"],
        "relationship": "primary_plus_context",
        "combo_tool": None,
        "rationale": (
            "When the user asks about a macro-thesis trade (e.g., 'how "
            "does gold do when real rates rise?'), pair the macro series "
            "with the asset OHLCV on the same x-axis. Use FRED's native "
            "frequency (often monthly or weekly) — don't try to "
            "interpolate to daily."
        ),
    },
    "pattern_views": {
        "description": (
            "Same chart, two pattern-detection approaches: algorithmic "
            "(`detect_channels` / `detect_breakouts`) and vision "
            "(`detect_patterns_vision`). They have different blind "
            "spots — algo catches straight channels well, vision "
            "catches H&S / wedges / curved patterns better."
        ),
        "kinds": ["ohlcv"],
        "relationship": "alternative_views",
        "combo_tool": None,
        "rationale": (
            "When the user asks for pattern recognition on a chart, "
            "default to vision (per SKILL.md). Fall back to algorithmic "
            "if vision returns no high-confidence patterns. Don't run "
            "both unless the user wants a cross-check — they'll often "
            "annotate the same patterns and clutter the card."
        ),
    },
    "forex_cross_source": {
        "description": (
            "FX OHLC is served by yfinance, FMP, Tiingo, Polygon. They "
            "diverge in minor details (tick rounding, weekend handling). "
            "When precision matters, cross-check two sources on the "
            "same pair to validate the move."
        ),
        "kinds": ["forex"],
        "relationship": "alternative_views",
        "combo_tool": None,
        "rationale": (
            "Normally just pick the primary (Tiingo). Use a second "
            "source only when validating a specific event (a flash "
            "move, a gap) where any source-specific artifact could "
            "mislead."
        ),
    },
}


def get_relationship(name: str) -> dict[str, Any] | None:
    """Return one relationship record by name, or None if unknown."""
    return KIND_RELATIONSHIPS.get(name)


def list_relationships() -> list[dict[str, Any]]:
    """Return every relationship as a flat list (for the agent to iterate)."""
    return [{"name": k, **v} for k, v in KIND_RELATIONSHIPS.items()]


def relationships_for_kind(kind: str) -> list[dict[str, Any]]:
    """Every relationship that involves ``kind``.

    Useful when the agent has already chosen a kind and wants to see
    "what else should I pull alongside this?".
    """
    return [
        {"name": k, **v}
        for k, v in KIND_RELATIONSHIPS.items()
        if kind in v.get("kinds", [])
    ]
