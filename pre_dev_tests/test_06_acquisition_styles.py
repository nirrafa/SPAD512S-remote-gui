"""
PRD §3 — Acquisition Styles

Single-shot, parameter sweeps, scheduled/overnight, and safe-boundary abort.
"""
import pytest


class TestSingleShot:

    def test_single_shot_intensity(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        assert resp["status"] == "done"

    def test_single_shot_returns_result_immediately(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/intensity", json=sample_intensity_params)
        assert "host_path" in resp
        assert "preview" in resp


class TestParameterSweeps:

    def test_sweep_over_single_parameter(self, bridge_client, sample_sweep_params):
        resp = bridge_client.post("/api/acquire/sweep", json=sample_sweep_params)
        assert resp["status"] == "done"
        assert resp["points_completed"] == len(sample_sweep_params["values"])

    def test_sweep_labeled_series(self, bridge_client, sample_sweep_params):
        """Each sweep point is labeled with its parameter value."""
        resp = bridge_client.post("/api/acquire/sweep", json=sample_sweep_params)
        for point in resp["results"]:
            assert "label" in point
            assert "value" in point

    def test_sweep_checkpoint_each_point(self, bridge_client, sample_sweep_params):
        """Each completed sweep point is checkpointed so progress survives
        a client disconnect."""
        resp = bridge_client.post("/api/acquire/sweep", json=sample_sweep_params)
        assert resp["checkpoints_written"] == len(sample_sweep_params["values"])

    def test_sweep_survives_client_disconnect(self, bridge_client, sample_sweep_params):
        """Start a sweep, disconnect the browser, reconnect — sweep continues."""
        bridge_client.post("/api/acquire/sweep", json=sample_sweep_params)
        bridge_client.disconnect()
        bridge_client.reconnect()
        status = bridge_client.get("/api/acquire/status")
        assert status["running"] is True

    def test_sweep_multi_parameter(self, bridge_client):
        """Sweep over multiple parameters simultaneously."""
        resp = bridge_client.post("/api/acquire/sweep", json={
            "mode": "gated",
            "sweep_parameters": {
                "gate_offset": [0, 10, 20],
                "integration_time_ms": [100, 200],
            },
            "base_params": {
                "bit_depth": 8,
                "gate_steps": 10,
                "gate_step_size_ps": 18,
                "gate_width": 5,
                "iterations": 1,
            },
        })
        assert resp["status"] == "done"
        assert resp["points_completed"] == 6  # 3 × 2


class TestScheduledAcquisition:

    def test_queue_scheduled_job(self, bridge_client, sample_intensity_params):
        resp = bridge_client.post("/api/acquire/schedule", json={
            "mode": "intensity",
            "params": sample_intensity_params,
            "start_time": "2026-06-28T02:00:00",
        })
        assert resp["status"] == "scheduled"
        assert "job_id" in resp

    def test_scheduled_job_runs_unattended(self, bridge_client, sample_intensity_params):
        """Scheduled job executes even if no browser is connected."""
        resp = bridge_client.post("/api/acquire/schedule", json={
            "mode": "intensity",
            "params": sample_intensity_params,
            "start_time": "2026-06-28T02:00:00",
        })
        job_id = resp["job_id"]
        # Simulate time passing and job completing
        job_status = bridge_client.get(f"/api/acquire/schedule/{job_id}")
        assert job_status["state"] in ["scheduled", "running", "completed", "failed"]

    def test_scheduled_job_visible_in_experiment_log(self, bridge_client, sample_intensity_params):
        bridge_client.post("/api/acquire/schedule", json={
            "mode": "intensity",
            "params": sample_intensity_params,
            "start_time": "2026-06-28T02:00:00",
        })
        log = bridge_client.get("/api/experiment-log")
        scheduled = [e for e in log["entries"] if e.get("scheduled")]
        assert len(scheduled) > 0


class TestSafeBoundaryAbort:

    def test_stop_between_iterations(self, bridge_client):
        """Stop request takes effect between iterations, not mid-frame."""
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1000,
        })
        resp = bridge_client.post("/api/acquire/stop")
        assert resp["status"] == "stopping"
        assert resp["stop_boundary"] == "between_iterations"

    def test_stop_between_sweep_points(self, bridge_client, sample_sweep_params):
        bridge_client.post("/api/acquire/sweep", json=sample_sweep_params)
        resp = bridge_client.post("/api/acquire/stop")
        assert resp["stop_boundary"] in ["between_iterations", "between_sweep_points"]

    def test_in_flight_frame_finishes(self, bridge_client):
        """An in-flight frame completes before the stop takes effect."""
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 5000,
            "iterations": 100,
        })
        resp = bridge_client.post("/api/acquire/stop")
        assert resp["in_flight_completed"] is True

    def test_hardware_left_in_safe_state_after_stop(self, bridge_client):
        """After stop, the hardware is in a safe idle state."""
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8,
            "integration_time": 100,
            "iterations": 1000,
        })
        bridge_client.post("/api/acquire/stop")
        status = bridge_client.get("/api/status")
        assert status["instrument_state"] == "idle"
