"""Stream-desync self-healing (the first lab smoke test's Windows bug).

A stray text reply glued onto binary frame data surfaced as
"acquisition length mismatch: expected 262144, got 262170" and then poisoned
every later command. The client must recover by dropping + re-establishing
the connection in both desync situations:

1. a wrong-length acquisition payload (stray bytes inside a response), and
2. data arriving while idle (a response nobody asked for).
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator

import pytest
from bridge.protocol.client import ProtocolClient, ProtocolError

_INFO = (
    "serial master: M1\n"
    "serial slave: S1\n"
    "sw: 1\n"
    "fw: 1\n"
    "hw: 1\n"
    "flavour: 512\n"
    "intensity: 1\n"
    "gated: 1\n"
    "flim: 1\n"
    "DONE"
)


class _FakeVendor:
    """Minimal lockstep vendor: handshake + scripted acquire responses."""

    def __init__(self) -> None:
        self.server: asyncio.Server | None = None
        self.writers: list[asyncio.StreamWriter] = []
        self.connections = 0
        self.acquire_payload: bytes = b""

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        return int(self.server.sockets[0].getsockname()[1])

    async def _client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.connections += 1
        self.writers.append(writer)
        writer.write(b"fake vendor\n")
        await writer.drain()
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    return
                command = data.decode()
                if command.startswith("D"):
                    writer.write(_INFO.encode())
                else:
                    writer.write(self.acquire_payload)
                await writer.drain()
        except (ConnectionResetError, OSError):
            return

    async def stop(self) -> None:
        for writer in self.writers:
            writer.close()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()


@pytest.fixture
async def vendor_and_client() -> Iterator[tuple[_FakeVendor, ProtocolClient]]:
    vendor = _FakeVendor()
    port = await vendor.start()
    client = ProtocolClient("127.0.0.1", port, read_timeout=2.0)
    await client.start()
    deadline = time.monotonic() + 5.0
    while not client.connected and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert client.connected
    yield vendor, client
    await client.stop()
    await vendor.stop()


async def test_length_mismatch_resets_connection(vendor_and_client) -> None:
    vendor, client = vendor_and_client
    # The lab bug in miniature: a stray text reply prepended to the frame data.
    stray = b"Pileup correction off\nDONE"
    frames = b"\x01" * 8
    vendor.acquire_payload = stray + frames + b"DONE"

    with pytest.raises(ProtocolError, match="length mismatch"):
        await client.send_acquire("I,8,...", expected_bytes=8)

    # The connection was dropped (desync cannot persist)…
    assert client.connected is False
    # …and auto-reconnect restores a clean stream that then works.
    vendor.acquire_payload = frames + b"DONE"
    deadline = time.monotonic() + 5.0
    while not client.connected and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert client.connected
    assert await client.send_acquire("I,8,...", expected_bytes=8) == frames


async def test_unsolicited_idle_data_triggers_reconnect(vendor_and_client) -> None:
    vendor, client = vendor_and_client
    before = vendor.connections

    # Lockstep protocols never deliver data while idle — this means desync.
    vendor.writers[-1].write(b"?")
    await vendor.writers[-1].drain()

    deadline = time.monotonic() + 5.0
    while vendor.connections == before and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert vendor.connections > before  # dropped and re-established

    deadline = time.monotonic() + 5.0
    while not client.connected and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert client.connected
    vendor.acquire_payload = b"\x02" * 4 + b"DONE"
    assert await client.send_acquire("I,...", expected_bytes=4) == b"\x02" * 4
