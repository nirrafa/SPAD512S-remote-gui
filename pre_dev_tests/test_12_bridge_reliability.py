"""
PRD Non-functional — Bridge Reliability

Auto-reconnect, sweep checkpoint/resume, survive browser disconnect,
clean abort leaving hardware safe.
"""
import pytest


class TestAutoReconnect:

    def test_bridge_reconnects_after_vendor_server_restart(
        self, bridge_client, mock_vendor_server
    ):
        mock_vendor_server.stop()
        mock_vendor_server.start()
        # Bridge should auto-reconnect
        status = bridge_client.get("/api/status", retry=True, timeout=15)
        assert status["vendor_connected"] is True

    def test_bridge_reports_disconnected_state(self, bridge_client, mock_vendor_server):
        mock_vendor_server.stop()
        status = bridge_client.get("/api/status")
        assert status["vendor_connected"] is False

    def test_commands_rejected_while_disconnected(self, bridge_client, mock_vendor_server):
        mock_vendor_server.stop()
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 1,
        })
        assert resp["status"] == "error"
        assert "disconnected" in resp["message"].lower()


class TestSweepCheckpointResume:

    def test_sweep_checkpoint_written(self, bridge_client, sample_sweep_params):
        resp = bridge_client.post("/api/acquire/sweep", json=sample_sweep_params)
        assert resp["checkpoints_written"] == len(sample_sweep_params["values"])

    def test_sweep_resume_after_failure(self, bridge_client, mock_vendor_server, sample_sweep_params):
        """If bridge crashes mid-sweep, resumed sweep picks up from last checkpoint."""
        # Start sweep, simulate crash after 2 points
        mock_vendor_server.fail_after_n_commands(2)
        bridge_client.post("/api/acquire/sweep", json=sample_sweep_params)
        # Restart and resume
        resp = bridge_client.post("/api/acquire/sweep/resume")
        assert resp["points_skipped"] == 2
        assert resp["status"] == "done"


class TestSurviveBrowserDisconnect:

    def test_acquisition_continues_after_browser_close(
        self, bridge_client, sample_intensity_params
    ):
        bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params, "iterations": 100,
        })
        bridge_client.disconnect()
        bridge_client.reconnect()
        status = bridge_client.get("/api/acquire/status")
        assert status["state"] in ["running", "completed"]

    def test_sweep_continues_after_browser_close(
        self, bridge_client, sample_sweep_params
    ):
        bridge_client.post("/api/acquire/sweep", json=sample_sweep_params)
        bridge_client.disconnect()
        bridge_client.reconnect()
        status = bridge_client.get("/api/acquire/status")
        assert status["state"] in ["running", "completed"]


class TestCleanAbort:

    def test_abort_leaves_hardware_idle(self, bridge_client):
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 1000,
        })
        bridge_client.post("/api/acquire/stop")
        status = bridge_client.get("/api/status")
        assert status["instrument_state"] == "idle"

    def test_abort_does_not_corrupt_vendor_protocol(
        self, bridge_client, mock_vendor_server
    ):
        """After abort, subsequent commands succeed (no protocol corruption)."""
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 1000,
        })
        bridge_client.post("/api/acquire/stop")
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 1,
        })
        assert resp["status"] == "done"
