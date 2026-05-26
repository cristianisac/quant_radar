"""Agent-facing sentiment tools.

Implements the multi-source routing described in
``quant_radar/sources/kind_coverage.py`` for ``kind="sentiment"``:

- ``fetch_sentiment(ticker)`` tries the primary source (Alpha Vantage)
  first and silently falls back to Marketaux when AV's daily quota is
  exhausted. The agent never needs to know which source ultimately
  served the data unless it asks.

- ``describe_sentiment_routing(kind="sentiment")`` returns the
  structured comparison from kind_coverage.py so the agent can read
  it at session start and make informed choices when the user asks
  about *which* source to use or *why*.

Per-ticker sentiment cards should reach for this rather than calling
the source adapters directly — it bakes the routing logic in one
place instead of pushing it onto every caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from quant_radar.cards.spec import DataRef
from quant_radar.sources import kind_coverage
from quant_radar.sources.hydrate import hydrate


def fetch_sentiment(
    ticker: str, *,
    source: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Fetch per-ticker news sentiment with automatic provider fallback.

    Returns ``(df, source_used)`` so the caller can show which provider
    actually served the data (useful in the UI when displaying scoped
    sentiment over time).

    If ``source`` is set, only that source is tried (no fallback).
    Otherwise walks the chain declared in kind_coverage.sentiment.

    Each row in the returned DataFrame is one article that mentions the
    ticker, with columns: sentiment_score, relevance_score,
    overall_score, sentiment_label, title, url, article_source, topics.
    """
    cov = kind_coverage.get_coverage("sentiment")
    if cov is None:
        raise RuntimeError("kind_coverage missing 'sentiment' entry")

    chain = [source] if source else cov.get("default_chain", [])
    if not chain:
        raise RuntimeError("no providers configured for kind='sentiment'")

    last_err: Exception | None = None
    for src in chain:
        try:
            df = hydrate(
                DataRef(
                    source=src, kind="sentiment",
                    name=ticker.upper(), interval="event",
                    start=start, end=end,
                ),
                refresh=refresh,
            )
            return df, src
        except Exception as e:  # noqa: BLE001 — try next provider
            last_err = e
            continue

    raise RuntimeError(
        f"All sentiment providers in {chain} failed for {ticker}. "
        f"Last error: {type(last_err).__name__}: {last_err}"
    )


def describe_sentiment_routing() -> dict[str, Any]:
    """Return the multi-source routing record for kind='sentiment'.

    The agent should call this once per session (or whenever the user
    asks about sentiment sources) to understand the relationship
    between providers — which is primary, which is fallback, which is
    complementary, and what each one's coverage/limits look like.
    """
    cov = kind_coverage.get_coverage("sentiment")
    return cov or {}


