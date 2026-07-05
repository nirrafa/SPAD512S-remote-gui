"""Data handling endpoints: save path, listing, download, sidecar.

SECURITY: these serve host files to an unauthenticated LAN. Every requested
path goes through :meth:`DataLocation.resolve`, which constrains it to the
configured data roots — ``..`` traversal and absolute escapes are rejected
before the filesystem is touched.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict

from bridge.protocol import commands
from bridge.protocol.client import NotConnectedError, ProtocolClient, ProtocolError
from bridge.services.data_location import DataLocation
from bridge.services.sidecar import SIDECAR_NAME, read_sidecar

router = APIRouter(prefix="/api/data")
settings_router = APIRouter(prefix="/api/settings")


class SavePathRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str


@settings_router.post("/save-path")
async def set_save_path(request: Request, body: SavePathRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    location: DataLocation = request.app.state.data_location
    try:
        await protocol.send_command(commands.set_save_path(body.path))
    except (NotConnectedError, ProtocolError) as exc:
        return {"status": "error", "message": str(exc)}
    location.set_save_path(body.path)
    return {"status": "ok", "path": body.path}


def _resolve_or_reject(request: Request, path: str) -> Path:
    location: DataLocation = request.app.state.data_location
    resolved = location.resolve(path)
    if resolved is None:
        raise HTTPException(status_code=400, detail="path outside data root")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="path not found")
    return resolved


@router.get("/list")
async def list_files(request: Request, path: str) -> list[str]:
    resolved = _resolve_or_reject(request, path)
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="not a directory")
    return sorted(child.name for child in resolved.iterdir())


@router.get("/download")
async def download(request: Request, path: str) -> Response:
    resolved = _resolve_or_reject(request, path)
    if resolved.is_file():
        return FileResponse(resolved, filename=resolved.name)
    files = sorted(p for p in resolved.rglob("*") if p.is_file())
    return JSONResponse(
        {
            "path": path,
            "files": [
                {"name": str(p.relative_to(resolved)), "size": p.stat().st_size}
                for p in files
            ],
            "total_bytes": sum(p.stat().st_size for p in files),
        }
    )


@router.get("/sidecar")
async def sidecar(request: Request, path: str) -> dict[str, object]:
    resolved = _resolve_or_reject(request, path)
    target = resolved / SIDECAR_NAME if resolved.is_dir() else resolved
    if not target.is_file():
        raise HTTPException(status_code=404, detail="sidecar not found")
    try:
        return read_sidecar(target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
