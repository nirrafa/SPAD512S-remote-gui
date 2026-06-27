"""
PRD §2 — Raw 1-bit Single-Photon Mode

Bit-depth-1 intensity path with distinct binary unpacking,
for high-speed/photon-statistics work.
"""
import pytest


class TestRaw1BitAcquisition:

    def test_raw_1bit_acquisition(self, bridge_client):
        resp = bridge_client.post("/api/acquire/raw-1bit", json={
            "integration_time_us": 100,
            "iterations": 1,
        })
        assert resp["status"] == "done"

    def test_raw_1bit_uses_binary_unpacking(self, bridge_client):
        """Raw 1-bit mode uses a distinct binary decode path,
        not the standard intensity decoder."""
        resp = bridge_client.post("/api/acquire/raw-1bit", json={
            "integration_time_us": 100,
            "iterations": 1,
        })
        assert resp["decode_method"] == "binary_unpack"

    def test_raw_1bit_bit_depth_is_1(self, bridge_client):
        resp = bridge_client.post("/api/acquire/raw-1bit", json={
            "integration_time_us": 100,
            "iterations": 1,
        })
        assert resp["bit_depth"] == 1

    def test_raw_1bit_multiple_iterations(self, bridge_client):
        resp = bridge_client.post("/api/acquire/raw-1bit", json={
            "integration_time_us": 100,
            "iterations": 50,
        })
        assert resp["total_frames"] == 50

    def test_raw_1bit_data_saved_on_host(self, bridge_client):
        resp = bridge_client.post("/api/acquire/raw-1bit", json={
            "integration_time_us": 100,
            "iterations": 1,
        })
        assert "host_path" in resp
