"""FastAPI application entrypoint for the SPAD512² bridge."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bridge import __version__
from bridge.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SPAD512² Bridge", version=__version__)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.state.settings = settings
    return app


app = create_app()
