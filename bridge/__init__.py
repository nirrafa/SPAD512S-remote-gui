"""SPAD512² remote control bridge.

FastAPI application that owns the single TCP connection to the Pi Imaging
vendor server, serializes commands, and exposes REST + WebSocket APIs to the
browser front-end.
"""

__version__ = "0.1.0"
