"""FastAPI application entrypoint for the SPAD512² bridge."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bridge import __version__
from bridge.config import Settings, get_settings
from bridge.core.instrument import InstrumentState
from bridge.core.ws_hub import WebSocketHub
from bridge.protocol.client import ProtocolClient
from bridge.routes import acquire, health, system, ws


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    hub = WebSocketHub()

    async def on_state_change(instrument: InstrumentState) -> None:
        await hub.broadcast_state(instrument.snapshot())

    async def on_connection_change(connected: bool) -> None:
        await hub.broadcast_state({"vendor_connected": connected})

    instrument = InstrumentState(on_change=on_state_change)
    protocol = ProtocolClient(
        settings.vendor_host,
        settings.vendor_port,
        on_state_change=on_connection_change,
    )

    app.state.hub = hub
    app.state.instrument = instrument
    app.state.protocol = protocol

    await protocol.start()
    try:
        yield
    finally:
        await protocol.stop()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SPAD512² Bridge", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(acquire.router)
    app.include_router(ws.router)
    return app


app = create_app()
