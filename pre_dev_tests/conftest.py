"""
Shared fixtures for PRD spec tests.

These fixtures define the interfaces the implementation must provide.
They will be wired to real implementations once the code exists.
"""
import pytest


@pytest.fixture
def mock_vendor_server():
    """A mock TCP server implementing the vendor cSPAD protocol.
    Must support commands: D, V, R, AE, CALIB, S, I, G, PU, Ga, Gf, F
    and return synthetic data with DONE/ERROR framing.
    """
    raise NotImplementedError("Wire to mock vendor server implementation")


@pytest.fixture
def bridge_client(mock_vendor_server):
    """An HTTP/WebSocket client connected to a running bridge instance
    that is itself connected to the mock vendor server."""
    raise NotImplementedError("Wire to bridge test client")


@pytest.fixture
def spa_client(bridge_client):
    """A browser automation handle (e.g. Playwright) pointed at the SPA
    served by the bridge, for end-to-end tests."""
    raise NotImplementedError("Wire to browser automation client")


@pytest.fixture
def sample_intensity_params():
    return {
        "bit_depth": 8,
        "integration_time_ms": 100,
        "iterations": 1,
        "roi_width": 512,
        "overlap": False,
        "pileup_correction": True,
    }


@pytest.fixture
def sample_gated_params():
    return {
        "bit_depth": 8,
        "integration_time_ms": 100,
        "iterations": 1,
        "gate_steps": 20,
        "gate_step_size_ps": 18,
        "gate_width": 5,
        "gate_offset": 0,
        "gate_direction": "forward",
        "gate_trigger_source": "external",
        "overlap": False,
        "stream": False,
        "pileup_correction": True,
    }


@pytest.fixture
def sample_flim_params():
    return {
        "calibration_type": "mono_exponential",
        "expected_tau_ns": 4.0,
        "gate_width": "medium",
        "integration_time_ms": 200,
        "gate_subsampling": 1,
        "output_format": "image",
    }


@pytest.fixture
def sample_sweep_params():
    return {
        "mode": "intensity",
        "sweep_parameter": "integration_time_ms",
        "values": [50, 100, 200, 500, 1000],
        "base_params": {
            "bit_depth": 8,
            "iterations": 1,
            "roi_width": 512,
        },
    }
