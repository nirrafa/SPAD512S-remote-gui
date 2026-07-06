"""Regression tests for the post-review safety fixes (B-27..B-31)."""
from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from bridge.config import Settings
from bridge.core.instrument import InstrumentState, InstrumentStatus
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
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if test_client.get("/api/status").json()["vendor_connected"]:
                break
            time.sleep(0.1)
        yield test_client


def test_stopping_counts_as_busy() -> None:
    """B-27: a STOPPING instrument must still reject a new acquisition."""
    inst = InstrumentState()
    assert not inst.is_busy
    inst._status = InstrumentStatus.STOPPING  # simulate mid-abort window
    assert inst.is_busy


def test_vex_hard_ceiling_rejected_even_with_confirm(client: TestClient) -> None:
    """B-30: an absurd Vex is refused outright, not merely gated on confirmation."""
    resp = client.post("/api/settings/vex", json={"vex": 100.0, "confirm": True}).json()
    assert resp["status"] == "error"
    assert "ceiling" in resp["message"].lower()
    assert not resp.get("requires_confirmation")


def test_config_rejects_nonpositive_poll_interval(client: TestClient) -> None:
    """B-29: poll_interval_s=0 would busy-loop the socket; must be rejected."""
    resp = client.put("/api/health/config", json={"poll_interval_s": 0})
    assert resp.status_code == 422


def test_health_config_get_put_symmetric(client: TestClient) -> None:
    """B-29: missing_laser_hz is now returned and settable."""
    cfg = client.get("/api/health/config").json()
    assert "missing_laser_hz" in cfg
    client.put("/api/health/config", json={"missing_laser_hz": 2.0})
    assert client.get("/api/health/config").json()["missing_laser_hz"] == 2.0


def test_auto_protect_actually_lowers_vex(client: TestClient, vendor: MockVendorServer) -> None:
    """B-28: over-max Vex triggers an actual set_vex to the ceiling, not just a flag."""
    vex_max = client.get("/api/health/config").json()["vex_max"]
    vendor.set_voltage("vex", vex_max + 5.0)

    first = client.get("/api/health/readings").json()
    assert first["vex_reduced"] is True

    # The reduction was commanded to the device: a fresh read reflects the safe bias.
    second = client.get("/api/health/readings").json()
    assert second["vex"] <= vex_max


def test_readings_expose_validity_and_timestamp(client: TestClient) -> None:
    """B-31: readings carry a validity flag + timestamp rather than looking live forever."""
    r = client.get("/api/health/readings").json()
    assert r["readings_valid"] is True
    assert isinstance(r["last_updated"], (int, float))
