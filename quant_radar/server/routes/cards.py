"""REST endpoints wrapping the card tools.

Each endpoint is a thin adapter — the agent-facing functions in
``quant_radar.tools`` do the real work. We just translate between HTTP
and Pydantic request models.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from quant_radar import tools
from quant_radar.cards import store
from quant_radar.server.schemas import (
    AddAnnotationRequest,
    CreateCardRequest,
    OKResponse,
    Target,
    UpdateCardRequest,
)

router = APIRouter()


@router.get("/cards/{target}", response_model=list[dict[str, Any]])
def list_cards(target: Target) -> list[dict[str, Any]]:
    return tools.load_dashboard(target)


@router.post("/cards", response_model=dict[str, Any])
def create_card(req: CreateCardRequest) -> dict[str, Any]:
    return tools.create_dashboard_card(
        type=req.type,
        title=req.title,
        data_refs=[d.model_dump(mode="json") for d in req.data_refs],
        chart_spec=req.chart_spec.model_dump(mode="json") if req.chart_spec else None,
        analysis_markdown=req.analysis_markdown,
        news=req.news,
        layout=req.layout.model_dump(mode="json") if req.layout else None,
        target=req.target,
    )


@router.patch("/cards/{card_id}", response_model=dict[str, Any])
def update_card(
    card_id: UUID, req: UpdateCardRequest, target: Target = "working"
) -> dict[str, Any]:
    out = tools.update_card(
        card_id,
        target=target,
        title=req.title,
        chart_spec=req.chart_spec.model_dump(mode="json") if req.chart_spec else None,
        data_refs=(
            [d.model_dump(mode="json") for d in req.data_refs]
            if req.data_refs is not None
            else None
        ),
        analysis_markdown=req.analysis_markdown,
        news=req.news,
        layout=req.layout.model_dump(mode="json") if req.layout else None,
    )
    if out is None:
        raise HTTPException(status_code=404, detail=f"card {card_id} not found")
    return out


@router.delete("/cards/{card_id}", response_model=OKResponse)
def remove_card(card_id: UUID, target: Target = "working") -> OKResponse:
    return OKResponse(ok=tools.remove_card(card_id, target=target))


@router.post("/cards/clear", response_model=dict[str, int])
def clear_cards(target: Target = "working") -> dict[str, int]:
    """Remove every card from ``target`` (main or working). UI exposes
    this as the per-tab "Clear all" button; tedious to click ✕ per card.
    """
    return {"removed": tools.clear_dashboard(target=target)}


@router.post("/cards/{card_id}/save-to-main", response_model=OKResponse)
def save_card_to_main(card_id: UUID) -> OKResponse:
    return OKResponse(ok=tools.save_card_to_dashboard(card_id))


@router.post("/cards/{card_id}/annotations", response_model=OKResponse)
def add_annotation(card_id: UUID, req: AddAnnotationRequest) -> OKResponse:
    return OKResponse(
        ok=tools.add_annotation(card_id, req.annotation, target=req.target)
    )


# --- Working session lifecycle ---


@router.post("/working/new", status_code=204)
def new_working() -> Response:
    tools.new_working_dashboard()
    return Response(status_code=204)


@router.post("/working/close", status_code=204)
def close_working() -> Response:
    tools.close_working_dashboard()
    return Response(status_code=204)


@router.get("/working/state", response_model=dict[str, bool])
def working_state() -> dict[str, bool]:
    return {"is_open": store.working_is_open()}
