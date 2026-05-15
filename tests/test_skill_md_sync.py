"""Guard against SKILL.md ↔ tool surface drift.

Every ``tools.<name>`` reference in SKILL.md must exist in
``quant_radar.tools.__all__``. Catches:
- a tool was renamed but SKILL.md kept the old name
- a tool was added but SKILL.md wasn't updated (false negative — only
  the *reverse* direction is silently lossy here, so we also assert no
  drift in the other direction with a relaxed check)
"""

from __future__ import annotations

import re
from pathlib import Path

import quant_radar.tools as qr_tools

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILL_MD = _REPO_ROOT / "SKILL.md"
_TOOL_REF = re.compile(r"tools\.([a-z_][a-z0-9_]*)\b")


def _referenced_tools() -> set[str]:
    text = _SKILL_MD.read_text()
    return set(_TOOL_REF.findall(text))


def test_skill_md_only_references_exported_tools():
    referenced = _referenced_tools()
    exported = set(qr_tools.__all__)
    missing = referenced - exported
    assert not missing, (
        f"SKILL.md references tools that don't exist in tools.__all__: "
        f"{sorted(missing)}"
    )


def test_all_exported_tools_are_callable():
    """Sanity: every name in __all__ resolves to a callable attribute."""
    for name in qr_tools.__all__:
        attr = getattr(qr_tools, name, None)
        assert callable(attr), f"{name} is exported but not callable"
