"""Tool ↔ source compatibility registry.

Each analytical tool that needs specific columns (e.g. RSI needs
``close``, ATR needs ``high/low/close``) declares its requirement via
``@requires_columns(...)``. The registry then answers questions like
"which tools work for a yfinance OHLCV DataRef?" by intersecting
the requirements with each source's declared schema.

This is the substrate the agent uses to know which tools apply to a
given fetched frame without hard-coding the mapping in SKILL.md.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from quant_radar.cards.spec import DataRef
from quant_radar.sources.catalog import CATALOG

F = TypeVar("F", bound=Callable[..., object])

# tool name -> required column set
_REQUIREMENTS: dict[str, frozenset[str]] = {}


def requires_columns(*cols: str) -> Callable[[F], F]:
    """Mark ``fn`` as needing ``cols`` present in the input DataFrame.

    The tool registry uses this to compute which sources can feed it.
    """

    def deco(fn: F) -> F:
        _REQUIREMENTS[fn.__name__] = frozenset(cols)
        return fn

    return deco


def requirements_for(tool_name: str) -> frozenset[str]:
    return _REQUIREMENTS.get(tool_name, frozenset())


def all_requirements() -> dict[str, list[str]]:
    """Serializable view of every declared requirement."""
    return {k: sorted(v) for k, v in _REQUIREMENTS.items()}


def tools_for_ref(ref: DataRef) -> list[str]:
    """Tools whose required columns are all present in the schema for
    ``(ref.source, ref.kind)``. Empty list if the source/kind is unknown.
    """
    cap = CATALOG.get(ref.source)
    if cap is None:
        return []
    schema_cols = set(cap.schema.get(ref.kind, []))
    if not schema_cols:
        return []
    return sorted(
        name for name, req in _REQUIREMENTS.items() if req.issubset(schema_cols)
    )
