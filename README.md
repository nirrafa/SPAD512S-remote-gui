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

### Browser end-to-end tests (optional)

The visualization (`test_10`) and end-to-end (`test_15`) specs drive a real
Chromium against the bridge-served SPA:

```bash
pip install -e ".[e2e]"
python -m playwright install chromium
cd frontend && npm run build && cd ..   # the bridge serves the built SPA
pytest pre_dev_tests/test_10_visualization.py pre_dev_tests/test_15_end_to_end.py
```

These skip cleanly if Playwright or the browser isn't installed; the rest of the
suite runs against the in-process bridge with no browser.

## Status

**Phases 0–13 complete — full PRD spec coverage (202/202 pre-dev tests) against
the mock vendor server.** Intensity, gated, FLIM, raw 1-bit, sweeps/scheduling,
calibration, safety/health, data handling, in-browser visualization, experiment
log + presets + re-run, and a Playwright browser E2E harness. The remaining work
is hardware bring-up on the Windows host once the SPAD512² is available. Track
progress in [docs/progress.md](docs/progress.md).
