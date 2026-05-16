"""FastAPI app factory.

Loopback-bound (`uvicorn ... --host 127.0.0.1` from the launcher). CORS
is enabled for the React dev server origin so phases B–C can talk to
this backend from a separate port during development.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from quant_radar.server.routes import cards, data, health, sources


def create_app() -> FastAPI:
    app = FastAPI(
        title="quant_radar API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # The React dev server typically runs on :3000 / :5173. We bind both
    # so either Next.js or Vite defaults work without configuration.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(cards.router, prefix="/api")
    app.include_router(sources.router, prefix="/api")
    app.include_router(data.router, prefix="/api")
    return app


app = create_app()
