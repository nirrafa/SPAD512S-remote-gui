"""
Shared fixtures for PRD spec tests.

These fixtures define the interfaces the implementation must provide.
They will be wired to real implementations once the code exists.
"""
import time

import pytest
import requests
from bridge.config import Settings
from bridge.main import create_app
from fastapi.testclient import TestClient
from mock_server.harness import MockVendorServer
from spa_harness import SpaClient, ThreadedBridge, free_port


class _WebSocketHandle:
    def __init__(self, context_manager):
        self._cm = context_manager
        self._ws = context_manager.__enter__()
        self.connected = True

    def receive(self, timeout=None):
        # TestClient websockets block until a frame; pytest-timeout guards hangs.
        return self._ws.receive_json()

    def close(self):
        if self.connected:
            self._cm.__exit__(None, None, None)
            self.connected = False


class BridgeTestClient:
    """Thin HTTP/WebSocket wrapper exposing the interface the spec tests use:
    ``.get``/``.post`` return parsed JSON, plus ``.ws_connect`` and
    browser-disconnect simulation."""

    def __init__(self, app):
        self._client = TestClient(app)
        self._client.__enter__()  # runs lifespan startup (connects to vendor)
        self._ws_handles: list[_WebSocketHandle] = []

    def get(self, path, retry=False, timeout=10):
        if not retry:
            return self._client.get(path).json()
        deadline = time.monotonic() + timeout
        last = self._client.get(path).json()
        while time.monotonic() < deadline:
            if last.get("vendor_connected") is True:
                return last
            time.sleep(0.2)
            last = self._client.get(path).json()
        return last

    def post(self, path, json=None):
        return self._client.post(path, json=json or {}).json()

    def put(self, path, json=None):
        return self._client.put(path, json=json or {}).json()

    def delete(self, path):
        return self._client.delete(path).json()

    def ws_connect(self, path):
        handle = _WebSocketHandle(self._client.websocket_connect(path))
        self._ws_handles.append(handle)
        return handle

    def disconnect(self):
        """Simulate the browser closing — the bridge keeps running."""
        for handle in self._ws_handles:
            handle.close()
        self._ws_handles.clear()

    def reconnect(self):
        """Simulate the browser reopening — same bridge instance."""

    def close(self):
        for handle in self._ws_handles:
            handle.close()
        self._client.__exit__(None, None, None)


@pytest.fixture
def mock_vendor_server():
    """A mock implementation of the vendor cSPAD protocol.
    Supports commands: D, V, R, AE, CALIB, S, I, G, PU, Ga, Gf, F
    and returns synthetic data with DONE/ERROR framing.
    """
    server = MockVendorServer()
    yield server
    server.stop()


@pytest.fixture
def bridge_client(request, mock_vendor_server, tmp_path):
    """An HTTP/WebSocket client connected to a running bridge instance
    that is itself connected to the mock vendor server.

    When a test also drives the browser (``spa_client``), this shares the same
    live uvicorn server so both see the same acquisitions/log; otherwise it uses
    the fast in-process ``TestClient``.
    """
    if "spa_client" in request.fixturenames:
        live = request.getfixturevalue("live_bridge")
        yield LiveHTTPClient(live.base_url)
        return
    mock_vendor_server.start()
    settings = Settings(
        vendor_host="127.0.0.1",
        vendor_port=mock_vendor_server.port,
        data_root=str(tmp_path),
    )
    client = BridgeTestClient(create_app(settings))
    client.get("/api/status", retry=True, timeout=5)
    yield client
    client.close()


class LiveHTTPClient:
    """Minimal HTTP client against the live uvicorn bridge (shared with the
    browser). Mirrors the ``.get`` interface the E2E spec tests use."""

    def __init__(self, base_url):
        self._base = base_url

    def get(self, path, **_):
        return requests.get(self._base + path, timeout=10).json()

    def post(self, path, json=None):
        return requests.post(self._base + path, json=json or {}, timeout=30).json()


@pytest.fixture
def live_bridge(mock_vendor_server, tmp_path):
    """A real uvicorn bridge (background thread) serving the built SPA and
    connected to the mock — the substrate the browser drives."""
    mock_vendor_server.start()
    settings = Settings(
        vendor_host="127.0.0.1",
        vendor_port=mock_vendor_server.port,
        data_root=str(tmp_path),
        bridge_port=free_port(),
    )
    bridge = ThreadedBridge(settings)
    bridge.start()
    yield bridge
    bridge.stop()


@pytest.fixture
def spa_client(live_bridge):
    """A Chromium page (Playwright) pointed at the SPA served by the bridge."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001 — missing browser binary → skip
        playwright.stop()
        pytest.skip(f"chromium unavailable: {exc}")

    page = browser.new_page()
    page.set_default_timeout(15000)
    page.goto(live_bridge.base_url)
    page.wait_for_selector(".tabs", timeout=15000)
    client = SpaClient(page, live_bridge.base_url)
    try:
        yield client
    finally:
        browser.close()
        playwright.stop()


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
