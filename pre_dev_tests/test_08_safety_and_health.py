"""
PRD §5 — Detector Safety & Health (Alarms + Auto-Protect)

Poll temps/voltages, raise alarms, auto-protect on threshold breach.
"""
import pytest


class TestHealthPolling:

    def test_temperatures_polled(self, bridge_client):
        health = bridge_client.get("/api/health/readings")
        for key in ["temp_master_fpga", "temp_slave_fpga", "temp_pcb", "temp_chip"]:
            assert key in health

    def test_voltages_polled(self, bridge_client):
        health = bridge_client.get("/api/health/readings")
        assert "vq" in health
        assert "vex" in health

    def test_cooling_state_polled(self, bridge_client):
        health = bridge_client.get("/api/health/readings")
        assert "cooling_active" in health

    def test_laser_frequency_polled(self, bridge_client):
        health = bridge_client.get("/api/health/readings")
        assert "laser_frequency_hz" in health

    def test_frame_frequency_polled(self, bridge_client):
        health = bridge_client.get("/api/health/readings")
        assert "frame_frequency_hz" in health

    def test_health_polling_interval(self, bridge_client):
        """Health readings are refreshed on a configurable interval."""
        config = bridge_client.get("/api/health/config")
        assert "poll_interval_s" in config


class TestAlarms:

    def test_over_temperature_alarm(self, bridge_client, mock_vendor_server):
        mock_vendor_server.set_temperature("chip", 85.0)
        health = bridge_client.get("/api/health/readings")
        assert any(a["type"] == "over_temperature" for a in health.get("alarms", []))

    def test_cooling_failure_alarm(self, bridge_client, mock_vendor_server):
        mock_vendor_server.set_cooling(active=False)
        health = bridge_client.get("/api/health/readings")
        assert any(a["type"] == "cooling_failure" for a in health.get("alarms", []))

    def test_missing_laser_trigger_alarm(self, bridge_client, mock_vendor_server):
        mock_vendor_server.set_laser_frequency(0)
        health = bridge_client.get("/api/health/readings")
        assert any(a["type"] == "missing_laser_trigger" for a in health.get("alarms", []))

    def test_abnormal_laser_trigger_alarm(self, bridge_client, mock_vendor_server):
        mock_vendor_server.set_laser_frequency(999999999)
        health = bridge_client.get("/api/health/readings")
        assert any(a["type"] == "abnormal_laser_trigger" for a in health.get("alarms", []))

    def test_overexposure_alarm(self, bridge_client, mock_vendor_server):
        """Suspected overexposure raises an alarm."""
        mock_vendor_server.simulate_overexposure()
        health = bridge_client.get("/api/health/readings")
        assert any(a["type"] == "suspected_overexposure" for a in health.get("alarms", []))

    def test_alarms_broadcast_over_websocket(self, bridge_client, mock_vendor_server):
        """Alarms are pushed to all connected WebSocket clients."""
        ws = bridge_client.ws_connect("/ws")
        mock_vendor_server.set_temperature("chip", 85.0)
        msg = ws.receive(timeout=5)
        assert msg["type"] == "alarm"


class TestAutoProtect:

    def test_auto_abort_on_over_temperature(self, bridge_client, mock_vendor_server):
        """Acquisition aborts if temperature exceeds threshold during run."""
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1000,
        })
        mock_vendor_server.set_temperature("chip", 90.0)
        status = bridge_client.get("/api/acquire/status")
        assert status["state"] in ["aborted", "stopping"]
        assert status.get("abort_reason") == "over_temperature"

    def test_auto_reduce_bias_on_threshold(self, bridge_client, mock_vendor_server):
        """Auto-protect can reduce Vex to a safe value instead of aborting."""
        mock_vendor_server.set_voltage("vex", 30.0)
        health = bridge_client.get("/api/health/readings")
        assert health.get("vex_reduced") or any(
            a["type"] == "vex_reduced" for a in health.get("alarms", [])
        )

    def test_configurable_thresholds(self, bridge_client):
        resp = bridge_client.put("/api/health/config", json={
            "temp_threshold_chip": 80.0,
            "vex_max": 25.0,
        })
        assert resp["status"] == "ok"
        config = bridge_client.get("/api/health/config")
        assert config["temp_threshold_chip"] == 80.0
        assert config["vex_max"] == 25.0

    def test_high_vex_requires_confirmation(self, bridge_client):
        """Setting a high Vex value requires explicit user confirmation."""
        resp = bridge_client.post("/api/settings/vex", json={"vex": 28.0})
        assert resp.get("requires_confirmation") is True

    def test_health_polling_available_during_acquisition(self, bridge_client, sample_intensity_params):
        """Health polling continues even while an acquisition is running."""
        bridge_client.post("/api/acquire/intensity", json={
            **sample_intensity_params,
            "iterations": 1000,
        })
        health = bridge_client.get("/api/health/readings")
        assert "temp_chip" in health
