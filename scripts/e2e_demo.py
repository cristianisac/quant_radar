"""End-to-end smoke run of the full quant_radar surface against real APIs.

Simulates every example query from the user's original spec. Tools are
called the way a Claude Code session would call them. The script does
not interpret news/sentiment items (that's the LLM's job in a real
session) — it just verifies the tools produce well-shaped payloads.

Run inside Docker:
    docker run --rm --read-only --tmpfs /tmp ... \\
        -v /tmp/quant_radar_data:/app/data \\
        quant-radar:dev python /app/scripts/e2e_demo.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from quant_radar import tools
from quant_radar.cards import store
from quant_radar.sources import binance_src, fred_src, yfinance_src

failures: list[str] = []


def step(n: int, title: str) -> None:
    print(f"\n{'=' * 72}\n  STEP {n}: {title}\n{'=' * 72}")


def note(msg: str) -> None:
    print(f"    · {msg}")


def ok(msg: str) -> None:
    print(f"    ✓ {msg}")


def warn(msg: str) -> None:
    print(f"    ⚠ {msg}")


def fail(label: str, e: Exception) -> None:
    failures.append(label)
    print(f"    ✗ {label}: {type(e).__name__}: {e}")
    traceback.print_exc(limit=2)


def fmt_pct(v: float | None) -> str:
    return f"{v * 100:+.2f}%" if v is not None else "—"


def fmt_float(v: float | None, digits: int = 3) -> str:
    return f"{v:.{digits}f}" if v is not None else "—"


# ============================================================
# STEP 1: Show me BTC with the 50d and 200d moving averages
# ============================================================
step(1, "Show me BTC with the 50d and 200d moving averages")
try:
    btc = yfinance_src.fetch_ohlcv("BTC-USD", interval="1d")
    note(f"fetched {len(btc)} bars, columns={list(btc.columns)}")
    note(f"date range: {btc.index[0].date()} → {btc.index[-1].date()}")
    note(f"last close ≈ {btc['close'].iloc[-1]:,.2f}")
    assert len(btc) >= 200, "need ≥200 bars for sma_200"
    assert (btc["close"] > 0).all(), "negative or zero prices?!"

    ma = tools.analyze_moving_averages(btc, asset="BTC-USD")
    note(f"summary: {ma['summary']}")
    note(f"  price vs 50d: {ma['price_vs_fast']}, vs 200d: {ma['price_vs_slow']}")
    note(f"  50d vs 200d: {ma['fast_vs_slow']}")
    note(f"  catching up: {ma['fast_catching_up_from_below']}")
    note(f"  golden/death cross recent: {ma['golden_cross_recent']}/{ma['death_cross_recent']}")
    assert ma["last_close"] == btc["close"].iloc[-1], "MA's last_close drift"

    card1 = tools.create_dashboard_card(
        type="chart",
        title="BTC with 50d/200d MAs",
        data_refs=[{"source": "yfinance", "kind": "ohlcv", "name": "BTC-USD"}],
        chart_spec={"overlays": ["sma_50", "sma_200"]},
    )
    ok(f"card created id={card1['id'][:8]}")
except Exception as e:
    fail("step 1", e)
    card1 = None

# ============================================================
# STEP 2: Plot ETH with detected channels — skip if none
# ============================================================
step(2, "Plot ETH with any detected channels — don't draw if none found")
try:
    eth = yfinance_src.fetch_ohlcv("ETH-USD", interval="1d")
    note(f"fetched {len(eth)} bars, last close ≈ {eth['close'].iloc[-1]:,.2f}")
    ch = tools.detect_channels(eth, lookback=60)
    note(f"found={ch['found']}, confidence={fmt_float(ch['confidence'])}")
    note(f"  direction={ch['direction']}, touches U/L={ch['touches_upper']}/{ch['touches_lower']}")
    note(f"  r2 U/L={fmt_float(ch['r2_upper'])}/{fmt_float(ch['r2_lower'])}")
    note(f"  parallel={fmt_float(ch['parallel_score'])}, reason={ch['reason']}")
    if ch["found"]:
        anns = tools.channel_annotations(eth, ch)
        card2 = tools.create_dashboard_card(
            type="chart",
            title=f"ETH with detected {ch['direction']} channel",
            data_refs=[{"source": "yfinance", "kind": "ohlcv", "name": "ETH-USD"}],
            chart_spec={"annotations": anns},
        )
        ok(f"channel met threshold → card with 2 trendlines: {card2['id'][:8]}")
    else:
        ok(f"channel below threshold ({fmt_float(ch['confidence'])}) → no draw (correct)")
except Exception as e:
    fail("step 2", e)

# ============================================================
# STEP 3: Show me NVDA with year-over-year change as a subplot
# ============================================================
step(3, "Show me NVDA with year-over-year change as a subplot")
try:
    nvda = yfinance_src.fetch_ohlcv("NVDA", interval="1d")
    note(f"fetched {len(nvda)} bars, last close ≈ {nvda['close'].iloc[-1]:,.2f}")
    rets = tools.compute_returns(nvda, periods=("1d", "1w", "1m", "1y", "yoy", "ytd"))
    for p, v in rets.items():
        note(f"  {p}: {fmt_pct(v)}")
    assert rets["1y"] == rets["yoy"], "1y and yoy should be identical"
    card3 = tools.create_dashboard_card(
        type="chart",
        title="NVDA with YoY subplot",
        data_refs=[{"source": "yfinance", "kind": "ohlcv", "name": "NVDA"}],
        chart_spec={"subplots": ["yoy"]},
    )
    ok(f"card created: {card3['id'][:8]}")
except Exception as e:
    fail("step 3", e)

# ============================================================
# STEP 4: Is SOL breaking out of a channel?
# ============================================================
step(4, "Is SOL breaking out of a channel?")
try:
    sol = binance_src.fetch_ohlcv("SOL")  # → SOLUSDT
    note(f"fetched {len(sol)} bars from Binance, last close ≈ {sol['close'].iloc[-1]:,.2f}")
    ch_sol = tools.detect_channels(sol, lookback=60)
    note(f"channel: found={ch_sol['found']}, confidence={fmt_float(ch_sol['confidence'])}")
    br = tools.detect_breakouts(sol, channel=ch_sol)
    note(f"breakout: found={br['found']}, direction={br.get('direction')}")
    if br["found"]:
        ok(
            f"SOL breaking out {br['direction']} "
            f"(close={br['close']:.2f}, boundary={br['boundary']:.2f}, margin={br['margin']:.2f})"
        )
    elif ch_sol["found"]:
        lower = br.get("lower", 0)
        upper = br.get("upper", 0)
        note(f"within channel: close vs (lower={lower:.2f}, upper={upper:.2f})")
        ok("no breakout, channel intact (correct)")
    else:
        ok("no high-confidence channel to break out of (correct)")
except Exception as e:
    fail("step 4", e)

# ============================================================
# STEP 5: Pull US 10y yield and compare with BTC
# ============================================================
step(5, "Pull US 10y yield and compare with BTC")
try:
    dgs10 = fred_src.fetch_macro_series("DGS10")
    note(f"DGS10 fetched: {len(dgs10)} bars, last value = {dgs10['value'].iloc[-1]:.2f}%")
    note(f"  date range: {dgs10.index[0].date()} → {dgs10.index[-1].date()}")
    assert 0 < dgs10["value"].iloc[-1] < 30, "10y yield outside sane range"
    card5 = tools.create_dashboard_card(
        type="combo",
        title="US 10y yield vs BTC",
        data_refs=[
            {"source": "fred", "kind": "macro", "name": "DGS10"},
            {"source": "yfinance", "kind": "ohlcv", "name": "BTC-USD"},
        ],
        chart_spec={},
    )
    ok(f"combo card created with 2 data_refs: {card5['id'][:8]}")
except Exception as e:
    fail("step 5", e)

# ============================================================
# STEP 6: Latest news and sentiment around AI stocks
# ============================================================
step(6, "Show me latest news and sentiment around AI stocks")
try:
    items = tools.fetch_news(
        "AI stocks OR artificial intelligence stocks",
        source="gdelt",
        max_items=10,
    )
    note(f"fetched {len(items)} news items via GDELT")
    for it in items[:5]:
        t = (it.get("title") or "")[:80]
        s = it.get("source", "?")
        note(f"  - {t} ({s})")
    sum_payload = tools.summarize_news(items)
    note(
        f"summarize_news → items_count={sum_payload['items_count']}, "
        f"instructions len={len(sum_payload['instructions'])}"
    )
    sent_payload = tools.score_sentiment(items, topic="AI stocks")
    note(
        f"score_sentiment → topic={sent_payload['topic']!r}, "
        f"items_count={sent_payload['items_count']}"
    )
    if items:
        card6 = tools.create_dashboard_card(
            type="news",
            title="AI stocks — latest news",
            news=items,
        )
        ok(f"news card created: {card6['id'][:8]} ({len(items)} items)")
    else:
        warn("no news returned — GDELT might be slow or query unmatched")
except Exception as e:
    fail("step 6", e)

# ============================================================
# STEP 7: Add RSI and ATR to this chart (update existing card)
# ============================================================
step(7, "Add RSI and ATR to this chart (update_card on the BTC card)")
try:
    if card1 is None:
        warn("STEP 1 BTC card not available — skipping")
    else:
        updated = tools.update_card(
            card1["id"],
            chart_spec={"overlays": ["sma_50", "sma_200"], "subplots": ["rsi", "atr"]},
        )
        if updated is None:
            fail("step 7", RuntimeError("update_card returned None"))
        else:
            note(f"id stable: {updated['id'] == card1['id']}")
            note(f"subplots now: {updated['chart_spec']['subplots']}")
            assert updated["id"] == card1["id"], "card id should not change on update"
            assert updated["chart_spec"]["subplots"] == ["rsi", "atr"]
            ok("card mutated in place")
except Exception as e:
    fail("step 7", e)

# ============================================================
# STEP 8: Save this card to my main dashboard
# ============================================================
step(8, "Save the BTC card to main")
try:
    if card1 is not None:
        main_before = len(tools.load_dashboard("main"))
        saved = tools.save_card_to_dashboard(card1["id"])
        main_after = len(tools.load_dashboard("main"))
        note(f"saved={saved}, main count {main_before} → {main_after}")
        assert saved is True, "should have promoted the working card"
        ok("BTC card now persists in main")
except Exception as e:
    fail("step 8", e)

# ============================================================
# STEP 9: Create a temporary working dashboard
# ============================================================
step(9, "Create a temporary working dashboard (reset + open)")
try:
    before = len(tools.load_dashboard("working"))
    tools.new_working_dashboard()
    after = len(tools.load_dashboard("working"))
    note(f"working: {before} → {after} cards")
    assert after == 0, "working should be empty after new_working_dashboard"
    assert store.working_is_open(), "Working tab should now be visible"
    ok("working dashboard re-opened (empty, tab visible)")
except Exception as e:
    fail("step 9", e)

# ============================================================
# STEP 10: 50d catching up to 200d screen across symbols
# ============================================================
step(10, "Screen: assets where 50d MA is catching up to 200d")
try:
    candidates = ["AAPL", "MSFT", "META", "TSLA", "NVDA"]
    catching_up: list[str] = []
    for sym in candidates:
        try:
            df = yfinance_src.fetch_ohlcv(sym, interval="1d")
            m = tools.analyze_moving_averages(df, asset=sym)
            if m["insufficient_data"]:
                note(f"  {sym}: insufficient data")
                continue
            cat = m["fast_catching_up_from_below"]
            note(
                f"  {sym}: catching_up={cat} "
                f"(fast={m['last_fast']:.2f}, slow={m['last_slow']:.2f}, "
                f"fast_slope={fmt_float(m['fast_slope'])}, slow_slope={fmt_float(m['slow_slope'])})"
            )
            if cat:
                catching_up.append(sym)
        except Exception as inner:
            warn(f"  {sym}: {type(inner).__name__}: {inner}")
    ok(f"catching up: {catching_up or '(none in sample)'}")
except Exception as e:
    fail("step 10", e)

# ============================================================
# STEP 11: Vision pattern detection
# ============================================================
step(11, "Vision: render PNG for ETH and hand off to agent's Read tool")
try:
    v = tools.detect_patterns_vision(eth, asset_name="ETH-USD", title="ETH-USD daily")
    note(f"image_path = {v['image_path']}")
    note(f"confidence_threshold = {v['confidence_threshold']}")
    path = Path(v["image_path"])
    if path.exists():
        size = path.stat().st_size
        ok(f"PNG written, size = {size:,} bytes")
        assert size > 5_000, "PNG suspiciously small"
    else:
        fail("step 11", FileNotFoundError(str(path)))
except Exception as e:
    fail("step 11", e)

# ============================================================
# STEP 12: Close the working dashboard
# ============================================================
step(12, "Close the working dashboard (Working tab disappears)")
try:
    tools.close_working_dashboard()
    open_now = store.working_is_open()
    note(f"working_is_open = {open_now} (expected False)")
    assert open_now is False, "working_is_open should be False after close"
    ok("working dashboard closed cleanly")
except Exception as e:
    fail("step 12", e)

# ============================================================
print("\n" + "=" * 72)
if failures:
    print(f"  E2E COMPLETED WITH {len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
else:
    print("  E2E COMPLETED — all 12 scenarios passed sanity checks")
print("=" * 72)
