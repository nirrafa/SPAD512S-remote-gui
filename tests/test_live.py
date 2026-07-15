"""Live-view route regression tests (default suite, mock-backed).

Confirms the on-demand contract: a frame returns a preview, nothing is
persisted to data_root or the experiment log, and the busy guard applies like
any other acquisition.
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from bridge.config import Settings
from bridge.main import create_app
from fastapi.testclient import TestClient
from mock_server.harness import MockVendorServer


@pytest.fixture
def vendor() -> Iterator[MockVendorServer]:
    server = MockVendorServer()
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def client(vendor: MockVendorServer, tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        vendor_host="127.0.0.1", vendor_port=vendor.port, data_root=str(tmp_path)
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_live_frame_returns_preview(client: TestClient) -> None:
    resp = client.post("/api/live/frame", json={}).json()
    assert resp["status"] == "done"
    assert resp["preview"]["data"]


def test_live_frame_writes_nothing_to_disk(client: TestClient, tmp_path: Path) -> None:
    client.post("/api/live/frame", json={})
    client.post("/api/live/frame", json={})
    assert list(tmp_path.iterdir()) == []


def test_live_frame_not_logged(client: TestClient) -> None:
    client.post("/api/live/frame", json={})
    log = client.get("/api/experiment-log").json()
    assert log["entries"] == []


def test_live_frame_repeatable(client: TestClient) -> None:
    for _ in range(5):
        resp = client.post("/api/live/frame", json={}).json()
        assert resp["status"] == "done"


def test_live_frame_rejects_invalid_bit_depth(client: TestClient) -> None:
    resp = client.post("/api/live/frame", json={"bit_depth": 3}).json()
    assert resp["status"] == "error"


def test_live_frame_rejects_invalid_roi_width(client: TestClient) -> None:
    resp = client.post("/api/live/frame", json={"roi_width": 300}).json()
    assert resp["status"] == "error"


def test_live_frame_rejected_while_disconnected(
    client: TestClient, vendor: MockVendorServer
) -> None:
    vendor.stop()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if client.get("/api/status").json()["vendor_connected"] is False:
            break
        time.sleep(0.1)
    resp = client.post("/api/live/frame", json={}).json()
    assert resp["status"] == "error"
    assert "disconnected" in resp["message"]


def test_live_frame_busy_guard(client: TestClient) -> None:
    # A large multi-batch intensity acquisition returns `running` after its
    # short result-grace window (same pattern as
    # test_13::test_command_rejected_while_busy) while the background task
    # keeps the instrument busy; an immediate live-frame request must be
    # rejected, not interleaved on the single socket.
    client.post(
        "/api/acquire/intensity",
        json={"bit_depth": 8, "integration_time": 100, "iterations": 1000},
    )
    resp = client.post("/api/live/frame", json={}).json()
    assert resp["status"] == "error"
    assert resp["message"] == "instrument busy"
