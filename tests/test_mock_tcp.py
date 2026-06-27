"""Integration tests for the mock vendor TCP server (no real hardware)."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np
import pytest_asyncio
from mock_server.server import MockVendorTCPServer


@pytest_asyncio.fixture
async def tcp_server() -> AsyncIterator[MockVendorTCPServer]:
    server = MockVendorTCPServer(port=0)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


async def _connect(server: MockVendorTCPServer) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets_port)
    banner = await reader.read(4096)
    assert banner.startswith(b"SPAD512S")
    return reader, writer


async def test_banner_and_system_info(tcp_server: MockVendorTCPServer) -> None:
    reader, writer = await _connect(tcp_server)
    writer.write(b"D")
    await writer.drain()
    text = (await reader.read(8192)).decode()
    # cSPAD parses info[5][18:] for the hardware flavour; must not be "1M".
    lines = text.split("\n")
    assert lines[5][18:] == "512"
    assert text.strip().endswith("DONE")
    writer.close()


async def test_intensity_binary_roundtrips(tcp_server: MockVendorTCPServer) -> None:
    reader, writer = await _connect(tcp_server)
    writer.write(b"PU,0")
    await writer.drain()
    await reader.read(8192)

    writer.write(b"I,8,100,1,0,0,0,1,512")
    await writer.drain()
    payload = await reader.readexactly(512 * 512 + 4)
    assert payload.endswith(b"DONE")

    frame = np.frombuffer(payload[:-4], dtype=np.uint8).reshape(512, 512)
    assert frame.shape == (512, 512)
    writer.close()


async def test_unknown_command_errors(tcp_server: MockVendorTCPServer) -> None:
    reader, writer = await _connect(tcp_server)
    writer.write(b"NOPE")
    await writer.drain()
    text = (await reader.read(8192)).decode()
    assert "ERROR" in text
    writer.close()


async def test_intensity_honors_non_512_roi_width(tcp_server: MockVendorTCPServer) -> None:
    # Regression: width is arg index 7 of the I command; a 256-wide ROI must
    # produce 512*256 bytes/frame (1 byte/px at 8-bit), not a 512-wide frame.
    reader, writer = await _connect(tcp_server)
    writer.write(b"PU,0")
    await writer.drain()
    await reader.read(8192)

    writer.write(b"I,8,100,1,0,0,0,1,256")
    await writer.drain()
    payload = await reader.readexactly(512 * 256 + 4)
    assert payload.endswith(b"DONE")
    assert len(payload) - 4 == 512 * 256
    writer.close()


async def test_gated_rejects_sub_six_bit_depth(tcp_server: MockVendorTCPServer) -> None:
    # Regression: gated does not support 1-bit; the mock normalizes to 8-bit,
    # so one gate step is 512*512 bytes (1 byte/px), not a packed 1-bit frame.
    reader, writer = await _connect(tcp_server)
    writer.write(b"PU,0")
    await writer.drain()
    await reader.read(8192)

    writer.write(b"G,1,100,1,1,18,0,5,0,0,0,0,0")
    await writer.drain()
    payload = await reader.readexactly(512 * 512 + 4)
    assert payload.endswith(b"DONE")
    assert len(payload) - 4 == 512 * 512
    writer.close()


async def test_fault_injected_acquisition_terminates_with_done(
    tcp_server: MockVendorTCPServer,
) -> None:
    # Regression: an injected failure during an acquisition must still terminate
    # with DONE so a read-until-DONE consumer does not hang; the payload carries
    # "ERROR" for detection.
    tcp_server.state.fail_after_n_commands(0)
    reader, writer = await _connect(tcp_server)

    writer.write(b"I,8,100,1,0,0,0,1,512")
    await writer.drain()
    buffer = bytearray()
    while not buffer.endswith(b"DONE"):
        chunk = await asyncio.wait_for(reader.read(65536), 2.0)
        assert chunk, "server closed without DONE terminator"
        buffer.extend(chunk)
    assert b"ERROR" in buffer
    writer.close()
