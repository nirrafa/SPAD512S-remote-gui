"""
PRD §8 — Reproducibility & Workflow

Presets, experiment log, sample/experiment naming, re-run from history.
"""
import pytest


class TestPresets:

    def test_save_preset(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/presets", json={
            "name": "standard_intensity",
            "mode": "intensity",
            "params": sample_intensity_params,
        })
        assert resp["status"] == "ok"
        assert "preset_id" in resp

    def test_load_preset(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/presets", json={
            "name": "standard_intensity",
            "mode": "intensity",
            "params": sample_intensity_params,
        })
        presets = bridge_client.get("/api/presets?mode=intensity")
        preset = next(p for p in presets if p["name"] == "standard_intensity")
        assert preset["params"]["bit_depth"] == sample_intensity_params["bit_depth"]

    def test_preset_per_mode(self, bridge_client, sample_intensity_params, sample_gated_params):
        bridge_client.post("/api/presets", json={
            "name": "preset_int", "mode": "intensity", "params": sample_intensity_params,
        })
        bridge_client.post("/api/presets", json={
            "name": "preset_gated", "mode": "gated", "params": sample_gated_params,
        })
        int_presets = bridge_client.get("/api/presets?mode=intensity")
        gated_presets = bridge_client.get("/api/presets?mode=gated")
        assert any(p["name"] == "preset_int" for p in int_presets)
        assert any(p["name"] == "preset_gated" for p in gated_presets)

    def test_delete_preset(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/presets", json={
            "name": "to_delete", "mode": "intensity", "params": sample_intensity_params,
        })
        del_resp = bridge_client.delete(f"/api/presets/{resp['preset_id']}")
        assert del_resp["status"] == "ok"


class TestExperimentLog:

    def test_acquisition_logged(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log")
        assert len(log["entries"]) > 0

    def test_log_entry_contains_parameters(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log")
        entry = log["entries"][-1]
        assert entry["mode"] == "intensity"
        assert "params" in entry

    def test_log_entry_contains_result_path(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log")
        entry = log["entries"][-1]
        assert "result_path" in entry

    def test_log_entry_contains_calibration_state(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log")
        entry = log["entries"][-1]
        assert "calibration_state" in entry

    def test_log_entry_contains_temperatures(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log")
        entry = log["entries"][-1]
        assert "temperatures" in entry

    def test_log_entry_contains_timestamp(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log")
        entry = log["entries"][-1]
        assert "timestamp" in entry

    def test_log_searchable(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params,
            "sample_name": "QD_batch_42",
        })
        results = bridge_client.get("/api/experiment-log?search=QD_batch_42")
        assert len(results["entries"]) > 0

    def test_log_browsable(self, bridge_client, sample_intensity_params):
        for _ in range(3):
            bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log?limit=2&offset=0")
        assert len(log["entries"]) == 2


class TestSampleExperimentNaming:

    def test_sample_name_in_file_organization(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params,
            "sample_name": "CdSe_QD",
            "experiment_name": "bleaching_test",
        })
        assert "CdSe_QD" in resp["host_path"] or "bleaching_test" in resp["host_path"]

    def test_notes_attached_to_acquisition(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params,
            "notes": "First run after realignment",
        })
        log = bridge_client.get("/api/experiment-log")
        entry = log["entries"][-1]
        assert entry["notes"] == "First run after realignment"


class TestRerunFromHistory:

    def test_rerun_identical(self, bridge_client, sample_intensity_params):
        """One click to repeat a past acquisition with identical parameters."""
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log")
        entry_id = log["entries"][-1]["id"]
        resp = bridge_client.post(f"/api/experiment-log/{entry_id}/rerun")
        assert resp["status"] == "done"

    def test_rerun_with_tweaks(self, bridge_client, sample_intensity_params):
        """Re-run a past acquisition with modified parameters."""
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        log = bridge_client.get("/api/experiment-log")
        entry_id = log["entries"][-1]["id"]
        resp = bridge_client.post(f"/api/experiment-log/{entry_id}/rerun", json={
            "overrides": {"integration_time": 200},
        })
        assert resp["status"] == "done"
