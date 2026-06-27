"""
PRD §2 — FLIM Acquisition Mode

Maps to cSPAD calib_FLIM + get_FLIM / F command.
Includes IRF calibration and phasor processing.
"""
import pytest


class TestFLIMCalibration:
    """IRF calibration must precede FLIM acquisition."""

    def test_irf_calibration_mono_exponential(self, bridge_client):
        resp = bridge_client.post("/api/calibrate/flim-irf", json={
            "calibration_type": "mono_exponential",
            "expected_tau_ns": 4.0,
            "gate_width": "medium",
        })
        assert resp["status"] == "done"

    def test_irf_calibration_bi_exponential(self, bridge_client):
        resp = bridge_client.post("/api/calibrate/flim-irf", json={
            "calibration_type": "bi_exponential",
            "expected_tau_ns": [2.0, 6.0],
            "gate_width": "short",
        })
        assert resp["status"] == "done"

    @pytest.mark.parametrize("gate_width", ["short", "medium", "long"])
    def test_irf_gate_width_options(self, bridge_client, gate_width):
        resp = bridge_client.post("/api/calibrate/flim-irf", json={
            "calibration_type": "mono_exponential",
            "expected_tau_ns": 4.0,
            "gate_width": gate_width,
        })
        assert resp["status"] == "done"


class TestFLIMAcquisition:

    def test_basic_flim_acquisition(self, bridge_client, sample_flim_params):
        resp = bridge_client.post("/api/acquire/flim", json=sample_flim_params)
        assert resp["status"] == "done"

    def test_flim_requires_irf_calibration(self, bridge_client, sample_flim_params):
        """Acquiring FLIM without prior IRF calibration should warn or error."""
        # Assume fresh state with no calibration
        resp = bridge_client.post("/api/acquire/flim", json=sample_flim_params)
        assert resp.get("warning") or resp["status"] == "error"

    def test_gate_subsampling(self, bridge_client, sample_flim_params):
        sample_flim_params["gate_subsampling"] = 2
        resp = bridge_client.post("/api/acquire/flim", json=sample_flim_params)
        assert resp["status"] == "done"

    def test_image_output_format(self, bridge_client, sample_flim_params):
        sample_flim_params["output_format"] = "image"
        resp = bridge_client.post("/api/acquire/flim", json=sample_flim_params)
        assert "lifetime_map" in resp or "preview" in resp

    def test_raw_output_format(self, bridge_client, sample_flim_params):
        sample_flim_params["output_format"] = "raw"
        resp = bridge_client.post("/api/acquire/flim", json=sample_flim_params)
        assert resp["status"] == "done"


class TestPhasorProcessing:

    def test_phasor_data_returned(self, bridge_client, sample_flim_params):
        resp = bridge_client.post("/api/acquire/flim", json=sample_flim_params)
        assert "phasor" in resp
        assert "g" in resp["phasor"]  # real component
        assert "s" in resp["phasor"]  # imaginary component
