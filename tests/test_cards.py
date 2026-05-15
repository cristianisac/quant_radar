"""Tests for the card spec, persistence, and agent-facing tools."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quant_radar import tools
from quant_radar.cards import Card, ChartSpec, DataRef, store
from quant_radar.core import config as config_module


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    fake = config_module._build_paths(tmp_path)
    fake.ensure()
    monkeypatch.setattr(config_module, "paths", fake)
    import quant_radar.cards.store as store_mod

    monkeypatch.setattr(store_mod, "paths", fake)
    yield fake


def _chart_card(title: str = "BTC daily") -> Card:
    return Card(
        type="chart",
        title=title,
        data_refs=[DataRef(source="yfinance", kind="ohlcv", name="BTC-USD")],
        chart_spec=ChartSpec(overlays=["sma_50", "sma_200"]),
    )


# --------------- Pydantic model ---------------


def test_card_roundtrips_json():
    card = _chart_card()
    raw = card.model_dump_json()
    restored = Card.model_validate_json(raw)
    assert restored.id == card.id
    assert restored.chart_spec is not None
    assert restored.chart_spec.overlays == ["sma_50", "sma_200"]


def test_card_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Card.model_validate({"type": "chart", "title": "x", "foo": "bar"})


# --------------- Main (SQLite) ---------------


def test_main_save_and_list():
    a = _chart_card("A")
    b = _chart_card("B")
    store.main_save(a)
    store.main_save(b)
    titles = sorted(c.title for c in store.main_list())
    assert titles == ["A", "B"]


def test_main_save_is_upsert():
    a = _chart_card("orig")
    store.main_save(a)
    a.title = "renamed"
    store.main_save(a)
    cards = store.main_list()
    assert len(cards) == 1
    assert cards[0].title == "renamed"


def test_main_remove():
    a = _chart_card()
    store.main_save(a)
    assert store.main_remove(a.id) is True
    assert store.main_remove(a.id) is False
    assert store.main_list() == []


def test_main_persists_across_reconnects(tmp_path):
    a = _chart_card()
    store.main_save(a)
    fresh = store.main_list()
    assert len(fresh) == 1
    assert fresh[0].id == a.id


# --------------- Working (JSON) ---------------


def test_working_save_and_list():
    store.working_save(_chart_card("W1"))
    store.working_save(_chart_card("W2"))
    titles = [c.title for c in store.working_list()]
    assert set(titles) == {"W1", "W2"}


def test_working_save_updates_in_place():
    a = _chart_card("v1")
    store.working_save(a)
    a.title = "v2"
    store.working_save(a)
    cards = store.working_list()
    assert len(cards) == 1
    assert cards[0].title == "v2"


def test_working_reset_clears_all():
    store.working_save(_chart_card("x"))
    store.working_save(_chart_card("y"))
    store.working_reset()
    assert store.working_list() == []


def test_working_remove_returns_bool():
    a = _chart_card()
    store.working_save(a)
    assert store.working_remove(a.id) is True
    assert store.working_remove(a.id) is False


# --------------- Cross-store ---------------


def test_promote_to_main_copies_card():
    a = _chart_card("promoteme")
    store.working_save(a)
    promoted = store.promote_to_main(a.id)
    assert promoted is not None
    assert any(c.id == a.id for c in store.main_list())
    # working copy remains intact (spec: "leaves working copy in place")
    assert any(c.id == a.id for c in store.working_list())


def test_promote_missing_card_returns_none():
    from uuid import uuid4

    assert store.promote_to_main(uuid4()) is None


# --------------- Agent-facing tools ---------------


def test_create_dashboard_card_default_target_is_working():
    out = tools.create_dashboard_card(
        type="chart",
        title="BTC",
        data_refs=[{"source": "yfinance", "kind": "ohlcv", "name": "BTC-USD"}],
        chart_spec={"overlays": ["sma_50"]},
    )
    assert out["title"] == "BTC"
    listing = tools.load_dashboard("working")
    assert len(listing) == 1
    assert tools.load_dashboard("main") == []


def test_save_card_to_dashboard_promotes_to_main():
    created = tools.create_dashboard_card(type="analysis", title="t", analysis_markdown="x")
    ok = tools.save_card_to_dashboard(created["id"])
    assert ok is True
    assert len(tools.load_dashboard("main")) == 1


def test_save_card_to_dashboard_missing_returns_false():
    from uuid import uuid4

    assert tools.save_card_to_dashboard(uuid4()) is False


def test_remove_card_from_working():
    created = tools.create_dashboard_card(type="analysis", title="t", analysis_markdown="x")
    assert tools.remove_card(created["id"]) is True
    assert tools.load_dashboard("working") == []


def test_new_working_dashboard_resets():
    tools.create_dashboard_card(type="analysis", title="a", analysis_markdown="x")
    tools.create_dashboard_card(type="analysis", title="b", analysis_markdown="y")
    tools.new_working_dashboard()
    assert tools.load_dashboard("working") == []


def test_persist_dashboard_returns_count():
    tools.create_dashboard_card(type="analysis", title="t", analysis_markdown="x")
    assert tools.persist_dashboard("working") == 1


def test_add_annotation_round_trip():
    created = tools.create_dashboard_card(
        type="chart",
        title="BTC",
        data_refs=[{"source": "yfinance", "kind": "ohlcv", "name": "BTC-USD"}],
        chart_spec={"overlays": ["sma_50"]},
    )
    ok = tools.add_annotation(
        created["id"],
        {"kind": "trendline", "points": [[1700000000.0, 50000.0], [1710000000.0, 60000.0]]},
    )
    assert ok is True
    card = store.working_get(created["id"])
    assert card is not None
    assert card.chart_spec is not None
    assert len(card.chart_spec.annotations) == 1
    assert card.chart_spec.annotations[0].kind == "trendline"


def test_add_annotation_no_chart_spec_returns_false():
    created = tools.create_dashboard_card(
        type="analysis", title="t", analysis_markdown="text"
    )
    ok = tools.add_annotation(created["id"], {"kind": "hline", "points": [[0, 0]]})
    assert ok is False


# --------------- update_card ---------------


def test_update_card_partial_update_keeps_id_and_other_fields():
    created = tools.create_dashboard_card(
        type="chart",
        title="orig",
        data_refs=[{"source": "yfinance", "kind": "ohlcv", "name": "BTC-USD"}],
        chart_spec={"overlays": ["sma_50"], "subplots": []},
    )
    updated = tools.update_card(
        created["id"],
        chart_spec={"overlays": ["sma_50", "sma_200"], "subplots": ["rsi", "atr"]},
    )
    assert updated is not None
    assert updated["id"] == created["id"]
    assert updated["title"] == "orig"  # untouched
    assert updated["chart_spec"]["overlays"] == ["sma_50", "sma_200"]
    assert updated["chart_spec"]["subplots"] == ["rsi", "atr"]
    assert updated["data_refs"] == created["data_refs"]


def test_update_card_title_only():
    created = tools.create_dashboard_card(
        type="analysis", title="orig", analysis_markdown="x"
    )
    updated = tools.update_card(created["id"], title="renamed")
    assert updated is not None
    assert updated["title"] == "renamed"
    assert updated["analysis_markdown"] == "x"


def test_update_card_missing_returns_none():
    from uuid import uuid4

    assert tools.update_card(uuid4(), title="x") is None


def test_update_card_in_main_target():
    created = tools.create_dashboard_card(
        type="analysis", title="orig", analysis_markdown="x", target="main"
    )
    updated = tools.update_card(
        created["id"], target="main", analysis_markdown="new text"
    )
    assert updated is not None
    assert updated["analysis_markdown"] == "new text"
    main = tools.load_dashboard("main")
    assert main[0]["analysis_markdown"] == "new text"


# --------------- working session lifecycle ---------------


def test_working_open_after_new_even_when_empty():
    tools.new_working_dashboard()
    assert store.working_is_open() is True
    assert tools.load_dashboard("working") == []


def test_close_working_dashboard_removes_file():
    tools.create_dashboard_card(type="analysis", title="t", analysis_markdown="x")
    assert store.working_is_open() is True
    tools.close_working_dashboard()
    assert store.working_is_open() is False
    assert tools.load_dashboard("working") == []


def test_close_working_dashboard_idempotent():
    tools.close_working_dashboard()
    tools.close_working_dashboard()
    assert store.working_is_open() is False


def test_new_then_close_lifecycle():
    tools.new_working_dashboard()
    assert store.working_is_open() is True
    tools.create_dashboard_card(type="analysis", title="t", analysis_markdown="x")
    assert len(tools.load_dashboard("working")) == 1
    tools.close_working_dashboard()
    assert store.working_is_open() is False
