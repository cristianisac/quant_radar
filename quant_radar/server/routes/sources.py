"""Source introspection endpoints — catalog + live history probe."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from quant_radar import tools

router = APIRouter()


@router.get("/sources", response_model=list[dict[str, Any]])
def list_sources() -> list[dict[str, Any]]:
    return tools.list_sources()


@router.get("/sources/{name}", response_model=dict[str, Any])
def describe_source(name: str) -> dict[str, Any]:
    out = tools.describe_source(name)
    if out is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not in catalog")
    return out


@router.get("/probe-history", response_model=dict[str, Any])
def probe_history(
    symbol: str, source: str = "yfinance", kind: str = "ohlcv"
) -> dict[str, Any]:
    return tools.probe_history(symbol, source=source, kind=kind)
