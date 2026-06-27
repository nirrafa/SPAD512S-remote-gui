"""
PRD Testing — Mock cSPAD Vendor Server

The mock must implement all vendor protocol commands and return
synthetic data with correct framing.
"""
import pytest


class TestMockProtocol:
    """The mock server implements the full vendor ASCII protocol."""

    def test_system_info_command_D(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("D")
        assert "DONE" in resp

    def test_voltage_command_V(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("V")
        assert "DONE" in resp

    def test_readout_command_R(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("R")
        assert "DONE" in resp

    def test_auto_exposure_command_AE(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("AE")
        assert "DONE" in resp

    def test_calibration_command_CALIB(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("CALIB")
        assert "DONE" in resp

    def test_status_command_S(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("S")
        assert "DONE" in resp

    def test_intensity_command_I(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("I")
        assert "DONE" in resp

    def test_gated_command_G(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("G")
        assert "DONE" in resp

    def test_pileup_command_PU(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("PU")
        assert "DONE" in resp

    def test_arbitrary_steps_command_Ga(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("Ga")
        assert "DONE" in resp

    def test_optimal_gated_params_command_Gf(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("Gf")
        assert "DONE" in resp

    def test_flim_command_F(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("F")
        assert "DONE" in resp

    def test_set_path_command(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("D,C:\\test_path")
        assert "DONE" in resp


class TestMockSyntheticData:

    def test_intensity_returns_synthetic_image(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("I")
        assert mock_vendor_server.last_image_data is not None
        assert mock_vendor_server.last_image_data.shape == (512, 512)

    def test_gated_returns_synthetic_stack(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("G")
        assert mock_vendor_server.last_image_data is not None
        assert len(mock_vendor_server.last_image_data.shape) == 3

    def test_flim_returns_phasor_data(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("F")
        assert mock_vendor_server.last_phasor_data is not None


class TestMockFraming:

    def test_done_framing(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("D")
        assert resp.strip().endswith("DONE")

    def test_error_framing(self, mock_vendor_server):
        resp = mock_vendor_server.send_command("INVALID_CMD")
        assert "ERROR" in resp

    def test_breakdown_calibration_handshake(self, mock_vendor_server):
        """Breakdown calibration has a multi-step handshake."""
        resp = mock_vendor_server.send_command("CALIB,BREAKDOWN")
        assert "DONE" in resp
