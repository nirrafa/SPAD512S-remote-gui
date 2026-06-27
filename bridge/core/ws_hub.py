"""WebSocket hub: client registry and broadcast helpers.

Slow or dead clients must not block others, so each broadcast tolerates
per-client send failures and drops disconnected clients.
"""
from __future__ import annotations

from typing import Any

from fastapi import WebSocket


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_json(message)
            except Exception:
                dead.append(client)
        for client in dead:
            self._clients.discard(client)

    async def broadcast_state(self, payload: dict[str, Any]) -> None:
        await self.broadcast({"type": "state", "data": payload})

    async def broadcast_progress(self, payload: dict[str, Any]) -> None:
        await self.broadcast({"type": "progress", "data": payload})

    async def broadcast_preview(self, payload: dict[str, Any]) -> None:
        await self.broadcast({"type": "preview", "data": payload})

    async def broadcast_alarm(self, payload: dict[str, Any]) -> None:
        await self.broadcast({"type": "alarm", "data": payload})
