"""Card data model.

A ``Card`` is a declarative, JSON-serializable specification of one
dashboard tile. The renderer (Phase 4) turns specs into Plotly figures
or news/sentiment panels; the store (this phase) persists them. Cards
never embed bulk data — they reference it by ``DataRef`` so reloads
re-fetch from the cache.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

CardType = Literal["chart", "news", "sentiment", "analysis", "combo"]
Target = Literal["main", "working"]
AnnotationKind = Literal["hline", "vline", "trendline", "rect", "text"]


class DataRef(BaseModel):
    """Pointer to cached data — how to re-fetch on reload."""

    source: str  # "yfinance" | "fred" | "coinpaprika" | ...
    kind: str  # "ohlcv" | "macro"
    name: str  # e.g. "BTC-USD", "DGS10"
    interval: str = "1d"
    start: datetime | None = None
    end: datetime | None = None


class Annotation(BaseModel):
    """A user-drawn line/shape/text on a chart, persisted with the card."""

    kind: AnnotationKind
    points: list[tuple[float, float]] = Field(default_factory=list)
    label: str | None = None
    color: str | None = None


class ChartSpec(BaseModel):
    """Rendering hints for a chart card."""

    overlays: list[str] = Field(default_factory=list)  # e.g. ["sma_50", "sma_200"]
    subplots: list[str] = Field(default_factory=list)  # e.g. ["rsi", "volume", "yoy"]
    annotations: list[Annotation] = Field(default_factory=list)


class LayoutHint(BaseModel):
    """Grid placement and size in the dashboard."""

    width: int = 6  # 1..12 — bootstrap-style columns
    height: int = 4  # arbitrary unit interpreted by the renderer
    x: int | None = None
    y: int | None = None


class Card(BaseModel):
    """One dashboard tile."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    type: CardType
    title: str
    data_refs: list[DataRef] = Field(default_factory=list)
    chart_spec: ChartSpec | None = None
    analysis_markdown: str | None = None  # for "analysis" type
    news: list[dict] = Field(default_factory=list)  # for "news" / "sentiment"
    layout: LayoutHint = Field(default_factory=LayoutHint)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)
