"""Shared fixtures for bridge tests.

Bridge tests run against the mock vendor server, never real hardware.
Fixtures are added here as the implementation grows (Phase 1+).
"""
from __future__ import annotations

import socket

import pytest
from bridge.config import Settings
from bridge.main import create_app
from fastapi.testclient import TestClient


def _unused_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def app():
    # Isolate the default suite from any stray vendor/mock on 9999.
    return create_app(Settings(vendor_host="127.0.0.1", vendor_port=_unused_port()))


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