def fetch_social_sentiment(
    ticker: str, *,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Fetch Reddit-mention velocity for ``ticker`` via Apewisdom.

    Returns ``(df, source_used)`` mirroring ``fetch_sentiment``'s shape.
    The DataFrame is a single-row snapshot of the current 24h window:
    mentions, mentions_24h_ago, mentions_change_pct, upvotes, rank, plus
    the filter (``all-stocks`` or ``all-crypto``) the ticker came from.

    Empty DataFrame means the ticker isn't on Apewisdom's current
    leaderboard — that's a real signal (no chatter), not an error.
    """
    cov = kind_coverage.get_coverage("social_sentiment")
    if cov is None:
        raise RuntimeError("kind_coverage missing 'social_sentiment' entry")

    chain = cov.get("default_chain", [])
    if not chain:
        raise RuntimeError("no providers configured for kind='social_sentiment'")

    last_err: Exception | None = None
    for src in chain:
        try:
            df = hydrate(
                DataRef(
                    source=src, kind="social_sentiment",
                    name=ticker.upper(), interval="snapshot",
                    start=start, end=end,
                ),
                refresh=refresh,
            )
            return df, src
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue

    raise RuntimeError(
        f"All social_sentiment providers in {chain} failed for {ticker}. "
        f"Last error: {type(last_err).__name__}: {last_err}"
    )


def describe_social_sentiment_routing() -> dict[str, Any]:
    """Return the multi-source routing record for kind='social_sentiment'."""
    cov = kind_coverage.get_coverage("social_sentiment")
    return cov or {}


def fetch_attention_and_polarity(
    ticker: str, *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Combine the volume axis (Apewisdom) with the polarity axis (AV/Marketaux).

    The two are orthogonal:

    - **Attention** = how loud is the room? mention count + 24h velocity
      from Apewisdom (Reddit-aggregator).
    - **Polarity** = what is the news saying? mean sentiment score +
      bullish/bearish/neutral label from Alpha Vantage (falls back to
      Marketaux when AV quota is exhausted).

    Returned dict shape::

        {
          "ticker": "MU",
          "attention": {
            "mentions": int, "mentions_24h_ago": int,
            "mentions_change_pct": float, "rank": int,
            "rank_24h_ago": int, "filter": "all-stocks"|"all-crypto",
            "source": "apewisdom",
          } | None,
          "polarity": {
            "mean_sentiment_score": float,        # ticker-relevance weighted
            "label": "Bullish"|"Somewhat-Bullish"|"Neutral"|"Somewhat-Bearish"|"Bearish",
            "article_count": int,
            "source": "alphavantage"|"marketaux",
          } | None,
          "divergence": str,   # human-readable interpretation, see below
        }

    ``attention`` is None when Apewisdom doesn't list the ticker (no
    chatter). ``polarity`` is None when every sentiment provider failed
    (e.g. all quotas exhausted, ticker not covered).

    The ``divergence`` string is the agent's headline read:

    - ``"loud + positive"``: both axes agree, strong directional conviction
    - ``"loud + negative"``: both axes agree, downside conviction
    - ``"loud + neutral"``: pure attention spike, no news support — meme / speculative
    - ``"loud + no news"``: high mentions, no news polarity available
    - ``"quiet + positive"``: news upgrade not yet on retail's radar
    - ``"quiet + negative"``: negative news not yet trending
    - ``"quiet + neutral"``: nothing to see
    - ``"no signal"``: neither axis returned data
    """
    # Attention
    attention: dict[str, Any] | None = None
    try:
        df_a, src_a = fetch_social_sentiment(ticker, refresh=refresh)
        if not df_a.empty:
            row = df_a.iloc[0]
            attention = {
                "mentions": int(row["mentions"]),
                "mentions_24h_ago": int(row["mentions_24h_ago"]),
                "mentions_change_pct": float(row["mentions_change_pct"]),
                "rank": int(row["rank"]),
                "rank_24h_ago": int(row["rank_24h_ago"]),
                "filter": str(row["filter"]),
                "source": src_a,
            }
    except Exception:  # noqa: BLE001 — attention is optional
        attention = None

    # Polarity — weighted by per-article relevance so off-topic mentions
    # don't drag the score.
    polarity: dict[str, Any] | None = None
    try:
        df_p, src_p = fetch_sentiment(ticker, refresh=refresh)
        if not df_p.empty and "sentiment_score" in df_p.columns:
            scores = pd.to_numeric(df_p["sentiment_score"], errors="coerce").dropna()
            relevance = pd.to_numeric(
                df_p.get("relevance_score", pd.Series([1.0] * len(scores))),
                errors="coerce",
            ).fillna(1.0)
            common = scores.index.intersection(relevance.index)
            scores = scores.loc[common]
            relevance = relevance.loc[common]
            if len(scores) > 0 and relevance.sum() > 0:
                mean_score = float((scores * relevance).sum() / relevance.sum())
            elif len(scores) > 0:
                mean_score = float(scores.mean())
            else:
                mean_score = 0.0
            polarity = {
                "mean_sentiment_score": round(mean_score, 4),
                "label": _label_from_score(mean_score),
                "article_count": int(len(df_p)),
                "source": src_p,
            }
    except Exception:  # noqa: BLE001 — polarity is optional
        polarity = None

    return {
        "ticker": ticker.upper(),
        "attention": attention,
        "polarity": polarity,
        "divergence": _interpret_divergence(attention, polarity),
    }


def _label_from_score(score: float) -> str:
    """Same thresholds as Alpha Vantage's published cutoffs."""
    if score >= 0.35:
        return "Bullish"
    if score >= 0.10:
        return "Somewhat-Bullish"
    if score > -0.10:
        return "Neutral"
    if score > -0.35:
        return "Somewhat-Bearish"
    return "Bearish"


def _interpret_divergence(
    attention: dict[str, Any] | None,
    polarity: dict[str, Any] | None,
) -> str:
    if attention is None and polarity is None:
        return "no signal"

    # "Loud" = mentions in top-100 of leaderboard OR mentions_change_pct >= 100%
    is_loud = False
    if attention is not None:
        is_loud = (
            attention["rank"] <= 100
            or attention["mentions_change_pct"] >= 100.0
        )

    loud_str = "loud" if is_loud else "quiet"

    if polarity is None:
        return f"{loud_str} + no news"

    label = polarity["label"]
    if label in ("Bullish", "Somewhat-Bullish"):
        return f"{loud_str} + positive"
    if label in ("Bearish", "Somewhat-Bearish"):
        return f"{loud_str} + negative"
    return f"{loud_str} + neutral"
