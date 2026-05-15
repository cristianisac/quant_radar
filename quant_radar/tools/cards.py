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


def save_card_to_dashboard(card_id: str | UUID) -> bool:
    """Promote a working card to the persistent main dashboard.

    Returns True if a card with ``card_id`` existed in working and was
    copied to main; False otherwise. The working copy is left in place
    so the user can still see it in the Working tab until the session
    ends.
    """
    promoted = store.promote_to_main(card_id)
    return promoted is not None


def update_card(
    card_id: str | UUID,
    *,
    target: Target = "working",
    title: str | None = None,
    chart_spec: dict | ChartSpec | None = None,
    data_refs: list[dict] | list[DataRef] | None = None,
    analysis_markdown: str | None = None,
    news: list[dict] | None = None,
    layout: dict | LayoutHint | None = None,
) -> dict[str, Any] | None:
    """Modify an existing card in-place. Only-set fields are updated.

    Use this for requests like *"Add RSI and ATR to this chart"* — the
    card's ID stays stable so references on the dashboard remain valid.
    Returns the updated card dict, or ``None`` if no card with that ID
    exists in the target dashboard.
    """
    card = store.get(card_id, target)
    if card is None:
        return None
    if title is not None:
        card.title = title
    if chart_spec is not None:
        card.chart_spec = _coerce_chart_spec(chart_spec)
    if data_refs is not None:
        card.data_refs = _coerce_data_refs(data_refs)
    if analysis_markdown is not None:
        card.analysis_markdown = analysis_markdown
    if news is not None:
        card.news = news
    if layout is not None:
        card.layout = _coerce_layout(layout)
    store.save(card, target)
    return card.model_dump(mode="json")


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
    """Start (or re-open) a working dashboard with no cards.

    Previous working cards are intentionally lost. The working.json file
    is present after this call so the UI knows the session is open.
    """
    store.working_reset()


def close_working_dashboard() -> None:
    """End the working session entirely — Working tab disappears.

    Symmetric to ``new_working_dashboard``. Use when the user is done
    with the scratchpad ("close my working dashboard").
    """
    store.working_close()


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
