"""FastAPI app factory.

Loopback-bound (`uvicorn ... --host 127.0.0.1` from the launcher). CORS
is enabled for the React dev server origin so phases B–C can talk to
this backend from a separate port during development.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from quant_radar.server.routes import cards, data, health, sources

# React bundle path inside the container (populated by the Dockerfile's
# Node build stage). When running outside Docker / from a source
# checkout without a build, the mount is skipped — the API still works.
_UI_DIST = Path(__file__).resolve().parent / "ui_dist"


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

    # Mount the React bundle LAST so /api/* still takes priority. The
    # `html=True` flag makes Vite's SPA routing work (404 → /index.html).
    if _UI_DIST.is_dir():
        app.mount("/", StaticFiles(directory=_UI_DIST, html=True), name="ui")
    return app


app = create_app()
