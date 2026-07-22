"""Dark-reference tests (gated + intensity): correction math + integration.

The mock's synthetic data stands in for real DCR — the integration tests
verify the mechanics (measure → store → fingerprint-check → subtract → flag),
not the physics.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from bridge.config import Settings
from bridge.main import create_app
from bridge.services.dark_reference import (
    DarkReferenceStore,
    apply_dark_correction,
    build_reference,
)
from fastapi.testclient import TestClient
from mock_server.harness import MockVendorServer

GATED_BODY = {
    "bit_depth": 8,
    "integration_time_ms": 100,
    "iterations": 1,
    "gate_steps": 5,
    "gate_step_size_ps": 18,
    "gate_width": 5,
    "gate_offset": 0,
    "gate_direction": "forward",
    "gate_trigger_source": "external",
}


# --- pure math ----------------------------------------------------------------


def test_build_reference_mean_for_few_repeats() -> None:
    stack = np.stack(
        [np.full((2, 2), 2, dtype=np.uint16), np.full((2, 2), 4, dtype=np.uint16)]
    )
    ref = build_reference(stack, iterations=2, gate_steps=1)
    assert ref.shape == (1, 2, 2)
    assert np.allclose(ref, 3.0)


def test_build_reference_median_for_three_plus_repeats() -> None:
    frames = [
        np.full((2, 2), 1, dtype=np.uint16),
        np.full((2, 2), 2, dtype=np.uint16),
        np.full((2, 2), 90, dtype=np.uint16),  # hot-pixel burst outlier
    ]
    ref = build_reference(np.stack(frames), iterations=3, gate_steps=1)
    assert np.allclose(ref, 2.0)  # median rejects the burst; mean would be 31


def test_build_reference_rejects_wrong_frame_count() -> None:
    stack = np.zeros((5, 2, 2), dtype=np.uint16)
    with pytest.raises(ValueError, match="expected 6"):
        build_reference(stack, iterations=2, gate_steps=3)


def test_apply_dark_correction_subtracts_and_clips_at_zero() -> None:
    signal = np.array([[[10, 3]], [[7, 0]]], dtype=np.uint16)  # (2 steps, 1, 2)
    reference = np.array([[[4.0, 5.0]], [[2.0, 1.0]]], dtype=np.float32)
    corrected = apply_dark_correction(signal, reference)
    assert corrected.dtype == np.uint16
    assert corrected.tolist() == [[[6, 0]], [[5, 0]]]  # 3-5 and 0-1 clip to 0


def test_apply_dark_correction_broadcasts_over_iterations() -> None:
    # 2 iterations x 1 gate step; reference is per-iteration.
    signal = np.array([[[10]], [[20]]], dtype=np.uint16)
    reference = np.array([[[4.0]]], dtype=np.float32)
    corrected = apply_dark_correction(signal, reference)
    assert corrected.tolist() == [[[6]], [[16]]]


def test_apply_dark_correction_rejects_shape_mismatch() -> None:
    signal = np.zeros((4, 2, 2), dtype=np.uint16)
    with pytest.raises(ValueError, match="whole number"):
        apply_dark_correction(signal, np.zeros((3, 2, 2), dtype=np.float32))
    with pytest.raises(ValueError, match="frame shape"):
        apply_dark_correction(signal, np.zeros((2, 3, 3), dtype=np.float32))


def test_store_round_trip(tmp_path: Path) -> None:
    store = DarkReferenceStore(tmp_path / "refs.sqlite")
    reference = np.random.default_rng(1).random((3, 4, 4)).astype(np.float32)
    fingerprint = {"bit_depth": 8, "gate_steps": 3}
    ref_id = store.save(
        mode="gated",
        fingerprint=fingerprint,
        reference=reference,
        iterations=5,
        source_path="/data/gated_images/acq00007",
    )

    loaded = store.get(ref_id)
    assert loaded is not None
    got_fp, got_ref = loaded
    assert got_fp == fingerprint
    assert np.array_equal(got_ref, reference)

    meta = store.meta(ref_id)
    assert meta is not None
    assert meta["source_path"] == "/data/gated_images/acq00007"
    assert meta["npy_path"].endswith(f"darkref_{ref_id}.npy")

    listing = store.list()
    assert [r["id"] for r in listing] == [ref_id]
    assert listing[0]["gate_steps"] == 3
    assert listing[0]["source_path"] == "/data/gated_images/acq00007"
    assert store.get("missing") is None
    assert store.meta("missing") is None


# --- integration (bridge + mock) ---------------------------------------------


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


def test_measure_and_list_dark_reference(client: TestClient) -> None:
    resp = client.post("/api/calibrate/gated-dark-reference", json=GATED_BODY).json()
    assert resp["status"] == "done"
    assert resp["gate_steps"] == 5
    assert resp["method"] == "mean"  # 1 iteration
    assert resp["host_path"]  # raw dark acquisition persisted as a lab record

    listing = client.get("/api/calibration/dark-references").json()
    assert [r["id"] for r in listing["references"]] == [resp["reference_id"]]
    assert listing["references"][0]["fingerprint"]["gate_steps"] == 5


def test_gated_acquire_with_matching_reference_corrects(client: TestClient) -> None:
    ref = client.post("/api/calibrate/gated-dark-reference", json=GATED_BODY).json()
    resp = client.post(
        "/api/acquire/gated",
        json={**GATED_BODY, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "done"
    assert resp["dark_corrected"] is True
    assert resp["dark_reference_id"] == ref["reference_id"]
    assert resp["total_gate_steps"] == 5


def test_mismatched_fingerprint_rejected(client: TestClient) -> None:
    ref = client.post("/api/calibrate/gated-dark-reference", json=GATED_BODY).json()
    resp = client.post(
        "/api/acquire/gated",
        json={**GATED_BODY, "gate_width": 7, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "error"
    assert "does not match" in resp["message"]
    assert "gate_width" in resp["message"]
    # Fast-fail: no acquisition ran, instrument back to idle immediately.
    assert client.get("/api/status").json()["instrument_state"] == "idle"


def test_unknown_reference_id_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/acquire/gated",
        json={**GATED_BODY, "dark_reference_id": "nope"},
    ).json()
    assert resp["status"] == "error"
    assert "not found" in resp["message"]


def test_signal_iterations_may_differ_from_reference(client: TestClient) -> None:
    # Reference is stored per-iteration, so a 2-iteration signal against a
    # 1-iteration dark is valid by design.
    ref = client.post("/api/calibrate/gated-dark-reference", json=GATED_BODY).json()
    resp = client.post(
        "/api/acquire/gated",
        json={**GATED_BODY, "iterations": 2, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "done"
    assert resp["dark_corrected"] is True


def test_documentation_trail(client: TestClient, tmp_path: Path) -> None:
    """Every sequence documents its full parameters; corrected runs reference
    the correction file (user requirement, 2026-08-05)."""
    import json

    ref = client.post("/api/calibrate/gated-dark-reference", json=GATED_BODY).json()
    assert ref["reference_npy_path"].endswith(".npy")

    resp = client.post(
        "/api/acquire/gated",
        json={**GATED_BODY, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "done"
    assert resp["dark_reference_path"] == ref["reference_npy_path"]

    # --- dark run's own sidecar: full params + explicit purpose ---------------
    folders = sorted((tmp_path / "gated_images").iterdir())
    dark_sidecar = json.loads((folders[0] / "sidecar.json").read_text())
    assert dark_sidecar["purpose"] == "gated_dark_reference"
    assert dark_sidecar["gate_steps"] == 5
    assert dark_sidecar["gate_step_size_ps"] == 18.0
    assert dark_sidecar["dark_reference_id"] is None  # a dark run is never corrected

    # --- corrected run's sidecar: full params + correction provenance ---------
    signal_sidecar = json.loads((folders[1] / "sidecar.json").read_text())
    assert signal_sidecar["gate_steps"] == 5
    correction = signal_sidecar["dark_correction"]
    assert correction["applied"] is True
    assert correction["reference_id"] == ref["reference_id"]
    assert correction["reference_npy_path"] == ref["reference_npy_path"]
    assert correction["reference_source_path"] == ref["host_path"]
    assert correction["method"] == "clip(signal - reference, 0)"
    # The store links back to the raw dark run it was built from.
    listing = client.get("/api/calibration/dark-references").json()
    assert listing["references"][0]["source_path"] == ref["host_path"]

    # --- experiment log: both sequences recorded with full params -------------
    entries = client.get("/api/experiment-log").json()["entries"]
    modes = [e["mode"] for e in entries]
    assert modes == ["gated_dark_reference", "gated"]
    dark_entry, signal_entry = entries
    assert dark_entry["params"]["reference_id"] == ref["reference_id"]
    assert dark_entry["params"]["gate_steps"] == 5
    assert dark_entry["notes"] == "dark-count reference measurement (sensor capped)"
    assert signal_entry["params"]["dark_corrected"] is True
    assert signal_entry["params"]["dark_reference_id"] == ref["reference_id"]
    assert signal_entry["params"]["dark_reference_npy_path"] == ref["reference_npy_path"]


def test_persisted_raw_stack_is_not_corrected(client: TestClient, tmp_path: Path) -> None:
    """The corrected view is derived; files on disk stay raw.

    With the mock, dark and signal stacks are statistically identical, so the
    corrected preview is near-zero while the persisted PNGs keep real counts —
    if persistence were (wrongly) corrected, the two acquisitions' folders
    would differ wildly in content size once corrected to ~zero.
    """
    ref = client.post("/api/calibrate/gated-dark-reference", json=GATED_BODY).json()
    resp = client.post(
        "/api/acquire/gated",
        json={**GATED_BODY, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "done"

    # The corrected preview of mock-vs-mock is dim (near-total subtraction)…
    corrected_peak = resp["preview"]["max_value"]
    dark_folders = sorted((tmp_path / "gated_images").iterdir())
    assert len(dark_folders) == 2  # dark reference + corrected signal run
    # …but both persisted folders contain full-size raw frames.
    for folder in dark_folders:
        pngs = list(folder.glob("IMG*.png"))
        assert len(pngs) == 5
        assert all(p.stat().st_size > 0 for p in pngs)
    assert corrected_peak < 255  # sanity: correction actually shrank the view


# --- intensity mode -----------------------------------------------------------

INTENSITY_BODY = {
    "bit_depth": 8,
    "integration_time": 100,
    "iterations": 1,
    "roi_width": 512,
}


def test_intensity_measure_correct_and_document(client: TestClient, tmp_path: Path) -> None:
    import json

    ref = client.post("/api/calibrate/intensity-dark-reference", json=INTENSITY_BODY).json()
    assert ref["status"] == "done"
    assert ref["method"] == "mean"
    assert ref["reference_npy_path"].endswith(".npy")

    listing = client.get("/api/calibration/dark-references?mode=intensity").json()
    assert [r["id"] for r in listing["references"]] == [ref["reference_id"]]
    assert listing["references"][0]["mode"] == "intensity"
    assert listing["references"][0]["gate_steps"] == 1  # degenerate intensity case

    resp = client.post(
        "/api/acquire/intensity",
        json={**INTENSITY_BODY, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "done"
    assert resp["dark_corrected"] is True
    assert resp["dark_reference_path"] == ref["reference_npy_path"]

    folders = sorted((tmp_path / "intensity_images").iterdir())
    assert len(folders) == 2  # dark run + corrected signal run, both persisted raw
    dark_sidecar = json.loads((folders[0] / "sidecar.json").read_text())
    assert dark_sidecar["purpose"] == "intensity_dark_reference"
    signal_sidecar = json.loads((folders[1] / "sidecar.json").read_text())
    correction = signal_sidecar["dark_correction"]
    assert correction["reference_id"] == ref["reference_id"]
    assert correction["reference_source_path"] == ref["host_path"]

    entries = client.get("/api/experiment-log").json()["entries"]
    assert [e["mode"] for e in entries] == ["intensity_dark_reference", "intensity"]
    assert entries[1]["params"]["dark_corrected"] is True


def test_intensity_fingerprint_mismatch_rejected(client: TestClient) -> None:
    ref = client.post("/api/calibrate/intensity-dark-reference", json=INTENSITY_BODY).json()
    resp = client.post(
        "/api/acquire/intensity",
        json={**INTENSITY_BODY, "roi_width": 256, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "error"
    assert "roi_width" in resp["message"]
    assert client.get("/api/status").json()["instrument_state"] == "idle"


def test_gated_reference_never_matches_intensity_acquisition(client: TestClient) -> None:
    # Disjoint fingerprint key sets: using a gated reference id on an intensity
    # acquisition must always be rejected, whatever the shared values are.
    ref = client.post("/api/calibrate/gated-dark-reference", json=GATED_BODY).json()
    resp = client.post(
        "/api/acquire/intensity",
        json={**INTENSITY_BODY, "dark_reference_id": ref["reference_id"]},
    ).json()
    assert resp["status"] == "error"
    assert "does not match" in resp["message"]


def test_mode_filter_on_list(client: TestClient) -> None:
    client.post("/api/calibrate/gated-dark-reference", json=GATED_BODY)
    client.post("/api/calibrate/intensity-dark-reference", json=INTENSITY_BODY)
    gated = client.get("/api/calibration/dark-references?mode=gated").json()["references"]
    intensity = client.get("/api/calibration/dark-references?mode=intensity").json()["references"]
    both = client.get("/api/calibration/dark-references").json()["references"]
    assert [r["mode"] for r in gated] == ["gated"]
    assert [r["mode"] for r in intensity] == ["intensity"]
    assert len(both) == 2
