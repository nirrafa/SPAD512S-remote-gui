# CLAUDE.md — SPAD512² Remote Control GUI

## Project overview

Web-based remote control GUI for the Pi Imaging SPAD512² camera in the Suchowski (FemtoNano) lab at TAU. Architecture: FastAPI Python bridge on the host PC + React/TypeScript SPA for the browser.

- [Product Requirements](docs/PRD.md)
- [Implementation Plan](docs/plan.md) — **living document, update as work progresses**
- [Progress Log](docs/progress.md) — **update at the end of every work session**
- [Learnings](docs/learnings.md) — **bugs, protocol quirks, and lessons for future lab tools**
- [Constraints](docs/constraints.md) — **update this file whenever a new constraint is discovered**
- [Known Bugs](docs/bugs.md) — **open issues & deferred fixes (mostly from `/code-review`); add an entry when a finding is deferred, move to Fixed when resolved**
- [Design: DCR correction](docs/design_gated_dcr_correction.md) — **implemented (gated + intensity dark references, WB sliders); correction physics awaits real-camera validation**
- [Windows smoke-test guide](docs/windows_smoke_test.md) — **beginner-proof runbook for the lab's Windows host; `frontend/dist` is committed so Windows needs Python only (rebuild + commit dist after frontend changes)**

## Stack

- **Bridge:** Python, FastAPI, asyncio, SQLite
- **Front-end:** React, TypeScript, Plotly/canvas for visualization
- **Protocol client:** wraps `cSPAD.py` (TCP ASCII protocol to vendor software)
- **Mock server:** Python TCP server implementing the vendor protocol for hardware-free dev

## Code conventions

- Python: snake_case for functions/variables, PascalCase for classes. Follow existing style in `theoretical_info/` reference code.
- TypeScript/React: camelCase for variables/functions, PascalCase for components. Prefer functional components with hooks.
- No comments unless the *why* is non-obvious. Never explain *what* code does.
- Keep acquisition logic in pure Python (reuse `cSPAD`); keep the React layer thin.
- Type hints on all Python function signatures. Strict TypeScript (`strict: true`).

## Key commands

```bash
# Bridge
pip install -e ".[dev]"          # install with dev deps (when set up)
pytest                           # run all tests
pytest tests/test_bridge.py -x   # bridge tests, stop on first failure
uvicorn bridge.main:app --reload # run bridge in dev mode

# Front-end
npm install                      # install deps
npm run dev                      # dev server
npm run build                    # production build
npm run lint                     # lint
npm test                         # run tests
```

## Pre-development spec tests

`pre_dev_tests/` contains **202 acceptance tests** (the plan's original 185 was an estimate) reverse-engineered from the PRD, organized by section. These are stubs — fixtures in `conftest.py` raise `NotImplementedError` until wired to the real implementation. After development, run them to verify PRD coverage:

| File | PRD Section |
|---|---|
| `test_01_connection_and_sysinfo.py` | §1 Connection & system info |
| `test_02_acquisition_intensity.py` | §2 Intensity mode |
| `test_03_acquisition_gated.py` | §2 Gated time-resolved mode |
| `test_04_acquisition_flim.py` | §2 FLIM mode |
| `test_05_acquisition_raw_1bit.py` | §2 Raw 1-bit single-photon |
| `test_06_acquisition_styles.py` | §3 Single-shot, sweeps, scheduled, abort |
| `test_07_calibration.py` | §4 Calibration (guided + state-aware) |
| `test_08_safety_and_health.py` | §5 Safety & health |
| `test_09_data_handling.py` | §6 Data handling & formats |
| `test_10_visualization.py` | §7 Visualization (browser) |
| `test_11_reproducibility_and_workflow.py` | §8 Presets, log, re-run |
| `test_12_bridge_reliability.py` | NF: Reliability |
| `test_13_concurrency_and_serialization.py` | NF: Concurrency |
| `test_14_mock_vendor_server.py` | Testing: Mock server |
| `test_15_end_to_end.py` | Testing: E2E scenarios |

## Status

**Phases 0–13 complete — full PRD spec coverage, 202/202 pre-dev passing against the mock.** Bridge + mock + SPA cover intensity, gated, FLIM, raw 1-bit, sweeps/scheduled/abort, calibration, safety/health, data handling, in-browser visualization, experiment log + presets + re-run, and a Playwright browser E2E harness (`test_10` + `test_15`). Code-review rounds applied (B-01..B-31, B-36 fixed; B-32..B-35, B-37 open — all hardware/edge). Browser E2E needs the optional `e2e` extra (`pip install -e ".[e2e]"` + `python -m playwright install chromium`); the `spa_client` fixture skips cleanly without it. **Phase 14 (post-PRD addition):** a spartan on-demand "Live" tab (`POST /api/live/frame` + `LivePage`) for hosts without the vendor GUI — single-shot or a 300 ms client-driven poll loop, no persistence/logging, same busy guard as any acquisition; see `tests/test_live.py` (8 tests). **Phase 15 (post-PRD addition):** dark-count (DCR) reference & correction for gated **and** intensity modes (`bridge/services/dark_reference.py`, `/api/calibrate/*-dark-reference`, `DarkReferenceControl`) plus manual WB min/max sliders on all image views (`WBRangeControl`) — display-only correction, raw data always persisted, full sidecar/log provenance; see `tests/test_dark_reference.py` (18 tests) and the [design doc](docs/design_gated_dcr_correction.md). **Phase 16 (post-PRD addition):** an acquisition **queue** (mixed intensity/gated series with per-item repeat, background task, own stop latch, every run logged — `bridge/services/queue.py`, `/api/queue/*`, Queue tab) and **paced gated** (`cooloff_s` on gated: one single-step `G` per offset with sleep between steps so the sensor cools; step boundaries get health-poll/stop protection; `cooloff_s` is part of the dark-reference fingerprint); see `tests/test_queue_and_paced.py` (9 tests). `main` is clean and green. **The only work left is hardware bring-up on the Windows host when the SPAD512² returns** — see the "Mock vs. real hardware" checklist in [constraints](docs/constraints.md) (B-32..B-35 + dark-correction physics).

## Testing

- Bridge tests run against the mock cSPAD server, not real hardware.
- Test each command path, serialization/busy behavior, safe-boundary abort, reconnect, sweep checkpoint/resume, auto-protect thresholds.
- End-to-end tests drive the SPA against bridge+mock.
- Verify produced files match reducer layout (`meta_*.json` + `movie_arr_*.npy`).
- **Git worktree gotcha:** background agents run in isolated worktrees, but the editable install (`pip install -e`) resolves `bridge`/`mock_server` back to the *main* checkout. In a worktree, always run tests as `PYTHONPATH="$PWD" pytest` or you'll test stale code and see phantom failures.

## Workflow

- Always run the mock server for development — never require the physical camera.
- Serialize all camera commands through the bridge's async queue.
- Preview frames sent to browser must be downsampled; full arrays stay on host.
- Check [constraints](docs/constraints.md) before making architectural decisions.

## Reference code (read-only, do not modify)

- `theoretical_info/piimaging_examples/cSPAD.py` — TCP protocol client
- `theoretical_info/piimaging_examples/python_tcp_stream_*.py` — streaming/decoding patterns
- `theoretical_info/piimaging_examples/python_image_metadata.py` — PNG metadata keys
- `theoretical_info/Piimaging-512-2-analysis-main/` — downstream analysis pipeline (must remain compatible)
