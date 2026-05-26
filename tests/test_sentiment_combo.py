"""Tests for the attention+polarity combo helper.

The helper composes two real fetchers, so we monkeypatch both at the
``quant_radar.tools.sentiment`` namespace where they're imported.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from quant_radar.tools import sentiment as sentiment_mod


def _attention_df(mentions: int = 690, prior: int = 70, rank: int = 1) -> pd.DataFrame:
    ts = pd.Timestamp("2026-05-26", tz=UTC)
    return pd.DataFrame(
        [{
            "ticker": "MU",
            "name": "Micron Technology",
            "mentions": mentions,
            "mentions_24h_ago": prior,
            "mentions_change_pct": round((mentions - prior) / max(prior, 1) * 100, 1),
            "upvotes": 4500,
            "rank": rank,
            "rank_24h_ago": rank + 3,
            "filter": "all-stocks",
        }],
        index=pd.DatetimeIndex([ts], name="timestamp"),
    )


def _polarity_df(scores: list[float], relevance: list[float]) -> pd.DataFrame:
    n = len(scores)
    idx = pd.DatetimeIndex(
        [pd.Timestamp("2026-05-26", tz=UTC) + pd.Timedelta(hours=i) for i in range(n)],
        name="timestamp",
    )
    return pd.DataFrame(
        {
            "sentiment_score": scores,
            "relevance_score": relevance,
            "overall_score": scores,
            "sentiment_label": ["x"] * n,
            "title": ["t"] * n,
            "url": ["u"] * n,
            "article_source": ["s"] * n,
            "topics": [""] * n,
        },
        index=idx,
    )


def test_combo_loud_positive(monkeypatch):
    monkeypatch.setattr(
        sentiment_mod, "fetch_social_sentiment",
        lambda t, refresh=False: (_attention_df(mentions=690, prior=70, rank=1), "apewisdom"),
    )
    monkeypatch.setattr(
        sentiment_mod, "fetch_sentiment",
        lambda t, refresh=False: (
            _polarity_df([0.45, 0.5, 0.4], [1.0, 0.8, 1.0]), "alphavantage",
        ),
    )
    out = sentiment_mod.fetch_attention_and_polarity("MU")
    assert out["ticker"] == "MU"
    assert out["attention"]["mentions"] == 690
    assert out["attention"]["source"] == "apewisdom"
    assert out["polarity"]["label"] == "Bullish"
    assert out["polarity"]["source"] == "alphavantage"
    assert out["polarity"]["article_count"] == 3
    assert out["divergence"] == "loud + positive"


def test_combo_quiet_negative(monkeypatch):
    monkeypatch.setattr(
        sentiment_mod, "fetch_social_sentiment",
        lambda t, refresh=False: (_attention_df(mentions=5, prior=4, rank=500), "apewisdom"),
    )
    monkeypatch.setattr(
        sentiment_mod, "fetch_sentiment",
        lambda t, refresh=False: (
            _polarity_df([-0.5, -0.45], [1.0, 1.0]), "marketaux",
        ),
    )
    out = sentiment_mod.fetch_attention_and_polarity("MU")
    assert out["attention"] is not None
    assert out["polarity"]["label"] == "Bearish"
    assert out["polarity"]["source"] == "marketaux"
    assert out["divergence"] == "quiet + negative"


def test_combo_attention_only(monkeypatch):
    monkeypatch.setattr(
        sentiment_mod, "fetch_social_sentiment",
        lambda t, refresh=False: (_attention_df(mentions=200, prior=20, rank=10), "apewisdom"),
    )

    def boom(*a, **kw):
        raise RuntimeError("all sentiment providers failed")

    monkeypatch.setattr(sentiment_mod, "fetch_sentiment", boom)
    out = sentiment_mod.fetch_attention_and_polarity("MU")
    assert out["attention"]["mentions"] == 200
    assert out["polarity"] is None
    assert out["divergence"] == "loud + no news"


def test_combo_no_signal(monkeypatch):
    empty_attention = _attention_df(mentions=0).iloc[0:0]
    monkeypatch.setattr(
        sentiment_mod, "fetch_social_sentiment",
        lambda t, refresh=False: (empty_attention, "apewisdom"),
    )

    def boom(*a, **kw):
        raise RuntimeError("all sentiment providers failed")

    monkeypatch.setattr(sentiment_mod, "fetch_sentiment", boom)
    out = sentiment_mod.fetch_attention_and_polarity("ZZZNOTREAL")
    assert out["attention"] is None
    assert out["polarity"] is None
    assert out["divergence"] == "no signal"


def test_combo_relevance_weighting(monkeypatch):
    # Article with low relevance (off-topic mention) should drag the score
    # less than a high-relevance article. Two articles: +0.6 @ rel 1.0,
    # -0.5 @ rel 0.1. Naive mean = +0.05 (Neutral). Weighted = (0.6 + -0.05)/1.1
    # = +0.5 (Bullish). Helper should pick the weighted form.
    monkeypatch.setattr(
        sentiment_mod, "fetch_social_sentiment",
        lambda t, refresh=False: (_attention_df(rank=50), "apewisdom"),
    )
    monkeypatch.setattr(
        sentiment_mod, "fetch_sentiment",
        lambda t, refresh=False: (
            _polarity_df([0.6, -0.5], [1.0, 0.1]), "alphavantage",
        ),
    )
    out = sentiment_mod.fetch_attention_and_polarity("MU")
    assert out["polarity"]["mean_sentiment_score"] > 0.35  # Bullish
    assert out["polarity"]["label"] == "Bullish"
