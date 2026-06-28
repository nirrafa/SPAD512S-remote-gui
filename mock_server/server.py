"""AsyncIO TCP server speaking the mock vendor cSPAD protocol.

Real clients (``cSPAD.py``, and later the bridge) connect here. The protocol
core in :mod:`mock_server.protocol` is shared with the in-process test harness.
"""
from __future__ import annotations

import asyncio

from mock_server.protocol import handle
from mock_server.state import MockState

BANNER = b"SPAD512S MockVendor 1.0\n"
_READ_SIZE = 8192
_WRITE_CHUNK = 1 << 20  # 1 MiB
_CHUNK_PACE_S = 0.003  # per-chunk pacing so multi-frame transfers take realistic time


class MockVendorTCPServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 9999,
                 state: MockState | None = None) -> None:
        self.host = host
        self.port = port
        self.state = state or MockState()
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._tasks: set[asyncio.Task[None]] = set()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        writer.write(BANNER)
        await writer.drain()
        self._clients.add(writer)
        try:
            while True:
                data = await reader.read(_READ_SIZE)
                if not data:
                    break
                command = data.decode("utf-8", errors="ignore")

                delay = self.state.take_delay()
                if delay:
                    await asyncio.sleep(delay)

                result = handle(command, self.state)
                if result.wire_bytes is not None:
                    # Stream large payloads in chunks with drain between, so the
                    # event loop stays responsive (a multi-frame acquisition does
                    # not block stop()/cancellation).
                    payload = result.wire_bytes
                    for offset in range(0, len(payload), _WRITE_CHUNK):
                        writer.write(payload[offset : offset + _WRITE_CHUNK])
                        await writer.drain()
                        if len(payload) > _WRITE_CHUNK:
                            await asyncio.sleep(_CHUNK_PACE_S)  # simulate transfer time
                    writer.write(b"DONE")
                else:
                    # Errors also terminate with DONE (text carries "ERROR")
                    # so read-until-DONE consumers never hang; see decoder.py.
                    writer.write(f"{result.text}\nDONE".encode())
                await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
            self._clients.discard(writer)
            if task is not None:
                self._tasks.discard(task)
            writer.close()

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    @property
    def sockets_port(self) -> int:
        """Actual bound port (useful when started with port 0)."""
        if self._server is None or not self._server.sockets:
            return self.port
        return int(self._server.sockets[0].getsockname()[1])

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        for writer in list(self._clients):
            writer.close()
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


async def run(host: str = "127.0.0.1", port: int = 9999) -> None:
    server = MockVendorTCPServer(host=host, port=port)
    await server.start()
    print(f"Mock vendor server listening on {host}:{server.sockets_port}")
    await server.serve_forever()
