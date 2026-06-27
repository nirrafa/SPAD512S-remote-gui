"""Shared fixtures for bridge tests.

Bridge tests run against the mock vendor server, never real hardware.
Fixtures are added here as the implementation grows (Phase 1+).
"""
from __future__ import annotations

import pytest
from bridge.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
