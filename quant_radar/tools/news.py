"""Agent-facing news + sentiment tools.

The summarize/score tools are **LLM-first** in the same way the vision
pattern tool is: they prep a structured payload that the calling agent
(Claude Code) reasons over directly. There's no external SDK call —
the agent already has multimodal text reasoning.

A deterministic FinBERT scorer is deferred per the user's direction; if
added later, it lives behind a ``method="finbert"`` flag.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from quant_radar.sources import finnhub_src, gdelt_src

NewsSource = Literal["gdelt", "finnhub"]


def fetch_news(
    query: str,
    *,
    source: NewsSource = "gdelt",
    start: datetime | None = None,
    end: datetime | None = None,
    max_items: int = 20,
) -> list[dict]:
    """Return a list of normalized news-item dicts."""
    if source == "gdelt":
        return gdelt_src.fetch_news(query, start=start, end=end, max_records=max_items)
    if source == "finnhub":
        if start is None or end is None:
            raise ValueError(
                "Finnhub company news requires start and end. For market-wide news, "
                "use fetch_top_headlines(source='finnhub') instead."
            )
        return finnhub_src.fetch_company_news(
            query, start=start, end=end, max_items=max_items
        )
    raise ValueError(f"unknown news source: {source!r}")


def fetch_top_headlines(
    *,
    source: NewsSource = "gdelt",
    category: str = "general",
    max_items: int = 10,
) -> list[dict]:
    """Latest headlines — GDELT for global, Finnhub for finance."""
    if source == "finnhub":
        return finnhub_src.fetch_general_news(category=category, max_items=max_items)
    return gdelt_src.fetch_news("*", max_records=max_items)


_SUMMARY_INSTRUCTIONS = (
    "Read the items below and write a 2-3 sentence summary covering the "
    "dominant themes. Then list the 3 most newsworthy headlines as a "
    "bulleted list (title and source). Be neutral; do not editorialize. "
    "If the items are sparse or conflicting, say so plainly."
)

_SENTIMENT_INSTRUCTIONS = (
    "Read each item below and score its tone toward the topic on a "
    "3-class scale: bullish, bearish, neutral. Return per-item scores, "
    "then an overall summary: distribution counts and a single label. "
    "Be conservative — when in doubt, choose neutral. Cite the item "
    "indices that drove the call."
)


def summarize_news(items: list[dict]) -> dict[str, Any]:
    """Structured payload for the calling LLM to summarize.

    Returns the items plus an instruction string. The agent (Claude Code)
    is the LLM — it should respond with the requested summary and may
    then persist a news card via ``create_dashboard_card``.
    """
    return {
        "items_count": len(items),
        "items": items,
        "instructions": _SUMMARY_INSTRUCTIONS,
    }


def score_sentiment(
    items: list[dict], *, topic: str | None = None
) -> dict[str, Any]:
    """Structured payload for the calling LLM to score sentiment."""
    return {
        "items_count": len(items),
        "items": items,
        "topic": topic,
        "instructions": _SENTIMENT_INSTRUCTIONS,
    }
