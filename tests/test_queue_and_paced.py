"""Acquisition queue + paced (cool-off) gated tests, mock-backed."""
from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from bridge.config import Settings
from bridge.main import create_app
from fastapi.testclient import TestClient
from mock_server.harness import MockVendorServer

GATED = {
    "bit_depth": 8,
    "integration_time_ms": 50,
    "iterations": 1,
    "gate_steps": 4,
    "gate_step_size_ps": 18,
    "gate_width": 5,
    "gate_offset": 0,
    "gate_direction": "forward",
    "gate_trigger_source": "external",
}
INTENSITY = {"bit_depth": 8, "integration_time": 50, "iterations": 1, "roi_width": 512}


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


def _wait_queue_done(client: TestClient, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get("/api/queue/status").json()
        if status["total"] > 0 and not status["running"]:
            return status
        time.sleep(0.2)
    raise AssertionError("queue did not finish in time")


# --- queue --------------------------------------------------------------------


def test_mixed_series_runs_and_documents(client: TestClient, tmp_path: Path) -> None:
    """The user's exact ask: '2 gated then 3 intensity', send it, come back."""
    resp = client.post(
        "/api/queue/run",
        json={
            "items": [
                {"mode": "gated", "params": GATED, "repeat": 2},
                {"mode": "intensity", "params": INTENSITY, "repeat": 3},
            ]
        },
    ).json()
    assert resp == {"status": "started", "total": 5}

    status = _wait_queue_done(client)
    assert [i["status"] for i in status["items"]] == ["done"] * 5
    assert [i["mode"] for i in status["items"]] == ["gated"] * 2 + ["intensity"] * 3
    assert all(i["host_path"] for i in status["items"])

    # Every run persisted + logged with full params.
    assert len(list((tmp_path / "gated_images").iterdir())) == 2
    assert len(list((tmp_path / "intensity_images").iterdir())) == 3
    entries = client.get("/api/experiment-log").json()["entries"]
    assert [e["mode"] for e in entries] == ["gated"] * 2 + ["intensity"] * 3
    assert all(e["params"]["queued"] is True for e in entries)
    assert entries[0]["params"]["gate_steps"] == 4


def test_queue_rejects_bad_input(client: TestClient) -> None:
    assert (
        client.post("/api/queue/run", json={"items": []}).json()["message"]
        == "queue is empty"
    )
    bad_mode = client.post(
        "/api/queue/run", json={"items": [{"mode": "flim", "params": {}}]}
    ).json()
    assert "unsupported mode" in bad_mode["message"]


def test_queue_busy_while_running(client: TestClient) -> None:
    first = client.post(
        "/api/queue/run",
        json={"items": [{"mode": "intensity", "params": INTENSITY, "repeat": 3}]},
    ).json()
    assert first["status"] == "started"
    second = client.post(
        "/api/queue/run",
        json={"items": [{"mode": "intensity", "params": INTENSITY}]},
    ).json()
    assert second == {"status": "error", "message": "instrument busy"}
    _wait_queue_done(client)


def test_queue_stop_skips_remaining(client: TestClient) -> None:
    client.post(
        "/api/queue/run",
        json={"items": [{"mode": "intensity", "params": INTENSITY, "repeat": 10}]},
    )
    client.post("/api/acquire/stop")
    status = _wait_queue_done(client)
    statuses = {i["status"] for i in status["items"]}
    assert "skipped" in statuses  # the tail never ran
    assert statuses <= {"done", "aborted", "skipped"}


# --- paced gated (cool-off) ---------------------------------------------------


def test_paced_gated_matches_continuous_layout(client: TestClient, tmp_path: Path) -> None:
    continuous = client.post("/api/acquire/gated", json=GATED).json()
    paced = client.post("/api/acquire/gated", json={**GATED, "cooloff_s": 0.05}).json()

    assert paced["status"] == "done"
    assert paced["cooloff_s"] == 0.05
    assert paced["total_gate_steps"] == continuous["total_gate_steps"] == 4
    assert paced["total_frames"] == continuous["total_frames"] == 4
    assert paced["previews_sent"] == 4
    assert paced["bytes"] == continuous["bytes"]

    # Identical on-disk layout: same PNG count, sidecar records the pacing.
    import json

    folders = sorted((tmp_path / "gated_images").iterdir())
    assert len(folders) == 2
    for folder in folders:
        assert len(list(folder.glob("IMG*.png"))) == 4
    paced_sidecar = json.loads((folders[1] / "sidecar.json").read_text())
    assert paced_sidecar["cooloff_s"] == 0.05


def test_paced_gated_actually_paces(client: TestClient) -> None:
    fast = time.monotonic()
    client.post("/api/acquire/gated", json=GATED)
    fast = time.monotonic() - fast

    slow = time.monotonic()
    client.post("/api/acquire/gated", json={**GATED, "cooloff_s": 0.4})
    slow = time.monotonic() - slow
    # 3 sleeps of 0.4 s between 4 steps ≈ 1.2 s extra.
    assert slow > fast + 1.0


def test_continuous_reference_rejected_for_paced_acquisition(client: TestClient) -> None:
    ref = client.post("/api/calibrate/gated-dark-reference", json=GATED).json()
    assert ref["status"] == "done"
    resp = client.post(
        "/api/acquire/gated",
        json={**GATED, "cooloff_s": 0.05, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "error"
    assert "cooloff_s" in resp["message"]  # thermal state differs — must not match


def test_paced_acquisition_with_paced_reference_corrects(client: TestClient) -> None:
    paced_body = {**GATED, "cooloff_s": 0.05}
    ref = client.post("/api/calibrate/gated-dark-reference", json=paced_body).json()
    assert ref["status"] == "done"
    resp = client.post(
        "/api/acquire/gated",
        json={**paced_body, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "done"
    assert resp["dark_corrected"] is True


def test_paced_gated_in_queue(client: TestClient) -> None:
    resp = client.post(
        "/api/queue/run",
        json={"items": [{"mode": "gated", "params": {**GATED, "cooloff_s": 0.05}}]},
    ).json()
    assert resp["status"] == "started"
    status = _wait_queue_done(client)
    assert status["items"][0]["status"] == "done"
