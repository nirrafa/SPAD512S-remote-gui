"""
PRD §2 — Gated Time-Resolved Acquisition Mode

Maps to cSPAD get_gated_intensity / G command, plus Ga (arbitrary steps)
and Gf (optimal parameters helper).
"""
import pytest


class TestGatedParameters:

    def test_gate_steps_and_step_size(self, bridge_client, sample_gated_params):
        resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
        assert resp["status"] == "done"

    def test_gate_step_size_resolution(self, bridge_client, sample_gated_params):
        """Step size is in multiples of ~18 ps."""
        sample_gated_params["gate_step_size_ps"] = 18
        resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
        assert resp["status"] == "done"

    def test_arbitrary_step_array(self, bridge_client, sample_gated_params):
        """Ga command: user provides an explicit array of gate positions."""
        sample_gated_params["arbitrary_steps"] = [0, 5, 10, 20, 50, 100]
        del sample_gated_params["gate_steps"]
        del sample_gated_params["gate_step_size_ps"]
        resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
        assert resp["status"] == "done"

    def test_gate_width(self, bridge_client, sample_gated_params):
        for width in [1, 5, 10, 20]:
            sample_gated_params["gate_width"] = width
            resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
            assert resp["status"] != "error"

    def test_gate_offset(self, bridge_client, sample_gated_params):
        sample_gated_params["gate_offset"] = 50
        resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
        assert resp["status"] == "done"

    def test_gate_direction(self, bridge_client, sample_gated_params):
        for direction in ["forward", "reverse"]:
            sample_gated_params["gate_direction"] = direction
            resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
            assert resp["status"] != "error"

    def test_gate_trigger_source(self, bridge_client, sample_gated_params):
        for source in ["internal", "external"]:
            sample_gated_params["gate_trigger_source"] = source
            resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
            assert resp["status"] != "error"

    def test_streaming_mode(self, bridge_client, sample_gated_params):
        sample_gated_params["stream"] = True
        resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
        assert resp["status"] == "done"


class TestOptimalParametersHelper:
    """Gf command: auto-fill steps/offset/min_step for one full cycle."""

    def test_optimal_params_returned(self, bridge_client):
        resp = bridge_client.get("/api/acquire/gated/optimal-params")
        for key in ["steps", "offset", "min_step"]:
            assert key in resp

    def test_optimal_params_applied_to_acquisition(self, bridge_client):
        """User can request optimal params and immediately acquire with them."""
        optimal = bridge_client.get("/api/acquire/gated/optimal-params")
        resp = bridge_client.post("/api/acquire/gated", json={
            "bit_depth": 8,
            "integration_time_ms": 100,
            "iterations": 1,
            "gate_steps": optimal["steps"],
            "gate_step_size_ps": optimal["min_step"],
            "gate_offset": optimal["offset"],
            "gate_width": 5,
            "gate_direction": "forward",
            "gate_trigger_source": "external",
        })
        assert resp["status"] == "done"


class TestGatedOutput:

    def test_returns_gated_stack(self, bridge_client, sample_gated_params):
        resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
        assert resp["status"] == "done"
        assert resp["total_gate_steps"] == sample_gated_params["gate_steps"]

    def test_preview_per_gate_step(self, bridge_client, sample_gated_params):
        """Each gate step produces a preview frame sent over WebSocket."""
        resp = bridge_client.post("/api/acquire/gated", json=sample_gated_params)
        assert resp["previews_sent"] == sample_gated_params["gate_steps"]
