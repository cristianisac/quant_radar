"""Agent-facing card tools.

These mirror the user's spec verbatim: ``create_dashboard_card``,
``save_card_to_dashboard``, ``remove_card``, ``persist_dashboard``,
``load_dashboard``. The functions accept simple kwargs (no pandas
imports needed by the agent) and return Pydantic dicts.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from quant_radar.cards import store
from quant_radar.cards.spec import (
    Annotation,
    Card,
    CardType,
    ChartSpec,
    DataRef,
    LayoutHint,
    Target,
)


def _coerce_data_refs(data_refs: list[dict] | list[DataRef] | None) -> list[DataRef]:
    if not data_refs:
        return []
    return [DataRef.model_validate(d) if not isinstance(d, DataRef) else d for d in data_refs]


def _coerce_chart_spec(chart_spec: dict | ChartSpec | None) -> ChartSpec | None:
    if chart_spec is None:
        return None
    return chart_spec if isinstance(chart_spec, ChartSpec) else ChartSpec.model_validate(chart_spec)


def _coerce_layout(layout: dict | LayoutHint | None) -> LayoutHint:
    if layout is None:
        return LayoutHint()
    return layout if isinstance(layout, LayoutHint) else LayoutHint.model_validate(layout)


def create_dashboard_card(
    *,
    type: CardType,
    title: str,
    data_refs: list[dict] | list[DataRef] | None = None,
    chart_spec: dict | ChartSpec | None = None,
    analysis_markdown: str | None = None,
    news: list[dict] | None = None,
    layout: dict | LayoutHint | None = None,
    target: Target = "working",
) -> dict[str, Any]:
    """Create a new card and persist it. Defaults to the working dashboard."""
    card = Card(
        type=type,
        title=title,
        data_refs=_coerce_data_refs(data_refs),
        chart_spec=_coerce_chart_spec(chart_spec),
        analysis_markdown=analysis_markdown,
        news=news or [],
        layout=_coerce_layout(layout),
    )
    store.save(card, target)
    return card.model_dump(mode="json")


def save_card_to_dashboard(card_id: str | UUID, *, target: Target = "main") -> bool:
    """Promote a card from working to main (or no-op if already there)."""
    if target == "main":
        promoted = store.promote_to_main(card_id)
        return promoted is not None
    card = store.working_get(card_id)
    if card is None:
        return False
    store.working_save(card)
    return True


def remove_card(card_id: str | UUID, *, target: Target = "working") -> bool:
    return store.remove(card_id, target)


def persist_dashboard(target: Target = "working") -> int:
    """Force-flush any in-memory state. Returns the number of cards persisted.

    The store is write-through, so this is mostly a no-op; we return the
    current count for the agent to confirm state.
    """
    return len(store.list_cards(target))


def load_dashboard(target: Target = "main") -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in store.list_cards(target)]


def new_working_dashboard() -> None:
    """Start a fresh working dashboard. Existing working cards are dropped."""
    store.working_reset()


def add_annotation(
    card_id: str | UUID,
    annotation: dict | Annotation,
    *,
    target: Target = "working",
) -> bool:
    """Append a user-drawn annotation to a card's chart spec."""
    card = store.get(card_id, target)
    if card is None or card.chart_spec is None:
        return False
    if isinstance(annotation, Annotation):
        ann = annotation
    else:
        ann = Annotation.model_validate(annotation)
    card.chart_spec.annotations.append(ann)
    store.save(card, target)
    return True
