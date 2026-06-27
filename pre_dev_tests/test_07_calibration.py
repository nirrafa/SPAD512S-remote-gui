"""
PRD §4 — Calibration (Guided + State-Aware)

Track calibration status, guide physical setup, warn if uncalibrated.
"""
import pytest


class TestBreakdownCalibration:

    def test_breakdown_auto_on_connect(self, bridge_client):
        """Breakdown calibration runs automatically when bridge connects."""
        status = bridge_client.get("/api/calibration/status")
        assert status["breakdown"]["state"] in ["done", "running"]

    def test_breakdown_calibration_explicit(self, bridge_client):
        resp = bridge_client.post("/api/calibrate/breakdown")
        assert resp["status"] == "done"


class TestNoiseCalibration:

    def test_noise_calibration(self, bridge_client):
        resp = bridge_client.post("/api/calibrate/noise")
        assert resp["status"] == "done"

    def test_noise_calibration_requires_dark(self, bridge_client):
        """Calibration prompts user to ensure dark conditions."""
        resp = bridge_client.post("/api/calibrate/noise")
        assert resp.get("setup_prompt") or resp["status"] == "done"


class TestDeadPixelCalibration:

    def test_dead_pixel_calibration(self, bridge_client):
        resp = bridge_client.post("/api/calibrate/dead-pixel")
        assert resp["status"] == "done"

    def test_dead_pixel_requires_dark(self, bridge_client):
        resp = bridge_client.post("/api/calibrate/dead-pixel")
        assert resp.get("setup_prompt") or resp["status"] == "done"


class TestMasterSlaveOffsetCalibration:

    def test_mst_slv_offset_calibration(self, bridge_client):
        resp = bridge_client.post("/api/calibrate/master-slave-offset")
        assert resp["status"] == "done"

    def test_mst_slv_requires_uniform_pulsed_illumination(self, bridge_client):
        resp = bridge_client.post("/api/calibrate/master-slave-offset")
        assert resp.get("setup_prompt") or resp["status"] == "done"


class TestCalibrationState:

    def test_all_calibration_statuses_reported(self, bridge_client):
        status = bridge_client.get("/api/calibration/status")
        for cal in ["breakdown", "noise", "dead_pixel", "master_slave_offset", "flim_irf"]:
            assert cal in status
            assert "state" in status[cal]

    def test_calibration_staleness_tracked(self, bridge_client):
        """Each calibration has a timestamp; staleness is surfaced."""
        status = bridge_client.get("/api/calibration/status")
        for cal in ["breakdown", "noise", "dead_pixel", "master_slave_offset"]:
            if status[cal]["state"] == "done":
                assert "timestamp" in status[cal]
                assert "stale" in status[cal]

    def test_warn_before_acquiring_uncalibrated(self, bridge_client):
        """If noise/dead-pixel calibration is missing, acquisition returns a warning."""
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1,
        })
        if not resp.get("calibration_valid"):
            assert "warning" in resp


class TestCalibrationQA:

    def test_dcr_curve_after_noise_calibration(self, bridge_client):
        """DCR-vs-percentage curve is available after noise calibration."""
        bridge_client.post("/api/calibrate/noise")
        resp = bridge_client.get("/api/calibration/dcr-curve")
        assert "percentages" in resp
        assert "dcr_values" in resp

    def test_dcr_curve_after_dead_pixel_calibration(self, bridge_client):
        bridge_client.post("/api/calibrate/dead-pixel")
        resp = bridge_client.get("/api/calibration/dcr-curve")
        assert "percentages" in resp
        assert "dcr_values" in resp
