"""
PRD Non-functional — Concurrency & Serialization

Single command queue, busy state broadcast, conflicting command rejection.
"""
import pytest


class TestCommandSerialization:

    def test_concurrent_commands_serialized(self, bridge_client):
        """Two simultaneous commands are queued, not interleaved."""
        import threading
        results = []

        def acquire():
            r = bridge_client.post("/api/acquire/intensity", json={
                "bit_depth": 8, "integration_time": 100, "iterations": 1,
            })
            results.append(r)

        t1 = threading.Thread(target=acquire)
        t2 = threading.Thread(target=acquire)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        statuses = [r["status"] for r in results]
        assert "done" in statuses
        # The second should either be rejected (busy) or queued and done
        assert all(s in ["done", "error", "busy"] for s in statuses)

    def test_command_rejected_while_busy(self, bridge_client):
        """A control command is rejected with clear messaging while instrument is busy."""
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 1000,
        })
        resp = bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 1,
        })
        assert resp["status"] == "error"
        assert "busy" in resp["message"].lower()


class TestBusyStateBroadcast:

    def test_busy_state_broadcast_to_all_clients(self, bridge_client):
        ws1 = bridge_client.ws_connect("/ws")
        ws2 = bridge_client.ws_connect("/ws")
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 10,
        })
        msg1 = ws1.receive(timeout=5)
        msg2 = ws2.receive(timeout=5)
        assert msg1["type"] == "busy"
        assert msg2["type"] == "busy"

    def test_busy_state_includes_context(self, bridge_client):
        ws = bridge_client.ws_connect("/ws")
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 10,
            "sample_name": "test_sample",
        })
        msg = ws.receive(timeout=5)
        assert msg["type"] == "busy"
        assert "mode" in msg
        assert "progress" in msg

    def test_health_polling_during_busy(self, bridge_client):
        """Read-only health polling stays available even during acquisition."""
        bridge_client.post("/api/acquire/intensity", json={
            "bit_depth": 8, "integration_time": 100, "iterations": 1000,
        })
        health = bridge_client.get("/api/health/readings")
        assert health is not None
        assert "temp_chip" in health
