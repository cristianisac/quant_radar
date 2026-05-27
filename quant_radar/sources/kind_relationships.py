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
    "regulatory_paper_trail": {
        "description": (
            "SEC filings + insider transactions + analyst estimates. "
            "The paper trail behind a name: what management actually "
            "filed, what insiders actually bought/sold, what analysts "
            "actually project."
        ),
        "kinds": ["sec_filings", "insider", "estimates"],
        "relationship": "siblings",
        "combo_tool": None,
        "rationale": (
            "When the user asks 'what's the actual regulatory paper "
            "trail for X' (often before earnings or after a news "
            "spike), pair these three. Insider transactions are a "
            "specific Form-4 subset of all filings — the wider "
            "sec_filings table catches 10-K / 10-Q / 8-K / etc."
        ),
    },
    "options_overlay": {
        "description": (
            "Options chain (strikes + expirations) layered onto the "
            "underlying's OHLCV. Read implied positioning by where "
            "open interest / strike density clusters."
        ),
        "kinds": ["options_chain", "ohlcv"],
        "relationship": "primary_plus_context",
        "combo_tool": None,
        "rationale": (
            "When the user asks about positioning, gamma exposure, or "
            "'where are the bets', pair OHLCV with the options chain. "
            "Strike density at a given expiration is a crude open-"
            "interest proxy; per-contract aggregates (separate "
            "DataRef with the contract_ticker as name) give the "
            "actual historical volume."
        ),
    },
    "macro_event_overlay": {
        "description": (
            "Economic calendar (CPI, NFP, ECB / Fed decisions, PMIs) "
            "layered against an asset's price chart. Tells the agent "
            "which scheduled macro prints to watch and shows where in "
            "history past prints printed surprise vs consensus."
        ),
        "kinds": ["economic_calendar", "ohlcv", "macro"],
        "relationship": "primary_plus_context",
        "combo_tool": None,
        "rationale": (
            "When the user asks about positioning around a macro print "
            "(CPI day, NFP, FOMC), pair the relevant economic_calendar "
            "table with the asset OHLCV. For long-horizon studies pair "
            "with the matching FRED macro series — historical actuals "
            "in the same shape as the upcoming forecasts."
        ),
    },
    "event_calendar_overlay": {
        "description": (
            "Forward event calendars (earnings, IPOs) layered with the "
            "ticker's OHLCV chart. Tells the agent where the next "
            "catalysts are without leaving the price view."
        ),
        "kinds": ["earnings_calendar", "ipo_calendar", "ohlcv"],
        "relationship": "primary_plus_context",
        "combo_tool": None,
        "rationale": (
            "When the user asks 'what's coming up' or wants to position "
            "around an upcoming print, pair OHLCV with the relevant "
            "calendar. Earnings calendar for individual names; IPO "
            "calendar for sector-wide flow / new-listing impact."
        ),
    },
    "shareholder_returns": {
        "description": (
            "Dividends + splits give the full picture of cash + structural "
            "returns to shareholders over time. Dividends show the cash "
            "yield trajectory; splits show share-count history (relevant "
            "for adjusted-vs-raw price comparisons)."
        ),
        "kinds": ["dividends", "splits"],
        "relationship": "siblings",
        "combo_tool": None,
        "rationale": (
            "When the user asks about a ticker's payout history or wants "
            "to understand a stock's return composition, create both as "
            "table cards. For a card-view preview, dividends is usually "
            "the headline; splits is a context table that's rarely the "
            "primary focus."
        ),
    },
    "actuals_vs_estimates": {
        "description": (
            "Forward analyst estimates (revenue / EPS / EBITDA ranges) "
            "vs the historical fundamentals trio. Useful for 'is the "
            "company beating or missing'."
        ),
        "kinds": ["estimates", "income", "balance", "cash"],
        "relationship": "primary_plus_context",
        "combo_tool": None,
        "rationale": (
            "Pair forward estimates (kind='estimates') with the most "
            "recent income statement when the user asks about consensus "
            "vs reality. Balance + cash become relevant when the question "
            "is about ability-to-deliver, not just earnings power."
        ),
    },
    "analyst_consensus": {
        "description": (
            "Monthly analyst recommendation counts (strong_buy / buy / "
            "hold / sell / strong_sell) plotted as a sentiment signal "
            "alongside news polarity and social attention."
        ),
        "kinds": ["recommendation", "sentiment", "social_sentiment"],
        "relationship": "orthogonal",
        "combo_tool": None,
        "rationale": (
            "Analyst consensus shifts slowly but reliably. When "
            "recommendation trend is improving (more buy / fewer sell) "
            "but social_sentiment is loud-negative, you're watching a "
            "professional / retail divergence. Surface both alongside "
            "the news polarity for the fullest picture."
        ),
    },
    "insider_ownership": {
        "description": (
            "Insider transactions (Form-4 filings) + monthly MSPR + "
            "sentiment + social signals. Compare what insiders are "
            "DOING with what news / Reddit are SAYING. MSPR (kind="
            "'insider_sentiment') normalizes net buying/selling to "
            "[-1, +1]; insider (kind='insider') gives raw Form-4 "
            "transaction detail."
        ),
        "kinds": [
            "insider", "insider_sentiment",
            "sentiment", "social_sentiment",
        ],
        "relationship": "orthogonal",
        "combo_tool": None,
        "rationale": (
            "Insiders selling into a news/social-sentiment spike is a "
            "classic divergence — the loudest convictions often coincide "
            "with the people closest to the data quietly cashing out. "
            "Use insider table alongside the attention+polarity combo "
            "for the fullest picture."
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
        "kinds": ["ohlcv", "sentiment", "social_sentiment", "news", "news_tone"],
        "relationship": "primary_plus_context",
        "combo_tool": None,
        "rationale": (
            "When the user asks 'why did X move' or 'what's behind this "
            "spike', pair the price chart with whichever context kind "
            "the data supports. For US equities/ETFs: sentiment + news. "
            "For meme tickers (MU, GME, TSLA): also social_sentiment. "
            "For crypto: social_sentiment + news + news_tone (GDELT "
            "topic-level tone for the broader narrative)."
        ),
    },
    "macro_mood_overlay": {
        "description": (
            "GDELT topic-level tone time-series (news_tone) charted "
            "alongside an asset's OHLCV. Tone is article-level / "
            "macro-mood, NOT per-ticker — use for narrative reads "
            "('how is the crypto coverage tone shifting?'), not "
            "per-stock signals."
        ),
        "kinds": ["news_tone", "ohlcv"],
        "relationship": "primary_plus_context",
        "combo_tool": None,
        "rationale": (
            "When the user asks about narrative shifts ('is bitcoin "
            "coverage turning sour?', 'how is AI-stock sentiment vs "
            "last month?'), pull a GDELT news_tone time-series against "
            "the asset OHLCV. Don't use this for per-ticker sentiment — "
            "GDELT tone is aggregated across all articles matching the "
            "query, so multi-ticker matches dilute the signal."
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
