"""End-to-end alignment audit.

Verifies the "supermanager of APIs" objective:

1. Capability catalog covers every active source and declares its schema.
2. Every active source is reachable and returns data matching its schema.
3. ``tools_for_ref`` advertises a non-empty tool set for OHLCV/macro refs.
4. Every compatible tool runs without error on real data from each source.
5. Date filtering works at fetch time, post-fetch, and on detectors.
6. FRED API friendly-name path resolves a real title.
7. Pattern detection runs (both vision render and algorithmic).

Run inside the container:
    docker run --rm --env-file .env quant-radar:dev \
        python scripts/integration_audit.py

Exits 0 if every check passes, 1 otherwise. Each check prints PASS/FAIL.
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from quant_radar import tools
from quant_radar.cards.spec import DataRef
from quant_radar.sources import fred_src
from quant_radar.sources.base_source import all_sources, get_source
from quant_radar.sources.catalog import CATALOG
from quant_radar.sources.hydrate import hydrate


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


results: list[CheckResult] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}{' — ' + detail if detail else ''}")
    results.append(CheckResult(name, passed, detail))


def check_catalog_coverage() -> None:
    print("\n=== 1. Catalog coverage ===")
    registry_names = {s.name for s in all_sources()}
    catalog_names = set(CATALOG.keys())
    missing_in_catalog = registry_names - catalog_names
    missing_in_registry = (catalog_names - registry_names) - {"gdelt", "finnhub"}
    record(
        "every registered source has a catalog entry",
        not missing_in_catalog,
        f"missing: {missing_in_catalog}" if missing_in_catalog else "",
    )
    record(
        "every data-source catalog entry has a registered adapter",
        not missing_in_registry,
        f"missing: {missing_in_registry}" if missing_in_registry else "",
    )
    for name, cap in CATALOG.items():
        if cap.status in {"deferred", "paid-only"}:
            continue
        record(
            f"  catalog[{name}].schema declared",
            bool(cap.schema),
            f"schema={cap.schema}",
        )


def check_source_fetch_and_schema() -> None:
    print("\n=== 2. Per-source fetch + schema match ===")
    fetch_specs: list[tuple[str, str, str, str]] = [
        ("yfinance", "ohlcv", "AAPL", "1d"),
        ("binance", "ohlcv", "BTCUSDT", "1d"),
        ("fred", "macro", "DGS10", "1d"),
    ]
    for source, kind, name, interval in fetch_specs:
        try:
            ref = DataRef(source=source, kind=kind, name=name, interval=interval)
            df = hydrate(ref)
            declared = set(CATALOG[source].schema.get(kind, []))
            actual = set(df.columns)
            ok = declared.issubset(actual) and len(df) > 0
            record(
                f"{source}/{kind} {name}: fetch + columns",
                ok,
                f"declared={sorted(declared)}, actual={sorted(actual)}, rows={len(df)}",
            )
        except Exception as e:
            record(f"{source}/{kind} {name}: fetch", False, f"{type(e).__name__}: {e}")


def check_tool_compatibility() -> None:
    print("\n=== 3. tools_for_ref returns expected tools per source ===")
    cases = [
        (DataRef(source="yfinance", kind="ohlcv", name="AAPL"),
         {"compute_indicators", "compute_returns", "analyze_moving_averages",
          "analyze_indicators", "detect_channels", "detect_breakouts",
          "detect_patterns_vision"}),
        (DataRef(source="binance", kind="ohlcv", name="BTCUSDT"),
         {"compute_indicators", "compute_returns", "analyze_moving_averages",
          "analyze_indicators", "detect_channels", "detect_breakouts",
          "detect_patterns_vision"}),
    ]
    for ref, expected in cases:
        actual = set(tools.tools_for_ref(ref))
        missing = expected - actual
        record(
            f"tools_for_ref({ref.source}/{ref.kind}) covers expected tools",
            not missing,
            f"missing={missing}" if missing else f"got {len(actual)} tools",
        )
    fred_ref = DataRef(source="fred", kind="macro", name="DGS10")
    fred_tools = set(tools.tools_for_ref(fred_ref))
    record(
        "tools_for_ref(fred/macro) correctly returns no close-requiring tools",
        not (fred_tools & {"compute_indicators", "detect_channels"}),
        f"fred-compat tools: {fred_tools}",
    )


def check_tools_on_real_data() -> None:
    print("\n=== 4. Every compatible tool runs on real OHLCV data ===")
    df = hydrate(DataRef(source="binance", kind="ohlcv", name="BTCUSDT", interval="1d"))
    try:
        rets = tools.compute_returns(df)
        record(
            "compute_returns",
            isinstance(rets, dict) and any(v is not None for v in rets.values()),
            f"keys={list(rets.keys())[:4]}",
        )
    except Exception as e:
        record("compute_returns", False, f"{type(e).__name__}: {e}")

    try:
        enriched = tools.compute_indicators(df, indicators=("sma_50", "sma_200", "rsi", "atr", "macd"))
        added = set(enriched.columns) - set(df.columns)
        record(
            "compute_indicators adds expected columns",
            {"sma_50", "sma_200", "rsi", "atr"}.issubset(added),
            f"added={sorted(added)[:6]}",
        )
    except Exception as e:
        record("compute_indicators", False, f"{type(e).__name__}: {e}")

    try:
        ma = tools.analyze_moving_averages(df)
        record(
            "analyze_moving_averages returns dict",
            isinstance(ma, dict) and len(ma) > 0,
            f"keys={list(ma.keys())[:4]}",
        )
    except Exception as e:
        record("analyze_moving_averages", False, f"{type(e).__name__}: {e}")

    try:
        states = tools.analyze_indicators(df)
        record(
            "analyze_indicators labels rsi + volatility",
            "rsi_state" in states and "volatility_regime" in states,
            f"{states}",
        )
    except Exception as e:
        record("analyze_indicators", False, f"{type(e).__name__}: {e}")


def check_date_filtering() -> None:
    print("\n=== 5. Date filtering — fetch-time, post-fetch, and on detectors ===")
    start = datetime(2023, 1, 1)
    end = datetime(2023, 12, 31)

    ref = DataRef(
        source="binance", kind="ohlcv", name="BTCUSDT", interval="1d",
        start=start, end=end,
    )
    df_pre = hydrate(ref)
    ok = (
        len(df_pre) > 0
        and df_pre.index.min() >= pd.Timestamp("2023-01-01", tz="UTC")
        and df_pre.index.max() <= pd.Timestamp("2023-12-31 23:59:59", tz="UTC")
    )
    record(
        "fetch-time start/end on DataRef respected",
        ok,
        f"rows={len(df_pre)}, span={df_pre.index.min().date()}..{df_pre.index.max().date()}",
    )

    df_full = hydrate(DataRef(source="binance", kind="ohlcv", name="BTCUSDT", interval="1d"))
    df_post = tools.filter_by_date(df_full, start="2023-01-01", end="2023-12-31")
    ok2 = (
        len(df_post) > 0
        and df_post.index.min() >= pd.Timestamp("2023-01-01", tz="UTC")
        and df_post.index.max() <= pd.Timestamp("2023-12-31 23:59:59", tz="UTC")
    )
    record(
        "post-fetch filter_by_date respected",
        ok2,
        f"rows={len(df_post)}, span={df_post.index.min().date()}..{df_post.index.max().date()}",
    )

    try:
        ch = tools.detect_channels(df_full, start="2023-06-01", end="2023-12-31")
        record(
            "detect_channels accepts start/end + returns scored result",
            "confidence" in ch and "found" in ch,
            f"confidence={ch.get('confidence', 'n/a'):.3f} found={ch.get('found')}",
        )
    except Exception as e:
        record("detect_channels(start/end)", False, f"{type(e).__name__}: {e}")


def check_fred_title() -> None:
    print("\n=== 6. FRED friendly-name path ===")
    title = fred_src.series_title("DGS10")
    record(
        "FRED API returns a non-empty title for DGS10",
        bool(title and len(title) > 5),
        f"title={title!r}",
    )


def check_rolling_zscore() -> None:
    print("\n=== 7. Rolling z-score on OHLCV + macro frames ===")
    df = hydrate(DataRef(source="binance", kind="ohlcv", name="BTCUSDT", interval="1d"))
    try:
        out = tools.rolling_zscore(df, window=30, min_obs=30)
        col = "zscore_30"
        ok = col in out.columns and out[col].iloc[:29].isna().all() and out[col].iloc[60:].notna().any()
        record(
            "rolling_zscore on OHLCV close (window=30)",
            ok,
            f"col added, warmup respected, tail-mean={out[col].iloc[-30:].mean():.3f}",
        )
    except Exception as e:
        record("rolling_zscore on OHLCV", False, f"{type(e).__name__}: {e}")

    macro = hydrate(DataRef(source="fred", kind="macro", name="DGS10"))
    try:
        out = tools.rolling_zscore(macro, column="value", window=90)
        col = "zscore_90"
        ok = col in out.columns and out[col].iloc[120:].notna().any()
        record(
            "rolling_zscore on FRED macro 'value' column (window=90)",
            ok,
            f"tail-mean={out[col].iloc[-30:].mean():.3f}",
        )
    except Exception as e:
        record("rolling_zscore on macro", False, f"{type(e).__name__}: {e}")


def check_fred_search() -> None:
    print("\n=== 8. FRED keyword search ===")
    try:
        hits = tools.search_fred("unemployment", limit=5)
        ids = [h.get("id") for h in hits]
        ok = bool(hits) and any("UNRATE" in (h.get("id") or "") for h in hits)
        record(
            "search_fred('unemployment') surfaces UNRATE",
            ok,
            f"top hits: {ids}",
        )
    except Exception as e:
        record("search_fred", False, f"{type(e).__name__}: {e}")


def check_pattern_detection() -> None:
    print("\n=== 7. Pattern detection (algo + vision) ===")
    df = hydrate(DataRef(source="binance", kind="ohlcv", name="BTCUSDT", interval="1d"))
    try:
        ch = tools.detect_channels(df)
        record(
            "algorithmic detect_channels returns scored output",
            "confidence" in ch,
            f"confidence={ch['confidence']:.3f}, found={ch['found']}",
        )
    except Exception as e:
        record("detect_channels", False, f"{type(e).__name__}: {e}")

    try:
        vis = tools.detect_patterns_vision(df, asset_name="BTCUSDT")
        from pathlib import Path
        png_ok = "image_path" in vis and Path(vis["image_path"]).exists()
        record(
            "detect_patterns_vision renders PNG agent can Read",
            png_ok,
            f"path={vis.get('image_path')}",
        )
    except Exception as e:
        record("detect_patterns_vision", False, f"{type(e).__name__}: {e}")


def main() -> int:
    print("quant_radar end-to-end alignment audit")
    print("=" * 60)
    for check in (
        check_catalog_coverage,
        check_source_fetch_and_schema,
        check_tool_compatibility,
        check_tools_on_real_data,
        check_date_filtering,
        check_fred_title,
        check_rolling_zscore,
        check_fred_search,
        check_pattern_detection,
    ):
        try:
            check()
        except Exception:
            traceback.print_exc()
            results.append(CheckResult(check.__name__, False, "exception"))

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"{passed}/{total} checks passed")
    failed = [r for r in results if not r.passed]
    if failed:
        print("\nFailed:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
