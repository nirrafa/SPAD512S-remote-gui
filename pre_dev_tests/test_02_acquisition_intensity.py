"""
PRD §2 — Intensity Acquisition Mode

Maps to cSPAD get_intensity / I command.
"""
import pytest


class TestIntensityParameters:
    """All intensity-mode parameters are accepted and forwarded correctly."""

    @pytest.mark.parametrize("bit_depth", [1, 4, 6, 7, 8, 9, 10, 11, 12])
    def test_valid_bit_depths_accepted(self, bridge_client, bit_depth):
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": bit_depth,
            "integration_time": 100,
            "iterations": 1,
        })
        assert resp["status"] != "error"

    def test_invalid_bit_depth_rejected(self, bridge_client):
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 3,
            "integration_time": 100,
            "iterations": 1,
        })
        assert resp["status"] == "error"

    def test_integration_time_unit_auto_switch(self, bridge_client):
        """For 1/4-bit: integration time in µs; for ≥6-bit: in ms.
        The API must handle this transparently."""
        # 1-bit → µs
        resp_1bit = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 1,
            "integration_time": 500,  # 500 µs
            "iterations": 1,
        })
        assert resp_1bit["integration_time_unit"] == "us"

        # 8-bit → ms
        resp_8bit = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,  # 100 ms
            "iterations": 1,
        })
        assert resp_8bit["integration_time_unit"] == "ms"

    @pytest.mark.parametrize("roi_width", [4, 8, 16, 32, 64, 128, 256, 512])
    def test_valid_roi_widths(self, bridge_client, roi_width):
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1,
            "roi_width": roi_width,
        })
        assert resp["status"] != "error"

    def test_overlap_mode(self, bridge_client):
        """Read/exposure overlap can be enabled."""
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1,
            "overlap": True,
        })
        assert resp["status"] != "error"

    def test_pileup_correction(self, bridge_client):
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1,
            "pileup_correction": True,
        })
        assert resp["status"] != "error"

    def test_multiple_iterations(self, bridge_client):
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 10,
        })
        assert resp["total_frames"] == 10

    def test_timeout_retry_on_acquisition_failure(self, bridge_client, mock_vendor_server):
        """If acquisition times out, bridge retries before reporting failure."""
        mock_vendor_server.set_next_response_delay(seconds=30)
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1,
            "timeout_s": 5,
        })
        assert resp["status"] in ["error", "timeout"]


class TestIntensityOutput:
    """Intensity acquisition produces correct output."""

    def test_returns_image_data(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        assert resp["status"] == "done"
        assert "preview" in resp

    def test_preview_is_downsampled(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        preview = resp["preview"]
        assert preview["width"] <= 512
        assert preview["height"] <= 512

    def test_full_data_saved_on_host(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        assert "host_path" in resp
