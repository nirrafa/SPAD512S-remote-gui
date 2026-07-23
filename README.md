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

**Windows lab host (real camera):** see the beginner-friendly, step-by-step
guide in [docs/windows_smoke_test.md](docs/windows_smoke_test.md) — install
Python, download the ZIP, double-click one `.bat`. No Node/npm needed.

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
log + presets + re-run, and a Playwright browser E2E harness. Post-PRD additions:
a spartan on-demand **Live** tab (single-shot or a 300 ms client-driven poll
loop) for hosts that can't run the vendor's own GUI; **dark-count (DCR)
reference & correction** for gated and intensity modes (covered-sensor
reference measurement → per-pixel subtraction, display-only, full provenance);
manual **WB min/max sliders** on every image view; an acquisition **queue**
(run a mixed series — "2 gated then 3 intensity" — unattended); and **paced
gated** mode (a configurable cool-off between gate steps so the sensor sheds
heat, with matching paced dark references). The remaining work is
hardware bring-up on the Windows host once the SPAD512² is available (including
dark-correction physics validation). Track progress in
[docs/progress.md](docs/progress.md).
