"""Tests for the cross-kind relationships registry."""

from __future__ import annotations

from quant_radar import tools
from quant_radar.sources import kind_relationships


def test_list_relationships_has_canonical_entries():
    out = tools.list_kind_relationships()
    names = {r["name"] for r in out}
    # The combos motivated explicitly by user-facing flows.
    assert "attention_and_polarity" in names
    assert "fundamentals_triplet" in names
    assert "price_in_context" in names


def test_relationship_record_shape():
    rec = kind_relationships.get_relationship("attention_and_polarity")
    assert rec is not None
    assert rec["relationship"] == "orthogonal"
    assert set(rec["kinds"]) == {"social_sentiment", "sentiment"}
    assert rec["combo_tool"] == "fetch_attention_and_polarity"
    assert "rationale" in rec and rec["rationale"]


def test_relationships_for_kind_filters():
    out = tools.relationships_for_kind("ohlcv")
    names = {r["name"] for r in out}
    # OHLCV anchors both price_in_context (news/sentiment) and macro_with_asset.
    assert "price_in_context" in names
    assert "macro_with_asset" in names
    assert "fundamentals_triplet" not in names

    out2 = tools.relationships_for_kind("sentiment")
    names2 = {r["name"] for r in out2}
    assert "attention_and_polarity" in names2


def test_kind_coverage_passthrough():
    cov = tools.describe_kind_coverage("sentiment")
    assert cov is not None
    assert "alphavantage" in cov["providers"]
    assert "marketaux" in cov["providers"]
    assert tools.describe_kind_coverage("nonexistent_kind") is None


def test_list_covered_kinds():
    kinds = tools.list_covered_kinds()
    assert "sentiment" in kinds
    assert "social_sentiment" in kinds
