"""Async TCP client for the vendor cSPAD protocol.

Owns the single connection to the vendor (or mock) server. Commands are
serialized through an asyncio lock; between commands an idle EOF watcher detects
passive disconnects so ``/api/status`` reflects reality without polling the
hardware. A background task auto-reconnects with exponential backoff.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from bridge.protocol import commands
from bridge.protocol.decoder import SystemInfo, parse_system_info

_BREAKDOWN_START = (
    "The breakdown calibration process will start soon.",
    "The breakdown calibration process has started.",
)
_BREAKDOWN_DONE = "The breakdown is around"

StateCallback = Callable[[bool], Awaitable[None]]


class NotConnectedError(RuntimeError):
    """Raised when a command is attempted while the vendor is disconnected."""


class ProtocolError(RuntimeError):
    """Raised when the vendor returns an ERROR frame or an unexpected payload.

    Distinct from :class:`NotConnectedError`: the connection is healthy, so the
    caller should surface the error rather than trigger a reconnect.
    """


class ProtocolClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        read_timeout: float = 10.0,
        connect_timeout: float = 5.0,
        max_backoff: float = 4.0,
        on_state_change: StateCallback | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.read_timeout = read_timeout
        self.connect_timeout = connect_timeout
        self.max_backoff = max_backoff
        self._on_state_change = on_state_change

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._lock = asyncio.Lock()
        self._idle_task: asyncio.Task[None] | None = None
        self._maintain_task: asyncio.Task[None] | None = None
        self._stopping = False
        self.system_info: SystemInfo | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._connect(), self.connect_timeout)
        self._maintain_task = asyncio.create_task(self._maintain())

    async def stop(self) -> None:
        self._stopping = True
        tasks = [t for t in (self._maintain_task, self._idle_task) if t is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(BaseException):
                await task
        self._maintain_task = None
        self._idle_task = None
        if self._writer is not None:
            self._writer.close()
        self._reader = None
        self._writer = None
        self._connected = False

    # --- connection lifecycle -------------------------------------------------

    async def _maintain(self) -> None:
        backoff = 0.5
        while not self._stopping:
            if self._connected:
                await asyncio.sleep(0.2)
                continue
            try:
                await asyncio.wait_for(self._connect(), self.connect_timeout)
                backoff = 0.5
            except (TimeoutError, OSError, ValueError):
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

    async def _connect(self) -> None:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        await reader.readline()  # welcome banner

        writer.write(commands.info().encode())
        await writer.drain()
        first = await self._read_text(reader)
        if any(phrase in first for phrase in _BREAKDOWN_START):
            await self._await_breakdown(reader)

        writer.write(commands.info().encode())
        await writer.drain()
        info_text = await self._read_text(reader)

        self._reader = reader
        self._writer = writer
        self.system_info = parse_system_info(info_text)
        await self._set_connected(True)
        self._start_idle_watch()

    async def _await_breakdown(self, reader: asyncio.StreamReader) -> None:
        while True:
            chunk = await self._read_text(reader)
            if _BREAKDOWN_DONE in chunk:
                return

    async def _teardown(self) -> None:
        self._cancel_idle()
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _handle_disconnect(self) -> None:
        if not self._connected:
            return
        await self._set_connected(False)
        await self._teardown()

    async def reset(self) -> None:
        """Force-drop the connection so ``_maintain`` reconnects.

        Used after a command times out mid-flight: the socket has a pending
        response, so the stream is desynced and must be re-established.
        """
        await self._handle_disconnect()

    async def _set_connected(self, value: bool) -> None:
        self._connected = value
        if self._on_state_change is not None:
            await self._on_state_change(value)

    # --- idle EOF watcher -----------------------------------------------------

    def _start_idle_watch(self) -> None:
        self._idle_task = asyncio.create_task(self._idle_watch())

    def _cancel_idle(self) -> None:
        if self._idle_task is not None:
            self._idle_task.cancel()
            self._idle_task = None

    async def _idle_watch(self) -> None:
        reader = self._reader
        if reader is None:  # disconnected before this task ran
            return
        try:
            data = await reader.read(1)
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError):
            await self._handle_disconnect()
            return
        if data == b"":  # peer closed the connection
            await self._handle_disconnect()

    # --- command I/O ----------------------------------------------------------

    async def send_command(self, command: str) -> str:
        async with self._lock:
            writer, reader = self._require_connection()
            self._cancel_idle()
            try:
                writer.write(command.encode())
                await writer.drain()
                text = await self._read_text(reader)
            except (TimeoutError, OSError, ConnectionError) as exc:
                await self._handle_disconnect()
                raise NotConnectedError("vendor disconnected during command") from exc
            self._start_idle_watch()
            if text.lstrip().startswith("ERROR"):
                raise ProtocolError(text.strip())
            return text

    async def send_acquire(self, command: str, expected_bytes: int | None = None) -> bytes:
        async with self._lock:
            writer, reader = self._require_connection()
            self._cancel_idle()
            try:
                writer.write(command.encode())
                await writer.drain()
                data = await self._read_binary(reader, expected_bytes)
            except (TimeoutError, OSError, ConnectionError) as exc:
                await self._handle_disconnect()
                raise NotConnectedError("vendor disconnected during acquisition") from exc
            self._start_idle_watch()
            return data

    def _require_connection(self) -> tuple[asyncio.StreamWriter, asyncio.StreamReader]:
        if not self._connected or self._writer is None or self._reader is None:
            raise NotConnectedError("vendor disconnected")
        return self._writer, self._reader

    async def _read_text(self, reader: asyncio.StreamReader) -> str:
        buffer = bytearray()
        while True:
            chunk = await asyncio.wait_for(reader.read(8192), self.read_timeout)
            if not chunk:
                raise ConnectionError("EOF during text read")
            buffer.extend(chunk)
            tail = buffer.strip()
            if tail.endswith(b"DONE") or tail.startswith(b"ERROR"):
                break
        return buffer.decode("utf-8", errors="ignore")

    async def _read_binary(
        self, reader: asyncio.StreamReader, expected_bytes: int | None
    ) -> bytes:
        """Read an acquisition payload terminated by ``DONE``.

        Always terminates on the ``DONE`` sentinel rather than a fixed length, so
        a short ``ERROR`` frame surfaces as a :class:`ProtocolError` instead of
        stalling until the read timeout and masquerading as a disconnect.
        ``expected_bytes`` (when known) gates premature termination on binary
        data that happens to end in ``DONE`` and is validated afterwards.
        """
        target = None if expected_bytes is None else expected_bytes + 4
        buffer = bytearray()
        while True:
            if buffer.endswith(b"DONE") and (
                target is None
                or len(buffer) >= target
                or buffer[:-4].lstrip().startswith(b"ERROR")
            ):
                break
            chunk = await asyncio.wait_for(reader.read(65536), self.read_timeout)
            if not chunk:
                raise ConnectionError("EOF during binary read")
            buffer.extend(chunk)

        payload = bytes(buffer[:-4])
        if payload.lstrip().startswith(b"ERROR"):
            raise ProtocolError(payload.decode("utf-8", errors="ignore").strip())
        if expected_bytes is not None and len(payload) != expected_bytes:
            raise ProtocolError(
                f"acquisition length mismatch: expected {expected_bytes}, got {len(payload)}"
            )
        return payload
