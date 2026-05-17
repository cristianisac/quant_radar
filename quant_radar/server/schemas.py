"""Request/response Pydantic models for the REST API.

Card response shape is the existing ``Card.model_dump(mode='json')`` —
no rewrap, so the frontend sees exactly the persisted form.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from quant_radar.cards.spec import Annotation, ChartSpec, DataRef, LayoutHint

CardType = Literal["chart", "news", "sentiment", "analysis", "combo"]
Target = Literal["main", "working"]


class CreateCardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: CardType
    title: str
    data_refs: list[DataRef] = Field(default_factory=list)
    chart_spec: ChartSpec | None = None
    analysis_markdown: str | None = None
    news: list[dict[str, Any]] = Field(default_factory=list)
    layout: LayoutHint | None = None
    target: Target = "working"


class UpdateCardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    data_refs: list[DataRef] | None = None
    chart_spec: ChartSpec | None = None
    analysis_markdown: str | None = None
    news: list[dict[str, Any]] | None = None
    layout: LayoutHint | None = None


class AddAnnotationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    annotation: Annotation
    target: Target = "working"


class OKResponse(BaseModel):
    ok: bool


class HealthResponse(BaseModel):
    status: str
    version: str


# --- Data hydration ---


class TimeSeriesResponse(BaseModel):
    """Columnar layout — feeds directly into Plotly.js traces."""

    source: str
    kind: str
    name: str
    interval: str
    timestamps: list[datetime]
    columns: dict[str, list[float]]
    # Human-readable name resolved per source (e.g. FRED "title" for
    # DGS10 → "10-Year Treasury Constant Maturity Rate"). None when no
    # friendly name is available — the UI falls back to ``name``.
    display_name: str | None = None
