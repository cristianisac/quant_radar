"""End-to-end against the FastAPI server using TestClient (no uvicorn).

Hits every endpoint with the same live APIs (yfinance / FRED / Binance)
that ``e2e_full.py`` exercises directly. Confirms the REST layer
faithfully exposes the tool surface.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from fastapi.testclient import TestClient

from quant_radar.server import create_app

failures: list[str] = []
warnings: list[str] = []


def step(label: str) -> None:
    print(f"\n{'=' * 76}\n  {label}\n{'=' * 76}")


def note(msg: str) -> None:
    print(f"    · {msg}")


def ok(msg: str) -> None:
    print(f"    ✓ {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"    ⚠ {msg}")


def fail(label: str, e: Exception) -> None:
    failures.append(label)
    print(f"    ✗ {label}: {type(e).__name__}: {e}")
    traceback.print_exc(limit=2)


def expect(cond: bool, msg: str, label: str) -> None:
    if cond:
        ok(msg)
    else:
        failures.append(label)
        print(f"    ✗ {label}: {msg}")


client = TestClient(create_app())


# ============================================================
step("A. Health")
try:
    r = client.get("/api/health")
    note(f"health: {r.json()}")
    expect(r.status_code == 200 and r.json()["status"] == "ok", "health 200 + ok", "A.health")
except Exception as e:
    fail("A.health", e)


# ============================================================
step("B. Sources catalog (list / describe / unknown)")
try:
    r = client.get("/api/sources")
    expect(r.status_code == 200, "GET /sources 200", "B.list_sources")
    names = {s["name"] for s in r.json()}
    expect(
        {"yfinance", "binance", "fred", "gdelt", "finnhub", "coinpaprika"} <= names,
        "all known sources catalogued",
        "B.catalog_complete",
    )

    r = client.get("/api/sources/binance")
    expect(r.status_code == 200 and r.json()["name"] == "binance", "describe binance", "B.describe_known")

    r = client.get("/api/sources/nope")
    expect(r.status_code == 404, "unknown source 404", "B.describe_unknown")
except Exception as e:
    fail("B.sources", e)


# ============================================================
step("C. Probe history (live yfinance + FRED)")
try:
    r = client.get(
        "/api/probe-history",
        params={"symbol": "AAPL", "source": "yfinance", "kind": "ohlcv"},
    )
    expect(r.status_code == 200 and r.json()["bars"] > 250, "AAPL probe long history", "C.probe_aapl")
    note(f"AAPL: first={r.json().get('first')}, bars={r.json().get('bars')}")

    r = client.get(
        "/api/probe-history",
        params={"symbol": "BTC", "source": "binance", "kind": "ohlcv"},
    )
    expect(r.status_code == 200 and r.json()["bars"] > 1000, "BTC probe long history", "C.probe_btc")
    note(f"BTC: first={r.json().get('first')}, bars={r.json().get('bars')}")

    r = client.get(
        "/api/probe-history",
        params={"symbol": "DGS10", "source": "fred", "kind": "macro"},
    )
    expect(r.status_code == 200 and r.json()["bars"] > 250, "DGS10 probe long history", "C.probe_dgs10")
    note(f"DGS10: first={r.json().get('first')}, bars={r.json().get('bars')}")
except Exception as e:
    fail("C.probe", e)


# ============================================================
step("D. Data hydration (returns Plotly-ready columnar JSON)")
try:
    r = client.get(
        "/api/data",
        params={"source": "yfinance", "kind": "ohlcv", "name": "AAPL", "interval": "1d"},
    )
    expect(r.status_code == 200, "GET /data 200", "D.data_status")
    body = r.json()
    expect("timestamps" in body and "columns" in body, "columnar shape", "D.data_shape")
    expect(len(body["timestamps"]) > 250, "AAPL daily ≥250 bars", "D.aapl_bars")
    expect("close" in body["columns"], "close column present", "D.close_col")
    note(f"AAPL data: {len(body['timestamps'])} bars, columns={list(body['columns'].keys())}")
except Exception as e:
    fail("D.data", e)

try:
    r = client.get("/api/data", params={"source": "nope", "kind": "ohlcv", "name": "X"})
    expect(r.status_code == 400, "unsupported ref → 400", "D.unsupported")
except Exception as e:
    fail("D.unsupported", e)


# ============================================================
step("E. Cards CRUD (every type + lifecycle)")

# Start fresh
client.post("/api/working/new")
expect(
    client.get("/api/working/state").json()["is_open"],
    "working tab is open after new",
    "E.lifecycle_new",
)

card_ids: dict[str, str] = {}
payloads = {
    "chart": {
        "type": "chart",
        "title": "BTC chart",
        "data_refs": [{"source": "binance", "kind": "ohlcv", "name": "BTCUSDT"}],
        "chart_spec": {"overlays": ["sma_50"]},
    },
    "news": {
        "type": "news",
        "title": "headlines",
        "news": [{"title": "t", "url": "u", "source": "s", "published_at": "2026-05-16T00:00:00Z"}],
    },
    "sentiment": {"type": "sentiment", "title": "sent", "analysis_markdown": "neutral"},
    "analysis": {"type": "analysis", "title": "notes", "analysis_markdown": "## notes"},
    "combo": {
        "type": "combo", "title": "10y vs BTC",
        "data_refs": [
            {"source": "fred", "kind": "macro", "name": "DGS10"},
            {"source": "binance", "kind": "ohlcv", "name": "BTCUSDT"},
        ],
        "chart_spec": {},
    },
}

for kind, body in payloads.items():
    try:
        r = client.post("/api/cards", json=body)
        expect(r.status_code == 200, f"create {kind} card 200", f"E.create_{kind}")
        card_ids[kind] = r.json()["id"]
    except Exception as e:
        fail(f"E.create_{kind}", e)

working_after = client.get("/api/cards/working").json()
expect(
    sum(1 for c in working_after if c["id"] in card_ids.values()) == 5,
    "all 5 cards present in working",
    "E.list_after_create",
)

# Update keeps id stable
try:
    chart_id = card_ids["chart"]
    r = client.patch(
        f"/api/cards/{chart_id}",
        params={"target": "working"},
        json={"chart_spec": {"overlays": ["sma_50", "sma_200"], "subplots": ["rsi", "atr"]}},
    )
    expect(r.status_code == 200 and r.json()["id"] == chart_id, "update id stable", "E.update_id")
    expect(r.json()["chart_spec"]["subplots"] == ["rsi", "atr"], "update applied", "E.update_applied")
except Exception as e:
    fail("E.update", e)

# Add annotation
try:
    chart_id = card_ids["chart"]
    ann = {"kind": "trendline", "points": [[1.0, 70000.0], [2.0, 75000.0]], "label": "uptrend"}
    r = client.post(
        f"/api/cards/{chart_id}/annotations",
        json={"annotation": ann, "target": "working"},
    )
    expect(r.status_code == 200 and r.json()["ok"], "annotation persisted", "E.annotation")
    reloaded = next(c for c in client.get("/api/cards/working").json() if c["id"] == chart_id)
    expect(
        len(reloaded["chart_spec"]["annotations"]) >= 1
        and reloaded["chart_spec"]["annotations"][-1]["label"] == "uptrend",
        "annotation round-trip via GET",
        "E.annotation_roundtrip",
    )
except Exception as e:
    fail("E.annotation", e)

# Save-to-main
try:
    main_before = len(client.get("/api/cards/main").json())
    for kind, cid in card_ids.items():
        r = client.post(f"/api/cards/{cid}/save-to-main")
        expect(r.status_code == 200 and r.json()["ok"], f"saved {kind} to main", f"E.save_{kind}")
    main_after = len(client.get("/api/cards/main").json())
    expect(
        main_after == main_before + 5,
        f"main grew by 5 ({main_before} → {main_after})",
        "E.main_grew",
    )
except Exception as e:
    fail("E.save", e)

# Remove from working
try:
    working_before = len(client.get("/api/cards/working").json())
    r = client.delete(f"/api/cards/{card_ids['news']}")
    expect(r.json()["ok"], "remove ok=True", "E.remove_ok")
    expect(
        len(client.get("/api/cards/working").json()) == working_before - 1,
        "working count drops by 1",
        "E.working_drop",
    )
    # remove again → False
    r = client.delete(f"/api/cards/{card_ids['news']}")
    expect(not r.json()["ok"], "double-remove ok=False", "E.double_remove")
except Exception as e:
    fail("E.remove", e)

# 404 on update
try:
    r = client.patch(
        "/api/cards/00000000-0000-0000-0000-000000000000",
        json={"title": "x"},
    )
    expect(r.status_code == 404, "missing card → 404", "E.update_missing")
except Exception as e:
    fail("E.update_missing", e)

# Close lifecycle
try:
    r = client.post("/api/working/close")
    expect(r.status_code == 204, "close 204", "E.close_204")
    expect(
        not client.get("/api/working/state").json()["is_open"],
        "working tab is closed",
        "E.closed_state",
    )
except Exception as e:
    fail("E.close", e)


# ============================================================
print("\n" + "=" * 76)
print(f"  FAILURES: {len(failures)}")
print(f"  WARNINGS: {len(warnings)}")
for f in failures:
    print(f"    ✗ {f}")
for w in warnings:
    print(f"    ⚠ {w}")
print("=" * 76)
print(f"  CWD: {Path.cwd()}")
sys.exit(1 if failures else 0)
