"""Unit tests for the WebSocket hub broadcast semantics."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from bridge.core.ws_hub import WebSocketHub


class _FakeWebSocket:
    def __init__(self, on_send: Callable[[], Awaitable[None]] | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self._on_send = on_send

    async def send_json(self, message: dict[str, Any]) -> None:
        if self._on_send is not None:
            await self._on_send()
        self.sent.append(message)


async def test_broadcast_survives_concurrent_connect() -> None:
    # Review finding #1: a client connecting mid-broadcast must not raise
    # "Set changed size during iteration".
    hub = WebSocketHub()
    intruder = _FakeWebSocket()

    async def connect_during_send() -> None:
        hub._clients.add(intruder)  # type: ignore[arg-type]

    existing = _FakeWebSocket(on_send=connect_during_send)
    hub._clients.add(existing)  # type: ignore[arg-type]

    await hub.broadcast({"type": "state", "data": {}})

    assert existing.sent  # broadcast completed without raising


async def test_broadcast_drops_dead_clients() -> None:
    hub = WebSocketHub()

    async def boom() -> None:
        raise RuntimeError("client gone")

    dead = _FakeWebSocket(on_send=boom)
    alive = _FakeWebSocket()
    hub._clients.add(dead)  # type: ignore[arg-type]
    hub._clients.add(alive)  # type: ignore[arg-type]

    await hub.broadcast({"type": "state", "data": {}})

    assert hub.client_count == 1
    assert alive.sent
