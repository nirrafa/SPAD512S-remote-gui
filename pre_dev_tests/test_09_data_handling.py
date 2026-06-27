"""
PRD §6 — Data Handling & Formats

File organization, reducer integration, JSON sidecar, and preview delivery.
"""
import pytest
import json


class TestSavePath:

    def test_set_save_path(self, bridge_client):
        resp = bridge_client.post("/api/settings/save-path", json={
            "path": "D:\\lab_data\\experiment_001",
        })
        assert resp["status"] == "ok"

    def test_save_path_used_for_acquisition(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/settings/save-path", json={
            "path": "D:\\lab_data\\experiment_001",
        })
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        assert resp["host_path"].startswith("D:\\lab_data\\experiment_001")


class TestFileOrganization:

    def test_intensity_folder_layout(self, bridge_client, sample_intensity_params):
        """Intensity data saved under data/intensity_images/acqXXXXX/."""
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        assert "intensity_images" in resp["host_path"]
        assert "acq" in resp["host_path"]

    def test_gated_folder_layout(self, bridge_client, sample_gated_params):
        resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
        assert "gated_images" in resp["host_path"]
        assert "acq" in resp["host_path"]

    def test_png_files_saved_with_metadata(self, bridge_client, sample_intensity_params):
        """Vendor saves IMGxxxxx.png with embedded metadata fields."""
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        files = bridge_client.get(f"/api/data/list?path={resp['host_path']}")
        png_files = [f for f in files if f.endswith(".png")]
        assert len(png_files) > 0


class TestReducerIntegration:

    def test_reducer_produces_meta_json(self, bridge_client, sample_intensity_params):
        """After acquisition + reducer, meta_acqXXXXX.json exists."""
        resp = bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params,
            "run_reducer": True,
        })
        assert resp["reducer_output"]["meta_json"] is not None

    def test_reducer_produces_movie_npy(self, bridge_client, sample_intensity_params):
        """After acquisition + reducer, movie_arr_acqXXXXX.npy exists."""
        resp = bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params,
            "run_reducer": True,
        })
        assert resp["reducer_output"]["movie_npy"] is not None

    def test_movie_npy_shape(self, bridge_client, sample_intensity_params):
        """movie_arr is a 3D array: nframes × x × y."""
        resp = bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params,
            "iterations": 5,
            "run_reducer": True,
        })
        shape = resp["reducer_output"]["movie_npy_shape"]
        assert len(shape) == 3
        assert shape[0] == 5  # nframes

    def test_reducer_output_compatible_with_pipeline(self, bridge_client, sample_intensity_params):
        """Produced files must be loadable by 512^2_*.py and SEP_D.py."""
        resp = bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params,
            "run_reducer": True,
        })
        assert resp["reducer_output"]["pipeline_compatible"] is True


class TestJSONSidecar:

    def test_sidecar_written_per_acquisition(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        assert "sidecar_path" in resp

    def test_sidecar_contains_full_params(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        sidecar = bridge_client.get(f"/api/data/sidecar?path={resp['sidecar_path']}")
        assert sidecar["bit_depth"] == sample_intensity_params["bit_depth"]
        assert sidecar["integration_time_ms"] == sample_intensity_params["integration_time_ms"]

    def test_sidecar_contains_calibration_state(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        sidecar = bridge_client.get(f"/api/data/sidecar?path={resp['sidecar_path']}")
        assert "calibration_state" in sidecar

    def test_sidecar_contains_temperatures(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        sidecar = bridge_client.get(f"/api/data/sidecar?path={resp['sidecar_path']}")
        assert "temperatures" in sidecar

    def test_sidecar_contains_timestamps(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        sidecar = bridge_client.get(f"/api/data/sidecar?path={resp['sidecar_path']}")
        assert "timestamp_start" in sidecar
        assert "timestamp_end" in sidecar

    def test_sidecar_contains_sample_experiment_tags(self, bridge_client):
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1,
            "sample_name": "QD_sample_A",
            "experiment_name": "lifetime_study_001",
        })
        sidecar = bridge_client.get(f"/api/data/sidecar?path={resp['sidecar_path']}")
        assert sidecar["sample_name"] == "QD_sample_A"
        assert sidecar["experiment_name"] == "lifetime_study_001"


class TestPreviewDelivery:

    def test_preview_sent_over_websocket(self, bridge_client, sample_intensity_params):
        ws = bridge_client.ws_connect("/ws")
        bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        msg = ws.receive(timeout=10)
        assert msg["type"] == "preview_frame"

    def test_preview_is_downsampled(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        preview = resp["preview"]
        assert preview["width"] * preview["height"] < 512 * 512

    def test_full_data_download_on_demand(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        download = bridge_client.get(f"/api/data/download?path={resp['host_path']}")
        assert download is not None
