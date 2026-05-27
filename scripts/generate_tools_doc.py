"""Generate TOOLS.md — a single source-of-truth for what the codebase exposes.

Three sections, each derived live from the registry so it cannot drift:

1. **API-specific data tools** — for each source in the catalog, the kinds
   it serves (with declared schema columns) + the auth, rate limit, status,
   and whether the integration audit has live-verified each (source, kind)
   pair under our actual keys.

2. **Agent-callable tool surface** — every function exported from
   ``quant_radar.tools.__all__``, grouped into:
     - Data fetching (per source)
     - Cross-kind composers (combo helpers, multi-source routing)
     - Analytical tools (column-agnostic, apply to any time series)
     - Card lifecycle
     - Discovery / introspection
     - News-specific tools

3. **Cross-kind relationships** — every relationship from
   ``kind_relationships.py`` so the agent can see at a glance what pairs.

Run::

    docker run --rm --env-file .env quant-radar:dev \
        python scripts/generate_tools_doc.py > TOOLS.md

A pytest assertion (``tests/test_tools_doc_sync.py``) re-runs this and
compares against the committed TOOLS.md so the doc stays in lockstep
with the registry.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

from quant_radar import tools as tools_module
from quant_radar.sources import kind_coverage, kind_relationships
from quant_radar.sources.base_source import all_sources
from quant_radar.sources.catalog import CATALOG

# Manual grouping of tools that exposes intent. Maintain when adding a tool.
_TOOL_GROUPS: list[tuple[str, list[str]]] = [
    (
        "Card lifecycle",
        [
            "create_dashboard_card",
            "update_card",
            "save_card_to_dashboard",
            "remove_card",
            "clear_dashboard",
            "load_dashboard",
            "new_working_dashboard",
            "close_working_dashboard",
            "persist_dashboard",
            "add_annotation",
        ],
    ),
    (
        "Analytical tools (column-agnostic — apply to any time series)",
        [
            "compute_returns",
            "compute_indicators",
            "analyze_indicators",
            "analyze_moving_averages",
            "rolling_zscore",
            "filter_by_date",
        ],
    ),
    (
        "Pattern detection",
        [
            "detect_channels",
            "detect_breakouts",
            "detect_patterns_vision",
            "channel_annotations",
        ],
    ),
    (
        "News tools",
        [
            "fetch_news",
            "fetch_top_headlines",
            "summarize_news",
            "score_sentiment",
        ],
    ),
    (
        "Sentiment + social (with multi-source routing)",
        [
            "fetch_sentiment",
            "describe_sentiment_routing",
            "fetch_social_sentiment",
            "describe_social_sentiment_routing",
            "fetch_attention_and_polarity",
        ],
    ),
    (
        "Economic calendar",
        [
            "fetch_economic_calendar",
            "describe_economic_calendar_routing",
        ],
    ),
    (
        "Discovery / source introspection",
        [
            "list_sources",
            "describe_source",
            "list_searchable_sources",
            "list_all_symbols",
            "list_binance_pairs",
            "search_source",
            "search_yfinance",
            "search_binance",
            "search_fred",
            "describe_symbol",
            "probe_history",
            "list_kind_relationships",
            "relationships_for_kind",
            "describe_kind_coverage",
            "list_covered_kinds",
            "tools_for_ref",
            "requirements_for",
            "all_requirements",
            "all_analytical_tools",
        ],
    ),
]


def _verify_access() -> dict[tuple[str, str], tuple[bool, str]]:
    """Live-probe every (source, kind) pair the catalog declares.

    Returns ``{(source, kind): (ok, detail)}``. Failures keep the message
    so the rendered doc shows *why* a pair isn't accessible (auth
    missing, rate-limited, paid-only endpoint, etc.).
    """
    result: dict[tuple[str, str], tuple[bool, str]] = {}
    for src in all_sources():
        cap = src.capability
        for kind in cap.kinds:
            examples = cap.examples or []
            if not examples:
                result[(src.name, kind)] = (False, "no example in catalog")
                continue
            # Pick the first sensible example for the kind.
            example = examples[0]
            if kind == "forex":
                fx = [e for e in examples if len(e) == 6 and e.isalpha() and e.isupper()]
                example = fx[0] if fx else example
            from quant_radar.cards.spec import DataRef
            ref = DataRef(source=src.name, kind=kind, name=example, interval="1d")
            if not src.supports(ref):
                # ABC doesn't cover this kind (e.g. gdelt/news is list[dict])
                result[(src.name, kind)] = (True, "non-conforming surface (not ABC)")
                continue
            try:
                df = src.fetch(ref)
                declared = set(cap.schema.get(kind, []))
                actual = set(df.columns)
                ok = declared.issubset(actual) and len(df) > 0
                result[(src.name, kind)] = (
                    ok, f"rows={len(df)}, schema⊆actual={declared.issubset(actual)}",
                )
            except Exception as e:  # noqa: BLE001
                result[(src.name, kind)] = (False, f"{type(e).__name__}: {e}")
    return result


def _render(buf: io.StringIO, *, verify: bool) -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    buf.write("# quant_radar — Tool & Data Surface\n\n")
    buf.write(
        "**Generated**: this file is produced by "
        "`scripts/generate_tools_doc.py` from the live registry "
        f"(`CATALOG` + `tools.__all__` + `kind_relationships`). "
        f"Last regenerated {today}.\n\n"
    )
    buf.write(
        "Do not edit by hand — change the registry instead, then "
        "regenerate. A pytest assertion guards against drift.\n\n"
    )
    buf.write("---\n\n")

    # --- 1. Data sources -------------------------------------------------
    buf.write("## 1. Data sources & coverage with our authentication\n\n")
    buf.write(
        "Each row is a (source, kind) pair. **Verified** means the "
        "integration audit successfully fetched real data using the keys "
        "in our `.env`. Failures keep the upstream error so you can see "
        "*why* a pair isn't accessible.\n\n"
    )

    access = _verify_access() if verify else {}

    for name in sorted(CATALOG.keys()):
        cap = CATALOG[name]
        buf.write(f"### `{name}`\n\n")
        buf.write(
            f"- **Auth**: {cap.auth}\n"
            f"- **Rate limit**: {cap.rate_limit}\n"
            f"- **Status**: {cap.status}\n"
            f"- **Coverage**: {cap.coverage}\n"
        )
        if cap.notes:
            buf.write(f"- **Notes**: {cap.notes}\n")
        buf.write("\n")
        buf.write(
            "| kind | declared schema | verified | detail |\n"
            "|---|---|:---:|---|\n"
        )
        for kind in cap.kinds:
            schema = cap.schema.get(kind, [])
            schema_str = ", ".join(f"`{c}`" for c in schema) if schema else "—"
            if verify:
                ok, detail = access.get((name, kind), (False, "not probed"))
                tick = "✅" if ok else "❌"
            else:
                tick, detail = "—", "verification skipped"
            buf.write(f"| `{kind}` | {schema_str} | {tick} | {detail} |\n")
        buf.write("\n")

    # --- 2. Tool surface -------------------------------------------------
    buf.write("## 2. Agent-callable tool surface\n\n")
    buf.write(
        "Every function exported from `quant_radar.tools`. The grouping "
        "is intent-based, not module-based. Tool count = "
        f"{len(tools_module.__all__)}.\n\n"
    )
    assigned: set[str] = set()
    for group_name, names in _TOOL_GROUPS:
        group_present = [n for n in names if n in tools_module.__all__]
        if not group_present:
            continue
        buf.write(f"### {group_name}\n\n")
        for n in sorted(group_present):
            fn = getattr(tools_module, n, None)
            doc = ""
            if fn is not None and fn.__doc__:
                doc = fn.__doc__.strip().split("\n")[0]
            buf.write(f"- `{n}` — {doc or '(no docstring)'}\n")
            assigned.add(n)
        buf.write("\n")

    leftover = [n for n in tools_module.__all__ if n not in assigned]
    if leftover:
        buf.write("### Other / uncategorized\n\n")
        for n in sorted(leftover):
            buf.write(f"- `{n}`\n")
        buf.write("\n")
        buf.write(
            "> If you're adding a tool, please also classify it in "
            "`scripts/generate_tools_doc.py::_TOOL_GROUPS`.\n\n"
        )

    # --- 3. Cross-kind relationships -------------------------------------
    buf.write("## 3. Cross-kind relationships\n\n")
    buf.write(
        "From `kind_relationships.py` — which data types pair / compose / "
        "extend each other.\n\n"
    )
    for r in kind_relationships.list_relationships():
        buf.write(f"### `{r['name']}` — *{r['relationship']}*\n\n")
        buf.write(f"**Kinds**: {', '.join(f'`{k}`' for k in r['kinds'])}\n\n")
        buf.write(f"{r['description']}\n\n")
        if r.get("combo_tool"):
            buf.write(f"**Combo tool**: `{r['combo_tool']}`\n\n")
        buf.write(f"**When to apply**: {r['rationale']}\n\n")

    # --- 4. Multi-source kind coverage -----------------------------------
    buf.write("## 4. Multi-source coverage per kind\n\n")
    buf.write(
        "From `kind_coverage.py` — when more than one source serves the "
        "same kind, how they relate (primary / fallback / complementary) "
        "and the default routing chain.\n\n"
    )
    for kind in kind_coverage.list_covered_kinds():
        cov = kind_coverage.get_coverage(kind) or {}
        buf.write(f"### `{kind}`\n\n")
        buf.write(f"{cov.get('description', '')}\n\n")
        buf.write("| provider | tier | rate limit |\n|---|---|---|\n")
        for prov, meta in (cov.get("providers") or {}).items():
            buf.write(
                f"| `{prov}` | {meta.get('tier', '?')} | "
                f"{meta.get('rate_limit', '?')} |\n"
            )
        buf.write("\n")
        chain = cov.get("default_chain") or []
        if chain:
            buf.write(f"**Default chain**: {' → '.join(f'`{p}`' for p in chain)}\n\n")
        if cov.get("routing_logic"):
            buf.write(f"**Routing logic**: {cov['routing_logic']}\n\n")


def render(*, verify: bool = True) -> str:
    buf = io.StringIO()
    _render(buf, verify=verify)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    verify = "--no-verify" not in sys.argv
    print(render(verify=verify), end="")
