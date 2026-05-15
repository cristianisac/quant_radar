"""Exhaustive E2E — every tool, every source, every card type.

Goes deeper than e2e_demo.py: exercises non-default code paths,
edge cases (short series, missing IDs, frequency variance in FRED,
non-equity yfinance assets, multi-DataRef cards, all update_card field
combinations, etc.). Run in Docker against real APIs.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

import pandas as pd

from quant_radar import tools
from quant_radar.cards import store
from quant_radar.sources import binance_src, fred_src, yfinance_src

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


# ============================================================
# A. INTROSPECTION
# ============================================================
step("A. INTROSPECTION — list / describe / probe_history")

try:
    src_list = tools.list_sources()
    names = {s["name"] for s in src_list}
    note(f"list_sources → {sorted(names)}")
    expect(
        {"yfinance", "binance", "fred", "gdelt", "finnhub", "coinpaprika"} <= names,
        "all six known sources present",
        "A.list_sources_completeness",
    )

    binance_cap = tools.describe_source("binance")
    expect(binance_cap is not None and "1d" in binance_cap["intervals"], "binance has 1d interval", "A.describe_binance")

    expect(tools.describe_source("nope") is None, "describe_source returns None for unknown", "A.describe_unknown")

    # probe across three different code paths
    btc_probe = tools.probe_history("BTC", source="binance", kind="ohlcv")
    note(f"probe BTC binance: first={btc_probe.get('first')}, bars={btc_probe.get('bars')}")
    expect(btc_probe["bars"] > 250, "BTC has long history", "A.probe_btc_history")

    aapl_probe = tools.probe_history("AAPL", source="yfinance", kind="ohlcv")
    note(f"probe AAPL yfinance: first={aapl_probe.get('first')}, bars={aapl_probe.get('bars')}")
    expect(aapl_probe["bars"] > 250, "AAPL has long history", "A.probe_aapl_history")

    dgs10_probe = tools.probe_history("DGS10", source="fred", kind="macro")
    note(f"probe DGS10 fred: first={dgs10_probe.get('first')}, bars={dgs10_probe.get('bars')}")
    expect(dgs10_probe["bars"] > 250, "DGS10 has long history", "A.probe_dgs10_history")
except Exception as e:
    fail("A.introspection", e)


# ============================================================
# B. YFINANCE — assets across asset classes
# ============================================================
step("B. YFINANCE — stocks, ETFs, indices, FX, crypto-USD")

for sym, asset_class in [("AAPL", "stock"), ("SPY", "ETF"), ("^GSPC", "index"),
                         ("EURUSD=X", "FX"), ("BTC-USD", "crypto-USD")]:
    try:
        df = yfinance_src.fetch_ohlcv(sym, interval="1d")
        last = float(df["close"].iloc[-1])
        note(f"{sym:10s} ({asset_class:9s}): {len(df):4d} bars, last close = {last:,.4f}")
        expect(len(df) > 200, f"{sym} has ≥200 bars", f"B.{sym}_bars")
        expect(last > 0, f"{sym} last close is positive", f"B.{sym}_positive")
    except Exception as e:
        fail(f"B.{sym}", e)


# ============================================================
# C. BINANCE — various intervals + symbols
# ============================================================
step("C. BINANCE — intervals + symbol normalization")

# Test bare vs preformed symbol normalization
for sym in ["BTC", "ETH", "BTCUSDT", "SOL"]:
    try:
        normalized = binance_src.to_binance_symbol(sym)
        note(f"normalize {sym!r} → {normalized!r}")
    except Exception as e:
        fail(f"C.normalize_{sym}", e)

# Daily for SOL
try:
    sol = binance_src.fetch_ohlcv("SOL", interval="1d")
    note(f"SOL/USDT 1d: {len(sol)} bars, last = {sol['close'].iloc[-1]:,.2f}")
    expect(len(sol) > 250, "SOL has long daily history", "C.sol_daily")
except Exception as e:
    fail("C.sol_daily", e)

# Weekly for BTC
try:
    btc_w = binance_src.fetch_ohlcv("BTC", interval="1w")
    note(f"BTC/USDT 1w: {len(btc_w)} bars")
    expect(len(btc_w) >= 52, "BTC has ≥1y of weekly bars", "C.btc_weekly")
except Exception as e:
    fail("C.btc_weekly", e)

# Hourly fetch (smaller window)
try:
    btc_1h = binance_src.fetch_ohlcv("BTC", interval="1h")
    note(f"BTC/USDT 1h: {len(btc_1h)} bars")
    expect(len(btc_1h) > 100, "BTC has plenty of hourly bars", "C.btc_hourly")
except Exception as e:
    fail("C.btc_hourly", e)

# Unsupported interval
try:
    binance_src.fetch_ohlcv("BTC", interval="bogus")
    failures.append("C.bad_interval")
    print("    ✗ C.bad_interval: should have raised")
except ValueError:
    ok("unsupported interval correctly raised ValueError")


# ============================================================
# D. FRED — native frequencies
# ============================================================
step("D. FRED — daily, monthly, quarterly frequencies")

for series, expected_freq in [
    ("DGS10", "daily"),
    ("CPIAUCSL", "monthly"),
    ("GDP", "quarterly"),
    ("UNRATE", "monthly"),
    ("DEXUSEU", "daily"),
]:
    try:
        df = fred_src.fetch_macro_series(series)
        span_days = (df.index[-1] - df.index[0]).days
        avg_spacing = span_days / max(len(df) - 1, 1)
        actual_freq = (
            "daily" if avg_spacing < 5
            else "weekly" if avg_spacing < 10
            else "monthly" if avg_spacing < 35
            else "quarterly" if avg_spacing < 100
            else "annual"
        )
        note(
            f"{series:10s} expected={expected_freq:9s} actual={actual_freq:9s} "
            f"bars={len(df):5d} last={df['value'].iloc[-1]}"
        )
        expect(
            actual_freq == expected_freq,
            f"{series} native frequency matches expectation",
            f"D.{series}_freq",
        )
    except Exception as e:
        fail(f"D.{series}", e)


# ============================================================
# E. ANALYTICS — every indicator, both regimes, returns
# ============================================================
step("E. ANALYTICS — indicators / returns / MA / regime")

try:
    btc = binance_src.fetch_ohlcv("BTC", interval="1d")

    # compute_indicators with all known indicators
    enriched = tools.compute_indicators(
        btc, indicators=("sma_50", "sma_200", "ema_12", "ema_26", "rsi", "atr", "macd"),
    )
    expected_cols = {"sma_50", "sma_200", "ema_12", "ema_26", "rsi", "atr",
                     "macd", "macd_signal", "macd_hist"}
    have = set(enriched.columns)
    missing = expected_cols - have
    expect(not missing, f"all expected indicator cols present (missing: {missing})", "E.indicator_cols")
    expect(
        not pd.isna(enriched["sma_200"].iloc[-1]),
        "SMA_200 last value is non-NaN (history was enough)",
        "E.sma200_value",
    )

    # compute_returns
    rets = tools.compute_returns(btc, periods=("1d", "1w", "1m", "1y", "yoy", "ytd"))
    note(f"BTC returns: {rets}")
    expect(all(v is not None for v in rets.values()), "all return periods computed", "E.returns_all")
    expect(rets["1y"] == rets["yoy"], "1y == yoy", "E.returns_yoy_alias")

    # analyze_moving_averages default
    ma = tools.analyze_moving_averages(btc, asset="BTC")
    note(f"MA summary: {ma['summary']}")
    expect(not ma["insufficient_data"], "MA analysis has enough data", "E.ma_sufficient")

    # analyze_moving_averages non-default periods
    ma_short = tools.analyze_moving_averages(btc, fast_period=20, slow_period=50, asset="BTC")
    note(f"BTC 20/50 MA: price_vs_fast={ma_short['price_vs_fast']}, fast_vs_slow={ma_short['fast_vs_slow']}")
    expect(ma_short["fast_period"] == 20 and ma_short["slow_period"] == 50, "non-default periods honored", "E.ma_periods")

    # analyze_indicators (RSI state + vol regime)
    states = tools.analyze_indicators(btc)
    note(f"BTC analyze_indicators: {states}")
    expect(
        states["rsi_state"] in {"overbought", "oversold", "neutral", "unknown"},
        "rsi_state is a valid label",
        "E.rsi_state",
    )
    expect(
        states["volatility_regime"] in {"high", "elevated", "normal", "low", "unknown"},
        "vol regime is a valid label",
        "E.vol_regime",
    )

    # Short-series edge case: returns should return None for too-far periods
    short = btc.iloc[-5:]
    short_rets = tools.compute_returns(short, periods=("1d", "1m", "1y"))
    note(f"short-series returns: {short_rets}")
    expect(short_rets["1m"] is None and short_rets["1y"] is None, "insufficient history → None", "E.short_returns")

    # analyze_moving_averages on short series
    short_ma = tools.analyze_moving_averages(short, asset="short")
    expect(short_ma["insufficient_data"], "short series → insufficient_data flag", "E.short_ma")
except Exception as e:
    fail("E.analytics", e)


# ============================================================
# F. PATTERN DETECTION — channels, breakouts, vision
# ============================================================
step("F. PATTERN DETECTION — algo + vision")

try:
    eth = yfinance_src.fetch_ohlcv("ETH-USD", interval="1d")

    # Default channel detection
    ch = tools.detect_channels(eth)
    note(f"ETH channel: found={ch['found']}, conf={ch['confidence']:.3f}, dir={ch['direction']}")

    # Breakout with explicit channel
    br_explicit = tools.detect_breakouts(eth, channel=ch)
    note(f"breakout (with channel): found={br_explicit['found']}")

    # Breakout auto-detecting channel internally
    br_auto = tools.detect_breakouts(eth)
    note(f"breakout (auto): found={br_auto['found']}")
    expect(
        br_explicit["found"] == br_auto["found"],
        "explicit-channel vs auto give same breakout verdict",
        "F.breakout_consistency",
    )

    # Channel annotations roundtrip
    if ch["found"]:
        anns = tools.channel_annotations(eth, ch)
        expect(anns is not None and len(anns) == 2, "channel_annotations returns 2 trendlines", "F.channel_anns")
    else:
        note("channel not found → channel_annotations not applicable")

    # Tighter threshold rejects most channels
    tighter = tools.detect_channels(eth, confidence_threshold=0.99, min_r2=0.99)
    expect(not tighter["found"], "absurdly tight thresholds reject", "F.tight_thresholds")

    # Vision PNG
    v = tools.detect_patterns_vision(eth, asset_name="ETH-USD")
    note(f"vision image: {v['image_path']}")
    p = Path(v["image_path"])
    expect(p.exists() and p.stat().st_size > 10_000, "PNG written and substantial", "F.vision_png")
except Exception as e:
    fail("F.patterns", e)


# ============================================================
# G. CARD CRUD — every type, every operation
# ============================================================
step("G. CARDS — create / update / save / remove / annotate for each type")

card_ids: dict[str, str] = {}

# Reset working dashboard for a clean slate
tools.new_working_dashboard()

try:
    # Chart card
    c_chart = tools.create_dashboard_card(
        type="chart",
        title="BTC chart card",
        data_refs=[{"source": "binance", "kind": "ohlcv", "name": "BTCUSDT"}],
        chart_spec={"overlays": ["sma_50"]},
    )
    card_ids["chart"] = c_chart["id"]

    # Analysis card
    c_an = tools.create_dashboard_card(
        type="analysis",
        title="BTC analysis",
        analysis_markdown="## BTC\n\nSome thoughts here.",
    )
    card_ids["analysis"] = c_an["id"]

    # News card
    c_news = tools.create_dashboard_card(
        type="news",
        title="News test",
        news=[{"title": "test headline", "url": "https://example.com", "source": "test", "published_at": "2026-05-15T12:00:00Z"}],
    )
    card_ids["news"] = c_news["id"]

    # Sentiment card
    c_sent = tools.create_dashboard_card(
        type="sentiment",
        title="Sentiment test",
        analysis_markdown="Overall bullish on AI.",
    )
    card_ids["sentiment"] = c_sent["id"]

    # Combo card with two data_refs
    c_combo = tools.create_dashboard_card(
        type="combo",
        title="DGS10 + BTC",
        data_refs=[
            {"source": "fred", "kind": "macro", "name": "DGS10"},
            {"source": "binance", "kind": "ohlcv", "name": "BTC"},
        ],
        chart_spec={},
    )
    card_ids["combo"] = c_combo["id"]

    ok("created 5 cards (one of each type), ids stored")
    working_after_create = tools.load_dashboard("working")
    expect(
        sum(1 for c in working_after_create if c["id"] in card_ids.values()) == 5,
        "our 5 cards are in working",
        "G.create_count",
    )

    # Update each card's title only
    for t, cid in card_ids.items():
        u = tools.update_card(cid, title=f"updated {t}")
        expect(u is not None and u["title"] == f"updated {t}", f"updated {t} title", f"G.update_title_{t}")

    # Update analysis_markdown on the analysis card without touching other fields
    a_before = next(c for c in tools.load_dashboard("working") if c["id"] == card_ids["analysis"])
    u = tools.update_card(card_ids["analysis"], analysis_markdown="**updated body**")
    expect(
        u is not None and u["analysis_markdown"] == "**updated body**" and u["title"] == a_before["title"],
        "analysis update preserves title",
        "G.update_partial",
    )

    # Add annotation to the chart card (via channel_annotations)
    eth_df = yfinance_src.fetch_ohlcv("ETH-USD", interval="1d")
    eth_channel = tools.detect_channels(eth_df)
    if eth_channel["found"]:
        anns = tools.channel_annotations(eth_df, eth_channel)
        for ann in anns:
            tools.add_annotation(card_ids["chart"], ann)
        card = store.working_get(card_ids["chart"])
        expect(
            card is not None and card.chart_spec is not None and len(card.chart_spec.annotations) == 2,
            "two trendline annotations persisted",
            "G.annotations_persisted",
        )

    # Update returning None for nonexistent
    expect(
        tools.update_card("00000000-0000-0000-0000-000000000000") is None,
        "update_card returns None for missing id",
        "G.update_missing",
    )

    # save_card_to_dashboard for each
    main_before = len(tools.load_dashboard("main"))
    for t, cid in card_ids.items():
        ok_save = tools.save_card_to_dashboard(cid)
        expect(ok_save, f"saved {t} to main", f"G.save_{t}")
    main_after_save = len(tools.load_dashboard("main"))
    expect(
        main_after_save == main_before + 5,
        f"main grew by exactly 5 (from {main_before} to {main_after_save})",
        "G.main_count",
    )

    # Remove one from working (delta-based to be re-run-safe)
    working_before_rm = len(tools.load_dashboard("working"))
    tools.remove_card(card_ids["news"])
    expect(
        len(tools.load_dashboard("working")) == working_before_rm - 1,
        "working count drops by 1 after remove",
        "G.remove_working",
    )

    # Remove one from main (delta-based)
    main_before_rm = len(tools.load_dashboard("main"))
    tools.remove_card(card_ids["sentiment"], target="main")
    expect(
        len(tools.load_dashboard("main")) == main_before_rm - 1,
        "main count drops by 1 after remove",
        "G.remove_main",
    )

    # remove nonexistent
    expect(
        not tools.remove_card("00000000-0000-0000-0000-000000000000"),
        "remove_card returns False for missing id",
        "G.remove_missing",
    )

    # persist_dashboard
    expect(
        tools.persist_dashboard("working") == 4,
        "persist_dashboard returns count",
        "G.persist_count",
    )

    # Working session lifecycle
    expect(store.working_is_open(), "working open after create", "G.working_open")
    tools.close_working_dashboard()
    expect(not store.working_is_open(), "working closed after close call", "G.working_close")
    tools.new_working_dashboard()
    expect(
        store.working_is_open() and len(tools.load_dashboard("working")) == 0,
        "new working is empty + open",
        "G.working_reopen",
    )
except Exception as e:
    fail("G.cards", e)


# ============================================================
# H. NEWS — GDELT only (Finnhub key not assumed)
# ============================================================
step("H. NEWS — GDELT fetch + summarize/score shape")

# GDELT is documented as opportunistic-only — flakiness here is a warn,
# not a fail. The summarize/score shape checks don't depend on the fetch.
items: list[dict] = []
try:
    items = tools.fetch_news("Bitcoin AND Ethereum", source="gdelt", max_items=10)
    note(f"GDELT items: {len(items)}")
    if items:
        ok(f"GDELT returned {len(items)} items")
        for it in items[:3]:
            note(f"  - {(it.get('title') or '')[:80]} ({it.get('source')})")
    else:
        warn("GDELT returned 0 items (recoverable; query-quality issue)")
except Exception as e:  # noqa: BLE001
    warn(f"GDELT fetch_news failed (expected — opportunistic): {type(e).__name__}")

try:
    top = tools.fetch_top_headlines(source="gdelt", max_items=5)
    note(f"top headlines: {len(top)} items")
except Exception as e:  # noqa: BLE001
    warn(f"GDELT fetch_top_headlines failed (expected — opportunistic): {type(e).__name__}")

# Shape checks for the LLM-first payloads — independent of fetch success.
try:
    sum_p = tools.summarize_news(items)
    expect(
        sum_p["items_count"] == len(items) and "instructions" in sum_p,
        "summarize_news shape correct",
        "H.summarize_shape",
    )

    sent_p = tools.score_sentiment(items, topic="crypto")
    expect(
        sent_p["topic"] == "crypto" and "instructions" in sent_p,
        "score_sentiment shape correct",
        "H.sentiment_shape",
    )

    empty_sum = tools.summarize_news([])
    expect(
        empty_sum["items_count"] == 0,
        "summarize_news([]) returns count=0",
        "H.empty_summarize",
    )
except Exception as e:
    fail("H.payload_shapes", e)


# ============================================================
# I. SANITY — multi-source comparison via combo card
# ============================================================
step("I. MULTI-SOURCE COMPARISON — US 10y vs BTC on one card (Phase 4 hydrate)")

try:
    from quant_radar.cards.spec import DataRef
    from quant_radar.ui.data import hydrate

    dgs10_df = hydrate(DataRef(source="fred", kind="macro", name="DGS10"))
    btc_df = hydrate(DataRef(source="binance", kind="ohlcv", name="BTCUSDT"))
    note(f"DGS10 hydrated: {len(dgs10_df)} obs, last = {dgs10_df['value'].iloc[-1]:.2f}%")
    note(f"BTCUSDT hydrated: {len(btc_df)} bars, last = {btc_df['close'].iloc[-1]:,.2f}")
    expect(len(dgs10_df) > 1000 and len(btc_df) > 1000, "both sources long-history", "I.hydrate_both")
except Exception as e:
    fail("I.multi_source", e)


# ============================================================
print("\n" + "=" * 76)
print(f"  FAILURES: {len(failures)}")
print(f"  WARNINGS: {len(warnings)}")
if failures:
    for f in failures:
        print(f"    ✗ {f}")
if warnings:
    for w in warnings[:5]:
        print(f"    ⚠ {w}")
print("=" * 76)
sys.exit(1 if failures else 0)
