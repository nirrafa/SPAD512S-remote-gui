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


class MockVendorTCPServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 9999,
                 state: MockState | None = None) -> None:
        self.host = host
        self.port = port
        self.state = state or MockState()
        self._server: asyncio.Server | None = None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.write(BANNER)
        await writer.drain()
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
                    writer.write(result.wire_bytes + b"DONE")
                elif result.is_error:
                    writer.write(f"{result.text}\n".encode())
                else:
                    writer.write(f"{result.text}\nDONE".encode())
                await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
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
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


async def run(host: str = "127.0.0.1", port: int = 9999) -> None:
    server = MockVendorTCPServer(host=host, port=port)
    await server.start()
    print(f"Mock vendor server listening on {host}:{server.sockets_port}")
    await server.serve_forever()
