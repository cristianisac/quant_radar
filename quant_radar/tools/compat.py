"""Tool ↔ source informational registry (no longer gating).

Historically, analytical tools declared required columns via
``@requires_columns(...)`` and ``tools_for_ref(ref)`` returned only the
tools whose requirements matched a source's schema. That gated which
indicators the agent could apply to a frame.

We removed that gate: analytical tools are now column-agnostic and
auto-pick the price column (close → value → only-numeric). Any tool
can be applied to any time series; if a column truly isn't there, the
tool raises a clear error. The user/agent decides what makes sense.

The functions here are kept as informational APIs for the agent:
``all_analytical_tools()`` returns the canonical list, ``tools_for_ref``
returns the same list regardless of ref (the universe of choices).
"""

from __future__ import annotations

from quant_radar.cards.spec import DataRef

# Canonical list of analytical tools the agent can apply to any time
# series. Order is informational only.
_ANALYTICAL_TOOLS: tuple[str, ...] = (
    "compute_returns",
    "compute_indicators",
    "analyze_moving_averages",
    "analyze_indicators",
    "rolling_zscore",
    "detect_channels",
    "detect_breakouts",
    "detect_patterns_vision",
)


def all_analytical_tools() -> list[str]:
    """Return every analytical tool the agent can apply to a time series."""
    return list(_ANALYTICAL_TOOLS)


def tools_for_ref(ref: DataRef) -> list[str]:  # noqa: ARG001
    """Return analytical tools applicable to ``ref``.

    Now returns the full list regardless of source/kind, because tools
    are column-agnostic. The agent picks what makes sense for the data;
    we don't pre-filter. Kept for backward compatibility with callers
    that asked "what can I do with this DataRef?".
    """
    return list(_ANALYTICAL_TOOLS)


# Legacy API kept as a no-op so older imports / older tests don't break.
# Tools no longer self-declare column requirements; column resolution
# happens at call time via `_pick_price_column`.
def requires_columns(*_cols: str):
    """No-op decorator. Tools are column-agnostic now."""

    def deco(fn):
        return fn

    return deco


def requirements_for(_tool_name: str) -> frozenset[str]:
    return frozenset()


def all_requirements() -> dict[str, list[str]]:
    return {}
