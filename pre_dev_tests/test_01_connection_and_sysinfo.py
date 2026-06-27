"""
PRD §1 — Connection & System Info

Tests that the bridge connects to the vendor server, exposes system
information, and surfaces laser/frame clock diagnostics.
"""
import pytest


class TestBridgeConnection:
    """Bridge ↔ vendor server TCP connection lifecycle."""

    def test_bridge_connects_to_vendor_server(self, bridge_client, mock_vendor_server):
        """Bridge establishes a TCP connection to the vendor command server
        on the configured port (default 9999)."""
        status = bridge_client.get("/api/status")
        assert status["vendor_connected"] is True

    def test_bridge_configurable_port(self, mock_vendor_server):
        """Bridge accepts a configurable port for the vendor server,
        not hardcoded to 9999."""
        # Start bridge with port=9998, verify it connects
        raise NotImplementedError

    def test_browser_connects_to_bridge(self, bridge_client):
        """SPA can reach the bridge over HTTP on the LAN."""
        resp = bridge_client.get("/api/health")
        assert resp is not None

    def test_websocket_connection(self, bridge_client):
        """SPA can open a WebSocket channel to the bridge for live updates."""
        ws = bridge_client.ws_connect("/ws")
        assert ws.connected


class TestSystemInfo:
    """PRD §1: Display system info via the D command."""

    def test_system_info_returns_fpga_serials(self, bridge_client):
        info = bridge_client.get("/api/system/info")
        assert "fpga_serial_master" in info
        assert "fpga_serial_slave" in info

    def test_system_info_returns_versions(self, bridge_client):
        info = bridge_client.get("/api/system/info")
        for key in ["sw_version", "fw_version", "hw_version"]:
            assert key in info

    def test_system_info_returns_hardware_flavour(self, bridge_client):
        info = bridge_client.get("/api/system/info")
        assert "hardware_flavour" in info

    def test_system_info_returns_sensor_size(self, bridge_client):
        info = bridge_client.get("/api/system/info")
        assert info["sensor_size"] in [512, 1024]

    def test_system_info_returns_enabled_features(self, bridge_client):
        info = bridge_client.get("/api/system/info")
        assert "enabled_features" in info
        for feature in ["intensity", "gated", "flim"]:
            assert feature in info["enabled_features"]

    def test_system_info_returns_valid_bit_depths(self, bridge_client):
        info = bridge_client.get("/api/system/info")
        assert "valid_bit_depths" in info

    def test_system_info_returns_valid_roi_widths(self, bridge_client):
        info = bridge_client.get("/api/system/info")
        assert "valid_roi_widths" in info


class TestTriggerDiagnostics:
    """PRD §1: Surface laser & frame clock frequencies (R command)."""

    def test_laser_frequency_reported(self, bridge_client):
        diag = bridge_client.get("/api/system/triggers")
        assert "laser_frequency_hz" in diag

    def test_frame_clock_frequency_reported(self, bridge_client):
        diag = bridge_client.get("/api/system/triggers")
        assert "frame_clock_frequency_hz" in diag

    def test_trigger_source_validation(self, bridge_client):
        """Bridge validates measured frequencies against the expected
        trigger source and flags mismatches."""
        diag = bridge_client.get("/api/system/triggers")
        assert "trigger_valid" in diag
