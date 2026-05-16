from __future__ import annotations

from fastapi import APIRouter

import quant_radar
from quant_radar.server.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=quant_radar.__version__)
