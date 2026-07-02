"""FastAPI application entrypoint for the SPAD512² bridge."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from bridge import __version__
from bridge.config import Settings, get_settings
from bridge.core.acquisition import AcquisitionRunner
from bridge.core.calibration_state import CalibrationStore
from bridge.core.instrument import InstrumentState
from bridge.core.ws_hub import WebSocketHub
from bridge.protocol.client import ProtocolClient
from bridge.routes import acquire, calibration, health, system, ws
from bridge.services.health import HealthMonitor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    hub = WebSocketHub()

    async def on_connection_change(connected: bool) -> None:
        await hub.broadcast_state({"vendor_connected": connected})

    # The acquisition runner owns busy/idle broadcasts (so the first frame a
    # client sees after an acquire is `busy`); state changes are not auto-pushed.
    instrument = InstrumentState()
    protocol = ProtocolClient(
        settings.vendor_host,
        settings.vendor_port,
        on_state_change=on_connection_change,
    )

    app.state.hub = hub
    app.state.instrument = instrument
    app.state.protocol = protocol
    app.state.flim_irf_calibrated = False

    calibration_store = CalibrationStore()
    app.state.calibration = calibration_store

    await protocol.start()
    # ProtocolClient performs the breakdown handshake on connect (see
    # protocol/client.py), so breakdown is already done by the time we get here.
    if protocol.connected:
        calibration_store.mark_done("breakdown")
    sensor_size = protocol.system_info["sensor_size"] if protocol.system_info else 512
    runner = AcquisitionRunner(
        protocol, instrument, hub, settings.data_root, sensor_size=sensor_size
    )
    app.state.runner = runner

    health_monitor = HealthMonitor(protocol, instrument, hub)
    runner.health_monitor = health_monitor
    app.state.health = health_monitor
    health_monitor.start()
    try:
        yield
    finally:
        await health_monitor.stop()
        await protocol.stop()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SPAD512² Bridge", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    # Unauthenticated LAN tool: wildcard origins, no credentials. ("*" + credentials
    # is an invalid CORS combination that browsers reject.)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(health.settings_router)
    app.include_router(system.router)
    app.include_router(acquire.router)
    app.include_router(calibration.router)
    app.include_router(calibration.status_router)
    app.include_router(ws.router)

    # Serve the built single-page app at "/" (same origin as the API, so no Vite
    # dev server is needed at runtime). Mounted last, after the API routers, so
    # /api/* and /ws take precedence. Only mounted when a production build exists.
    spa_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if (spa_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(spa_dist), html=True), name="spa")

    return app


app = create_app()
