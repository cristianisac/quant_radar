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

CardType = Literal["chart", "news", "sentiment", "analysis", "combo", "table"]
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


class Series(BaseModel):
    """Explicit series assignment for multi-axis charts.

    Lets a card place two (or more) named columns on left/right y-axes
    regardless of whether the data lives in one frame or many. ``ref``
    indexes into ``card.data_refs``; ``column`` names the column in
    that frame. Without an explicit ``series`` list the chart falls
    back to the close→value→first-numeric waterfall on the first ref
    (and on the second ref as a right-axis series, if present).

    Example — two series from the **same** frame on dual axes::

        chart_spec = {
            "series": [
                {"ref": 0, "column": "standard_contracts", "axis": "left"},
                {"ref": 0, "column": "micro_contracts",    "axis": "right"},
            ],
        }
    """

    ref: int = 0
    column: str
    axis: Literal["left", "right"] = "left"
    label: str | None = None


class ChartSpec(BaseModel):
    """Rendering hints for a chart card."""

    overlays: list[str] = Field(default_factory=list)  # e.g. ["sma_50", "sma_200"]
    subplots: list[str] = Field(default_factory=list)  # e.g. ["rsi", "volume", "yoy"]
    annotations: list[Annotation] = Field(default_factory=list)
    # Explicit series → axis assignment. Use when both series live in
    # one frame, or when you want to force which goes left vs right.
    # When empty, the renderer uses the implicit "first ref → left,
    # second ref → right" rule that all existing cards rely on.
    series: list[Series] = Field(default_factory=list)


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
