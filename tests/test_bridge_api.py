"""Bridge REST/reconnect regression tests (default suite, mock-backed)."""
from __future__ import annotations

import time
from collections.abc import Iterator

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
def client(vendor: MockVendorServer, tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        vendor_host="127.0.0.1", vendor_port=vendor.port, data_root=str(tmp_path)
    )
    with TestClient(create_app(settings)) as test_client:
        _wait_connected(test_client, expected=True)
        yield test_client


def _wait_connected(client: TestClient, *, expected: bool, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get("/api/status").json()["vendor_connected"] is expected:
            return True
        time.sleep(0.1)
    return client.get("/api/status").json()["vendor_connected"] is expected


def test_status_connected(client: TestClient) -> None:
    body = client.get("/api/status").json()
    assert body["vendor_connected"] is True
    assert body["instrument_state"] == "idle"


def test_system_info_shape(client: TestClient) -> None:
    info = client.get("/api/system/info").json()
    assert info["sensor_size"] == 512
    assert info["enabled_features"] == {"intensity": True, "gated": True, "flim": True}
    assert 8 in info["valid_bit_depths"]


def test_triggers(client: TestClient) -> None:
    diag = client.get("/api/system/triggers").json()
    assert diag["laser_frequency_hz"] > 0
    assert diag["trigger_valid"] is True


def test_intensity_round_trip(client: TestClient) -> None:
    resp = client.post(
        "/api/acquire/intensity",
        json={"bit_depth": 8, "integration_time": 100, "iterations": 1, "roi_width": 512},
    ).json()
    assert resp["status"] == "done"
    assert resp["bytes"] == 512 * 512


def test_reconnect_cycle(client: TestClient, vendor: MockVendorServer) -> None:
    vendor.stop()
    assert _wait_connected(client, expected=False)
    vendor.start()
    assert _wait_connected(client, expected=True, timeout=15)


def test_intensity_rejected_while_disconnected(
    client: TestClient, vendor: MockVendorServer
) -> None:
    vendor.stop()
    assert _wait_connected(client, expected=False)
    resp = client.post(
        "/api/acquire/intensity", json={"bit_depth": 8, "integration_time": 100}
    ).json()
    assert resp["status"] == "error"
    assert "disconnected" in resp["message"].lower()


def test_invalid_roi_width_rejected_without_desync(client: TestClient) -> None:
    # Review finding #2: an out-of-range roi_width must be rejected before it
    # reaches the vendor, and must not desync the stream for later commands.
    bad = client.post(
        "/api/acquire/intensity",
        json={"bit_depth": 8, "integration_time": 100, "roi_width": 300},
    ).json()
    assert bad["status"] == "error"
    assert "roi_width" in bad["message"]

    # The connection is still healthy and in sync.
    diag = client.get("/api/system/triggers").json()
    assert diag["laser_frequency_hz"] > 0
    ok = client.post(
        "/api/acquire/intensity",
        json={"bit_depth": 8, "integration_time": 100, "roi_width": 512},
    ).json()
    assert ok["status"] == "done"


def test_invalid_bit_depth_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/acquire/intensity",
        json={"bit_depth": 5, "integration_time": 100, "roi_width": 512},
    ).json()
    assert resp["status"] == "error"
    assert "bit_depth" in resp["message"]


