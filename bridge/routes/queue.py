"""Acquisition-queue endpoints: run a mixed measurement series unattended."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from bridge.protocol.client import ProtocolClient
from bridge.services.queue import AcquisitionQueue

router = APIRouter(prefix="/api/queue")


class QueueItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: str
    params: dict[str, Any] = {}
    repeat: int = Field(default=1, ge=1, le=100)


class QueueRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[QueueItem]


@router.post("/run")
async def run_queue(request: Request, body: QueueRequest) -> dict[str, object]:
    protocol: ProtocolClient = request.app.state.protocol
    queue: AcquisitionQueue = request.app.state.queue

    if not protocol.connected:
        return {"status": "error", "message": "vendor disconnected"}
    return await queue.start([item.model_dump() for item in body.items])


@router.get("/status")
async def queue_status(request: Request) -> dict[str, object]:
    queue: AcquisitionQueue = request.app.state.queue
    return queue.status()
