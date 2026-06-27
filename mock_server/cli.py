"""CLI entry point: ``python -m mock_server --port 9999``."""
from __future__ import annotations

import argparse
import asyncio
import contextlib

from mock_server.server import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Pi Imaging SPAD512² vendor server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(host=args.host, port=args.port))
