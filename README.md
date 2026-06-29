# SPAD512² Remote Control GUI

Web-based remote control for the Pi Imaging SPAD512² camera in the Suchowski
(FemtoNano) lab at TAU. A FastAPI Python bridge runs on the host PC and serves a
React/TypeScript single-page app to the browser over the LAN.

## Architecture

```
Browser (React SPA)  ──HTTP/WS──►  FastAPI bridge  ──TCP──►  Vendor server / Mock
```

- **Bridge** (`bridge/`) — owns the single TCP connection, serializes commands,
  exposes REST + WebSocket.
- **Mock server** (`mock_server/`) — implements the vendor cSPAD ASCII protocol
  for hardware-free development.
- **Front-end** (`frontend/`) — React SPA for acquisition, calibration, health,
  and visualization.

See [docs/plan.md](docs/plan.md) for the phased implementation plan and
[docs/PRD.md](docs/PRD.md) for requirements. To exercise the bridge yourself with
no hardware, see [docs/manual-testing.md](docs/manual-testing.md).

## Quick start (no CLI)

Double-click a launcher in [`launchers/`](launchers/) to start the mock camera +
bridge + GUI and open your browser — see [launchers/README.md](launchers/README.md).
After a one-time `python3.11 -m venv .venv && pip install -e ".[dev]"`.

## Development

### Bridge

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn bridge.main:app --reload
```

### Front-end

```bash
cd frontend
npm install
npm run dev
```

## Status

Phases 0–4 complete (mock server, bridge core, intensity + gated modes, first
browser GUI). Track progress in [docs/progress.md](docs/progress.md).
