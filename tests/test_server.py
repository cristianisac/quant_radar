"""FastAPI endpoint tests.

Uses fastapi's TestClient (no uvicorn process needed). Cards store is
redirected to a tmp_path so tests are hermetic.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quant_radar.core import config as config_module
from quant_radar.server import create_app


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    fake = config_module._build_paths(tmp_path)
    fake.ensure()
    monkeypatch.setattr(config_module, "paths", fake)
    import quant_radar.cache.store as cache_store
    import quant_radar.cards.store as cards_store

    monkeypatch.setattr(cards_store, "paths", fake)
    monkeypatch.setattr(cache_store, "paths", fake)
    yield fake


@pytest.fixture
def client():
    return TestClient(create_app())


# ---------------- Health ----------------


def test_health_returns_status_and_version(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


# ---------------- Cards ----------------


def _chart_payload():
    return {
        "type": "chart",
        "title": "BTC",
        "data_refs": [{"source": "yfinance", "kind": "ohlcv", "name": "BTC-USD"}],
        "chart_spec": {"overlays": ["sma_50"]},
    }


def test_create_card_appears_in_working_listing(client):
    r = client.post("/api/cards", json=_chart_payload())
    assert r.status_code == 200
    card = r.json()
    assert card["title"] == "BTC"
    assert card["type"] == "chart"

    r = client.get("/api/cards/working")
    assert r.status_code == 200
    cards = r.json()
    assert len(cards) == 1
    assert cards[0]["id"] == card["id"]


def test_update_card_keeps_id_and_changes_only_provided_fields(client):
    created = client.post("/api/cards", json=_chart_payload()).json()
    r = client.patch(
        f"/api/cards/{created['id']}",
        params={"target": "working"},
        json={"title": "renamed"},
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["id"] == created["id"]
    assert updated["title"] == "renamed"
    # data_refs and chart_spec preserved
    assert updated["data_refs"] == created["data_refs"]


def test_update_missing_card_returns_404(client):
    r = client.patch(
        "/api/cards/00000000-0000-0000-0000-000000000000",
        json={"title": "x"},
    )
    assert r.status_code == 404


def test_remove_card(client):
    created = client.post("/api/cards", json=_chart_payload()).json()
    r = client.delete(f"/api/cards/{created['id']}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = client.delete(f"/api/cards/{created['id']}")
    assert r.json() == {"ok": False}


def test_clear_endpoint_removes_all_cards_from_target(client):
    # Seed 3 working cards.
    for title in ("a", "b", "c"):
        client.post("/api/cards", json={
            "type": "analysis", "title": title, "analysis_markdown": "x",
        })
    assert len(client.get("/api/cards/working").json()) == 3
    r = client.post("/api/cards/clear?target=working")
    assert r.status_code == 200
    assert r.json() == {"removed": 3}
    assert client.get("/api/cards/working").json() == []
    # Idempotent: clearing an empty target returns 0 (not 404).
    r = client.post("/api/cards/clear?target=working")
    assert r.json() == {"removed": 0}


def test_save_to_main_promotes_card(client):
    created = client.post(
        "/api/cards",
        json={"type": "analysis", "title": "t", "analysis_markdown": "x"},
    ).json()
    r = client.post(f"/api/cards/{created['id']}/save-to-main")
    assert r.status_code == 200 and r.json() == {"ok": True}
    main_cards = client.get("/api/cards/main").json()
    assert any(c["id"] == created["id"] for c in main_cards)


def test_add_annotation_roundtrips(client):
    created = client.post("/api/cards", json=_chart_payload()).json()
    ann = {"kind": "hline", "points": [[0.0, 70000.0]], "label": "support"}
    r = client.post(
        f"/api/cards/{created['id']}/annotations",
        json={"annotation": ann, "target": "working"},
    )
    assert r.status_code == 200 and r.json() == {"ok": True}
    reloaded = client.get("/api/cards/working").json()[0]
    assert reloaded["chart_spec"]["annotations"][0]["label"] == "support"


def test_working_lifecycle(client):
    # New session opens an empty working dashboard
    r = client.post("/api/working/new")
    assert r.status_code == 204
    assert client.get("/api/working/state").json() == {"is_open": True}
    assert client.get("/api/cards/working").json() == []

    # Close removes the file
    r = client.post("/api/working/close")
    assert r.status_code == 204
    assert client.get("/api/working/state").json() == {"is_open": False}


# ---------------- Sources ----------------


def test_list_sources_includes_known_backends(client):
    r = client.get("/api/sources")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert {"yfinance", "binance", "fred", "gdelt", "finnhub"} <= names


def test_describe_known_source(client):
    r = client.get("/api/sources/binance")
    assert r.status_code == 200
    assert r.json()["name"] == "binance"


def test_describe_unknown_source_404(client):
    r = client.get("/api/sources/nope")
    assert r.status_code == 404


def test_probe_history_mocked(client):
    raw = pd.DataFrame(
        {
            "Open": range(300), "High": range(300), "Low": range(300),
            "Close": range(300), "Adj Close": range(300), "Volume": range(300),
        },
        index=pd.date_range("2020-01-01", periods=300, freq="D"),
    )
    from quant_radar.sources import yfinance_src

    with patch.object(yfinance_src.yf, "download", return_value=raw):
        r = client.get("/api/probe-history", params={"symbol": "AAPL"})
    assert r.status_code == 200
    out = r.json()
    assert out["bars"] == 300


# ---------------- Data hydration ----------------


def test_data_endpoint_returns_columns(client):
    raw = pd.DataFrame(
        {
            "Open": [1.0, 2, 3], "High": [1.0, 2, 3], "Low": [1.0, 2, 3],
            "Close": [1.0, 2, 3], "Adj Close": [1.0, 2, 3], "Volume": [10, 20, 30],
        },
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )
    from quant_radar.sources import yfinance_src

    with patch.object(yfinance_src.yf, "download", return_value=raw):
        r = client.get(
            "/api/data",
            params={"source": "yfinance", "kind": "ohlcv", "name": "AAPL"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "yfinance"
    assert len(body["timestamps"]) == 3
    assert "close" in body["columns"]
    assert body["columns"]["close"] == [1.0, 2.0, 3.0]


def test_data_endpoint_unsupported_ref_returns_400(client):
    r = client.get(
        "/api/data",
        params={"source": "bogus", "kind": "ohlcv", "name": "X"},
    )
    assert r.status_code == 400
