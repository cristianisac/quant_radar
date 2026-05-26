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
    """News sources (gdelt/finnhub) intentionally don't conform to the
    time-series Source ABC — they return list[dict] articles, not DataFrames.
    Every *other* active catalog entry MUST register a Source subclass.
    """
    print("\n=== 1. Catalog coverage ===")
    NEWS_SOURCES = {"gdelt", "finnhub"}
    registry_names = {s.name for s in all_sources()}
    catalog_names = set(CATALOG.keys())
    missing_in_catalog = registry_names - catalog_names
    missing_in_registry = (catalog_names - registry_names) - NEWS_SOURCES
    record(
        "every registered source has a catalog entry",
        not missing_in_catalog,
        f"missing: {missing_in_catalog}" if missing_in_catalog else "",
    )
    record(
        "every time-series catalog entry has a registered adapter "
        "(news sources excluded by design)",
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
    """Analytical tools are column-agnostic now — they auto-pick the price
    column (close → value → only-numeric). ``tools_for_ref`` returns the
    full analytical tool set regardless of source. The agent decides
    what makes sense; we don't gate.
    """
    print("\n=== 3. Analytical tools are column-agnostic ===")
    full_set = set(tools.all_analytical_tools())
    for ref in (
        DataRef(source="yfinance", kind="ohlcv", name="AAPL"),
        DataRef(source="binance", kind="ohlcv", name="BTCUSDT"),
        DataRef(source="fred", kind="macro", name="DGS10"),
    ):
        actual = set(tools.tools_for_ref(ref))
        record(
            f"tools_for_ref({ref.source}/{ref.kind}) returns full tool set",
            actual == full_set,
            f"got {len(actual)} tools",
        )

    # Live cross-source proof: same tools run on OHLCV + macro frames.
    btc = hydrate(DataRef(source="binance", kind="ohlcv", name="BTCUSDT", interval="1d"))
    dgs = hydrate(DataRef(source="fred", kind="macro", name="DGS10"))
    try:
        rets_btc = tools.compute_returns(btc)
        rets_dgs = tools.compute_returns(dgs)
        record(
            "compute_returns works on OHLCV (close) AND macro (value) without hint",
            isinstance(rets_btc, dict) and isinstance(rets_dgs, dict)
            and any(v is not None for v in rets_btc.values())
            and any(v is not None for v in rets_dgs.values()),
            f"btc keys={list(rets_btc)[:3]}, dgs keys={list(rets_dgs)[:3]}",
        )
    except Exception as e:
        record("column-agnostic compute_returns", False, f"{type(e).__name__}: {e}")

    try:
        z_btc = tools.rolling_zscore(btc, window=30)
        z_dgs = tools.rolling_zscore(dgs, window=30)
        record(
            "rolling_zscore auto-picks close on OHLCV, value on FRED",
            "zscore_30" in z_btc.columns and "zscore_30" in z_dgs.columns,
            "",
        )
    except Exception as e:
        record("column-agnostic rolling_zscore", False, f"{type(e).__name__}: {e}")


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


def _example_for_kind(cap, kind: str) -> str | None:
    """Heuristic: pick an example from cap.examples that fits ``kind``.

    - forex: looks for a 6-letter all-uppercase ticker (EURUSD, GBPUSD)
    - ohlcv / macro / others: anything that doesn't match the forex pattern,
      falling back to the first example
    """
    examples = cap.examples or []
    if not examples:
        return None
    if kind == "forex":
        fx = [e for e in examples if len(e) == 6 and e.isalpha() and e.isupper()]
        return fx[0] if fx else None
    non_fx = [e for e in examples if not (len(e) == 6 and e.isalpha() and e.isupper())]
    return non_fx[0] if non_fx else examples[0]


def check_per_source_contract_sweep() -> None:
    """Iterate every registered Source × every kind it claims and verify
    the ABC contract holds end-to-end: fetch + schema match + search +
    describe + list_all.

    Generic — any new source added via scaffold_source.py is automatically
    covered. No per-source hand-coded expectations.
    """
    print("\n=== 8a. Per-source ABC contract sweep ===")
    for src in all_sources():
        cap = src.capability
        if cap.status in {"deferred", "paid-only"} or not cap.examples:
            continue

        # fetch + schema match — exercise every kind the source claims.
        for kind in cap.kinds:
            example = _example_for_kind(cap, kind)
            if example is None:
                continue
            ref = DataRef(source=src.name, kind=kind, name=example, interval="1d")
            try:
                df = src.fetch(ref)
                declared = set(cap.schema.get(kind, []))
                actual = set(df.columns)
                ok = declared.issubset(actual) and len(df) > 0
                record(
                    f"{src.name}/{kind} {example}: fetch + schema",
                    ok,
                    f"rows={len(df)}, declared⊆actual={declared.issubset(actual)}",
                )
            except Exception as e:
                record(
                    f"{src.name}/{kind} {example}: fetch",
                    False,
                    f"{type(e).__name__}: {e}",
                )

        example = _example_for_kind(cap, cap.kinds[0]) or cap.examples[0]

        # search returns something OR is documented unsupported
        try:
            hits = src.search(example, limit=3)
            # We don't require non-empty (some upstreams have flaky search),
            # but it must not raise.
            record(
                f"{src.name}: search() callable",
                isinstance(hits, list),
                f"got {len(hits)} hits",
            )
        except Exception as e:
            record(f"{src.name}: search", False, f"{type(e).__name__}: {e}")

        # describe returns dict or None (must not raise)
        try:
            meta = src.describe(example)
            record(
                f"{src.name}: describe() callable",
                meta is None or isinstance(meta, dict),
                f"longname={meta.get('longname') if meta else None!r}",
            )
        except Exception as e:
            record(f"{src.name}: describe", False, f"{type(e).__name__}: {e}")

        # list_all returns list (may be empty for unbounded sources)
        try:
            listed = src.list_all(limit=5)
            record(
                f"{src.name}: list_all() callable",
                isinstance(listed, list),
                f"sample size={len(listed)}",
            )
        except Exception as e:
            record(f"{src.name}: list_all", False, f"{type(e).__name__}: {e}")


def check_discovery_per_source() -> None:
    """Every source must satisfy search(query) and describe(name) per ABC."""
    print("\n=== 8. Discovery contract — search + describe on every source ===")

    # FRED
    try:
        hits = tools.search_fred("unemployment", limit=5)
        ok = any("UNRATE" in (h.get("symbol") or "") for h in hits)
        record(
            "search_fred('unemployment') surfaces UNRATE",
            ok,
            f"symbols: {[h.get('symbol') for h in hits]}",
        )
        if hits:
            sample = hits[0]
            record(
                "  fred hit carries longname + frequency + units + notes",
                bool(sample.get("longname")) and "frequency" in sample
                and "units" in sample and "notes" in sample,
                f"keys={sorted(sample.keys())}",
            )
    except Exception as e:
        record("search_fred", False, f"{type(e).__name__}: {e}")

    try:
        meta = tools.describe_symbol("fred", "DGS10")
        record(
            "describe_symbol('fred','DGS10') returns title + units + notes",
            bool(meta and meta.get("longname") and meta.get("units")
                 and meta.get("notes")),
            f"longname={meta.get('longname') if meta else None!r}, "
            f"notes_len={len(meta.get('notes') or '') if meta else 0}",
        )
    except Exception as e:
        record("describe_symbol(fred,DGS10)", False, f"{type(e).__name__}: {e}")

    # yfinance
    try:
        hits = tools.search_yfinance("Apple", limit=3)
        ok = any(h.get("symbol") == "AAPL" for h in hits)
        record(
            "search_yfinance('Apple') surfaces AAPL with longname",
            ok and any(h.get("longname") for h in hits),
            f"top: {[(h.get('symbol'), h.get('longname')) for h in hits]}",
        )
    except Exception as e:
        record("search_yfinance", False, f"{type(e).__name__}: {e}")

    try:
        meta = tools.describe_symbol("yfinance", "AAPL")
        record(
            "describe_symbol('yfinance','AAPL') returns longname + sector",
            bool(meta and meta.get("longname") and meta.get("sector")),
            f"longname={meta.get('longname') if meta else None!r}, "
            f"sector={meta.get('sector') if meta else None!r}",
        )
    except Exception as e:
        record("describe_symbol(yfinance,AAPL)", False, f"{type(e).__name__}: {e}")

    # Binance
    try:
        pairs = tools.list_binance_pairs(quote="USDT")
        ok = len(pairs) > 100  # USDT pairs are easily 200+
        record(
            "list_binance_pairs(quote='USDT') enumerates pairs",
            ok,
            f"count={len(pairs)} (sample: {[p['symbol'] for p in pairs[:3]]})",
        )
    except Exception as e:
        record("list_binance_pairs", False, f"{type(e).__name__}: {e}")

    try:
        hits = tools.search_binance("Bitcoin", limit=5)
        btc_top = hits and hits[0].get("symbol", "").startswith("BTC")
        has_longname = hits and "Bitcoin" in (hits[0].get("longname") or "")
        record(
            "search_binance('Bitcoin') surfaces BTC pairs with long name",
            bool(btc_top and has_longname),
            f"top: {hits[0].get('symbol') if hits else None} → "
            f"{hits[0].get('longname') if hits else None}",
        )
    except Exception as e:
        record("search_binance", False, f"{type(e).__name__}: {e}")

    try:
        meta = tools.describe_symbol("binance", "BTCUSDT")
        record(
            "describe_symbol('binance','BTCUSDT') resolves long name",
            bool(meta and meta.get("longname") and "Bitcoin" in meta["longname"]),
            f"longname={meta.get('longname') if meta else None!r}",
        )
    except Exception as e:
        record("describe_symbol(binance,BTCUSDT)", False, f"{type(e).__name__}: {e}")

    # Cross-source generic dispatch sanity.
    try:
        registered = {s["source"] for s in tools.list_searchable_sources()}
        record(
            "every source registers a search+describe surface (ABC contract)",
            {"fred", "yfinance", "binance"}.issubset(registered),
            f"registered: {sorted(registered)}",
        )
    except Exception as e:
        record("list_searchable_sources", False, f"{type(e).__name__}: {e}")


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
        check_per_source_contract_sweep,
        check_discovery_per_source,
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
