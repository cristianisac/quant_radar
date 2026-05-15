"""Tests for news source adapters and the news/sentiment tool wrappers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import requests
import responses

from quant_radar import tools
from quant_radar.sources import finnhub_src, gdelt_src

# --------------- GDELT ---------------


_GDELT_PAYLOAD = {
    "articles": [
        {
            "url": "https://example.com/a",
            "title": "Bitcoin rallies on macro relief",
            "domain": "example.com",
            "language": "English",
            "sourcecountry": "US",
            "seendate": "20260515T120000Z",
        },
        {
            "url": "https://news.example/b",
            "title": "AI stocks pull back",
            "domain": "news.example",
            "language": "English",
            "sourcecountry": "US",
            "seendate": "20260515T100000Z",
        },
    ]
}


@responses.activate
def test_gdelt_fetch_news_normalizes():
    responses.add(
        responses.GET, gdelt_src._BASE, json=_GDELT_PAYLOAD, status=200,
    )
    items = gdelt_src.fetch_news("BTC", max_records=10)
    assert len(items) == 2
    assert items[0]["title"] == "Bitcoin rallies on macro relief"
    assert items[0]["source"] == "example.com"
    assert items[0]["published_at"].endswith("+00:00")


@responses.activate
def test_gdelt_fetch_news_uses_timespan_by_default():
    responses.add(
        responses.GET, gdelt_src._BASE, json={"articles": []}, status=200,
    )
    gdelt_src.fetch_news("BTC")
    url = responses.calls[0].request.url or ""
    assert "timespan=1d" in url
    assert "startdatetime" not in url


@responses.activate
def test_gdelt_fetch_news_uses_explicit_range_when_given():
    responses.add(
        responses.GET, gdelt_src._BASE, json={"articles": []}, status=200,
    )
    gdelt_src.fetch_news(
        "BTC",
        start=datetime(2026, 5, 1, tzinfo=UTC),
        end=datetime(2026, 5, 8, tzinfo=UTC),
    )
    url = responses.calls[0].request.url or ""
    assert "startdatetime=20260501000000" in url
    assert "enddatetime=20260508000000" in url


@responses.activate
def test_gdelt_handles_non_json_response():
    responses.add(
        responses.GET, gdelt_src._BASE, body="<html>not json</html>", status=200,
    )
    assert gdelt_src.fetch_news("BTC") == []


@responses.activate
def test_gdelt_http_error_propagates():
    responses.add(
        responses.GET, gdelt_src._BASE, json={"err": "limited"}, status=429,
    )
    with pytest.raises(requests.HTTPError):
        gdelt_src.fetch_news("BTC")


# --------------- Finnhub ---------------


_FINNHUB_PAYLOAD = [
    {
        "category": "general",
        "datetime": 1747300000,
        "headline": "Fed cuts rates",
        "id": 1,
        "image": "",
        "related": "",
        "source": "Reuters",
        "summary": "The Fed cut rates by 25bps...",
        "url": "https://example.com/fed",
    },
    {
        "category": "general",
        "datetime": 1747300050,
        "headline": "Markets rally",
        "id": 2,
        "image": "",
        "related": "",
        "source": "Bloomberg",
        "summary": "Stocks moved sharply higher...",
        "url": "https://example.com/rally",
    },
]


def test_finnhub_no_key_raises(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FINNHUB_API_KEY"):
        finnhub_src.fetch_general_news()


@responses.activate
def test_finnhub_general_news(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    responses.add(
        responses.GET, f"{finnhub_src._BASE}/news", json=_FINNHUB_PAYLOAD, status=200,
    )
    items = finnhub_src.fetch_general_news()
    assert len(items) == 2
    assert items[0]["title"] == "Fed cuts rates"
    assert items[0]["source"] == "Reuters"
    assert items[0]["summary"].startswith("The Fed")


@responses.activate
def test_finnhub_company_news(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    responses.add(
        responses.GET,
        f"{finnhub_src._BASE}/company-news",
        json=_FINNHUB_PAYLOAD,
        status=200,
    )
    items = finnhub_src.fetch_company_news(
        "AAPL",
        start=datetime(2026, 5, 1, tzinfo=UTC),
        end=datetime(2026, 5, 8, tzinfo=UTC),
    )
    assert len(items) == 2
    url = responses.calls[0].request.url or ""
    assert "symbol=AAPL" in url
    assert "from=2026-05-01" in url
    assert "to=2026-05-08" in url


# --------------- agent-facing tools ---------------


@responses.activate
def test_tools_fetch_news_routes_to_gdelt():
    responses.add(
        responses.GET, gdelt_src._BASE, json=_GDELT_PAYLOAD, status=200,
    )
    items = tools.fetch_news("BTC")
    assert len(items) == 2


def test_tools_fetch_news_finnhub_requires_dates():
    with pytest.raises(ValueError, match="start and end"):
        tools.fetch_news("AAPL", source="finnhub")


def test_tools_fetch_news_unknown_source_raises():
    with pytest.raises(ValueError, match="unknown news source"):
        tools.fetch_news("BTC", source="bogus")  # type: ignore[arg-type]


@responses.activate
def test_tools_fetch_top_headlines_gdelt():
    responses.add(
        responses.GET, gdelt_src._BASE, json=_GDELT_PAYLOAD, status=200,
    )
    items = tools.fetch_top_headlines()
    assert len(items) == 2


@responses.activate
def test_tools_fetch_top_headlines_finnhub(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    responses.add(
        responses.GET, f"{finnhub_src._BASE}/news", json=_FINNHUB_PAYLOAD, status=200,
    )
    items = tools.fetch_top_headlines(source="finnhub")
    assert len(items) == 2


def test_summarize_news_returns_structured_payload():
    items = [{"title": "x", "url": "u", "source": "s"}]
    out = tools.summarize_news(items)
    assert out["items_count"] == 1
    assert out["items"] == items
    assert "instructions" in out and "summary" in out["instructions"].lower()


def test_summarize_news_empty():
    out = tools.summarize_news([])
    assert out["items_count"] == 0
    assert out["items"] == []


def test_score_sentiment_returns_structured_payload():
    items = [{"title": "stocks up", "url": "u", "source": "s"}]
    out = tools.score_sentiment(items, topic="AI stocks")
    assert out["items_count"] == 1
    assert out["topic"] == "AI stocks"
    assert "bullish" in out["instructions"]
    assert "bearish" in out["instructions"]


def test_score_sentiment_topic_optional():
    out = tools.score_sentiment([])
    assert out["topic"] is None
