"""Pydantic models for data flowing through the toolkit.

These are the boundary types: every fetch tool returns one of these,
and every downstream tool consumes one of these. Keeping the set small
and stable is what lets card specs reference data by key rather than
by value.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Interval = Literal["1m", "5m", "15m", "1h", "1d", "1w", "1mo"]


class TimeSeries(BaseModel):
    """Generic univariate series indexed by timestamp."""

    name: str
    source: str
    interval: Interval
    timestamps: list[datetime]
    values: list[float]
    unit: str | None = None

    def __len__(self) -> int:
        return len(self.timestamps)


class OHLCV(BaseModel):
    """Open/High/Low/Close/Volume series."""

    symbol: str
    source: str
    interval: Interval
    timestamps: list[datetime]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.timestamps)


class NewsItem(BaseModel):
    """A single news article reference."""

    title: str
    url: str
    source: str
    published_at: datetime
    summary: str | None = None
    tickers: list[str] = Field(default_factory=list)
