"""Guards that ``TOOLS.md`` stays in lockstep with the live registry.

We don't do strict text equality (the verified-access column would
need live network calls in CI). Instead, we assert structural
coverage: every source, every kind, every exported tool, every
relationship must appear in the committed doc.

To regenerate after a registry change::

    docker run --rm --env-file .env quant-radar:dev \
        python scripts/generate_tools_doc.py > TOOLS.md
"""

from __future__ import annotations

from pathlib import Path

from quant_radar import tools
from quant_radar.sources import kind_coverage, kind_relationships
from quant_radar.sources.catalog import CATALOG

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS_MD = _REPO_ROOT / "TOOLS.md"


def _doc() -> str:
    assert _TOOLS_MD.exists(), (
        "TOOLS.md missing — regenerate with "
        "`python scripts/generate_tools_doc.py > TOOLS.md`"
    )
    return _TOOLS_MD.read_text(encoding="utf-8")


def test_every_catalog_source_appears() -> None:
    doc = _doc()
    for name in CATALOG:
        assert f"### `{name}`" in doc, (
            f"source '{name}' missing — regenerate TOOLS.md"
        )


def test_every_kind_appears_under_its_source() -> None:
    doc = _doc()
    for name, cap in CATALOG.items():
        # Locate the source section.
        marker = f"### `{name}`"
        assert marker in doc
        start = doc.index(marker)
        # Section ends at the next "### `" header.
        rest = doc[start + len(marker):]
        next_h3 = rest.find("\n### ")
        section = rest if next_h3 == -1 else rest[:next_h3]
        for kind in cap.kinds:
            assert f"`{kind}`" in section, (
                f"{name}/{kind} missing — regenerate TOOLS.md"
            )


def test_every_exported_tool_appears() -> None:
    doc = _doc()
    for name in tools.__all__:
        assert f"`{name}`" in doc, (
            f"tool '{name}' missing — regenerate TOOLS.md"
        )


def test_every_relationship_appears() -> None:
    doc = _doc()
    for r in kind_relationships.list_relationships():
        assert f"`{r['name']}`" in doc, (
            f"relationship '{r['name']}' missing — regenerate TOOLS.md"
        )


def test_every_kind_coverage_entry_appears() -> None:
    doc = _doc()
    for kind in kind_coverage.list_covered_kinds():
        # Each covered kind appears as a section header in section 4.
        assert f"### `{kind}`" in doc, (
            f"kind_coverage '{kind}' missing — regenerate TOOLS.md"
        )
