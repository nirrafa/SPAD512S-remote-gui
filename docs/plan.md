# Implementation Plan — SPAD512² Remote Control GUI

> **This is a living document.** Update status checkboxes, add notes, and revise estimates as work progresses. Each phase has a validation gate — do not advance until the gate passes.

**References:** [PRD](PRD.md) · [Constraints](constraints.md) · [CLAUDE.md](../CLAUDE.md) · [Pre-dev tests](../pre_dev_tests/)

---

## Table of contents

1. [Project setup & tooling](#phase-0-project-setup--tooling)
2. [Mock vendor server](#phase-1-mock-vendor-server)
3. [Bridge core](#phase-2-bridge-core)
4. [Intensity mode (end-to-end vertical slice)](#phase-3-intensity-mode-vertical-slice)
5. [Gated time-resolved mode](#phase-4-gated-time-resolved-mode)
6. [FLIM mode](#phase-5-flim-mode)
7. [Raw 1-bit single-photon mode](#phase-6-raw-1-bit-single-photon-mode)
8. [Calibration system](#phase-7-calibration-system)
9. [Safety, health & auto-protect](#phase-8-safety-health--auto-protect)
10. [Sweeps, scheduling & resilience](#phase-9-sweeps-scheduling--resilience)
11. [Data handling & reducer integration](#phase-10-data-handling--reducer-integration)
12. [Front-end visualization](#phase-11-front-end-visualization)
13. [Experiment log, presets & reproducibility](#phase-12-experiment-log-presets--reproducibility)
14. [Integration, polish & hardware bring-up](#phase-13-integration-polish--hardware-bring-up)

---

## Phase 0 — Project setup & tooling

**Goal:** Repository structure, dependencies, dev tooling, CI-ready skeleton.

### Tasks

- [x] Initialize git repository
- [x] Create Python package structure for the bridge
- [x] Create React/TypeScript app for the front-end
- [x] Set up linting, formatting, type checking for both sides
- [x] Write `pyproject.toml` with dev/test extras
- [x] Write `package.json` with scripts (dev, build, lint, test)
- [x] Configure pytest and vitest/jest
- [x] Create `.gitignore` for Python, Node, OS files

### File tree after this phase

```
├── bridge/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entrypoint
│   ├── config.py                # Settings (port, thresholds, paths)
│   └── py.typed
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       └── vite-env.d.ts
├── mock_server/
│   ├── __init__.py
│   └── server.py                # Mock vendor TCP server
├── tests/
│   ├── conftest.py
│   └── __init__.py
├── pre_dev_tests/               # (already exists)
├── docs/
│   ├── PRD.md
│   ├── constraints.md
│   └── plan.md
├── pyproject.toml
├── CLAUDE.md
└── .gitignore
```

### Validation gate

- [x] `pip install -e ".[dev]"` succeeds
- [x] `pytest --collect-only` discovers test infrastructure
- [x] `npm install && npm run build` produces a bundle
- [x] `uvicorn bridge.main:app` starts and responds to `GET /api/health`

---

## Phase 1 — Mock vendor server

**Goal:** A Python TCP server that implements the vendor cSPAD ASCII protocol so all development happens hardware-free. This is the foundation everything else tests against.

### Protocol analysis (from `cSPAD.py` and examples)

The vendor server speaks a simple ASCII protocol over TCP:

| Command | Wire format | Response |
|---|---|---|
| Connect | (client connects) | `"SPAD512S ..."` welcome banner |
| System info | `D` | Multi-line info string |
| Set path | `D,<path>` | Path confirmation |
| Voltages (read) | `V` | `"Vq,Vex"` |
| Voltages (set) | `V,<vex>` | Confirmation |
| Temperatures + freq | `R` | `"T_MSTR,T_SLV,T_PCB,T_CHIP,laser_freq,frame_freq"` |
| Cooling | `S,<0\|1>` | Confirmation |
| Auto-exposure | `AE,<mode>,<intTime>` | Confirmation |
| Pileup correction | `PU,<0\|1>` | Confirmation |
| Intensity acquire | `I,<bitDepth>,<intTime>,<iterations>,0,<overlap>,0,1,<im_width>` | Binary image data + `DONE` / `ERROR` |
| Gated acquire | `G,<bitDepth>,<intTime>,<iters>,<steps>,<stepSize>,<arbitrary>,<width>,<offset>,<dir>,<trig>,<overlap>,<stream>` | Binary image data + `DONE` |
| Arbitrary steps | `Ga,<step1>;<step2>;...` | Confirmation |
| Optimal gated params | `Gf,1,<stepSize>,<gateWidth>,1` | Multi-line: nbrSteps, offset, minStep |
| FLIM calibrate | `F,c,<mode>,<intTime>,<expTau>,<gateWidth>` | Calibration result or `ERROR` |
| FLIM acquire | `F,i,<intTime>,<subsample>,<rawFlag>,1` | Text data lines + `DONE` |
| Noise calibration | `CALIB,0` | `"Noise calibration complete."` |
| Dead pixel cal | `CALIB,1` | Confirmation |
| Master/slave offset | `CALIB,2` | Confirmation |
| Breakdown cal | `CALIB,3` | Multi-step handshake → `"The breakdown is around X"` |

### Tasks

- [x] Implement TCP listener with asyncio (bind `127.0.0.1`, configurable port)
- [x] Parse incoming ASCII commands and dispatch to handlers
- [x] `D` handler: return synthetic system info (FPGA serials, versions, sensor size, features)
- [x] `V` handler: return/set mock voltages
- [x] `R` handler: return mock temperatures + frequencies
- [x] `S` handler: cooling enable/disable
- [x] `PU` handler: pileup correction toggle
- [x] `I` handler: generate synthetic 512×512 image data in the correct binary format
  - [x] ≤8-bit: 1 byte per pixel
  - [x] ≥9-bit: 2 bytes per pixel (little-endian, odd/even interleave)
  - [x] 1-bit: packed binary (`np.unpackbits` compatible)
  - [x] Append `DONE` sentinel
- [x] `G` handler: generate synthetic gated stack (`iterations × gate_steps` frames)
- [x] `Ga` handler: accept arbitrary step arrays
- [x] `Gf` handler: return computed optimal parameters
- [x] `F,c` handler: FLIM IRF calibration (store state, return result)
- [~] `F,i` handler: returns phasor data for now (CSV-line text format deferred to Phase 5 FLIM work)
- [x] `CALIB,0/1/2/3` handlers with correct framing (including breakdown handshake)
- [x] `D,<path>` handler: set path
- [x] `AE` handler: auto-exposure
- [x] Error response for unknown commands
- [x] Test helpers: `set_temperature()`, `set_voltage()`, `set_laser_frequency()`, `fail_after_n_commands()`, `set_next_response_delay()`
- [x] CLI entry point: `python -m mock_server --port 9999`

### Files

```
mock_server/
├── __init__.py
├── server.py            # AsyncIO TCP server, command dispatcher
├── handlers.py          # Per-command handler functions
├── synthetic_data.py    # Numpy-based synthetic image/decay/phasor generators
├── state.py             # Mutable server state (temps, voltages, calibration flags)
└── cli.py               # CLI entry point
```

### Validation gate

- [x] `pre_dev_tests/test_14_mock_vendor_server.py` — all 19 tests pass
- [x] Can connect with the original `cSPAD.py` client and run `get_info()`, `get_temps()`, `get_intensity()` successfully
- [x] Binary data decoded by `cSPAD.get_intensity()` produces a valid numpy array (`(512, 512, 1)` uint16)

---

## Phase 2 — Bridge core

**Goal:** FastAPI app that owns the single TCP connection to the vendor server (or mock), serializes commands through an async queue, exposes REST + WebSocket, and manages busy/idle state.

### Architecture

```
                    ┌─────────────────────────────────┐
                    │         FastAPI (bridge)         │
                    │                                  │
  HTTP/WS ────────►│  REST routes    WebSocket hub     │
                    │       │              │            │
                    │       ▼              ▼            │
                    │   ┌─────────────────────┐        │
                    │   │   Command Queue      │        │
                    │   │   (asyncio.Queue)     │        │
                    │   └─────────┬───────────┘        │
                    │             ▼                     │
                    │   ┌─────────────────────┐        │
                    │   │  Protocol Client     │        │
                    │   │  (wraps cSPAD)       │        │
                    │   └─────────┬───────────┘        │
                    │             │ TCP                  │
                    └─────────────┼────────────────────┘
                                  ▼
                          Vendor server / Mock
```

### Tasks

- [x] Protocol client: async wrapper around `cSPAD.py` logic
  - [x] Async TCP connect with configurable host/port
  - [x] Handle welcome banner + breakdown calibration handshake on connect (double-D)
  - [x] `send_command(cmd: str) -> str` for text responses (DONE-stripping)
  - [x] `send_acquire(cmd: str, ...) -> bytes` for binary image data
  - [x] Auto-reconnect on connection loss with exponential backoff (fixed-port rebind)
  - [x] Connection state observable + **passive idle-EOF disconnect detection**
- [~] Command queue: serialization via the protocol client's asyncio lock + instrument busy guard
  - [x] Reject new commands while an acquisition is running (busy error)
  - [ ] Formal `asyncio.Queue` consumer + health-poll bypass — deferred to Phase 3 (`test_13`) / Phase 8
- [x] Instrument state manager
  - [x] States: `idle`, `acquiring`, `calibrating`, `stopping`
  - [ ] Track current operation metadata (mode, params, progress) — Phase 3
  - [x] Broadcast state changes to all WebSocket clients
- [x] WebSocket hub
  - [x] Client registry (connect/disconnect tracking)
  - [x] Broadcast methods: `broadcast_state/progress/preview/alarm`
  - [x] Tolerates slow/dead clients (drops on send failure)
- [x] REST API skeleton
  - [x] `GET /api/health`, `GET /api/status`
  - [x] `GET /api/system/info`, `GET /api/system/triggers`
  - [x] `POST /api/acquire/stop` (minimal; safe-boundary refinement in Phase 9)
  - [x] `WS /ws`
- [x] Configuration via environment variables (`SPAD_` prefix; vendor/bridge host+port)
- [x] CORS middleware for LAN access (allow all origins)

### Files

```
bridge/
├── __init__.py
├── main.py              # FastAPI app, lifespan, startup/shutdown
├── config.py            # Pydantic settings
├── protocol/
│   ├── __init__.py
│   ├── client.py        # Async TCP client wrapping cSPAD logic
│   ├── commands.py      # Command string builders
│   └── decoder.py       # Binary response decoders (intensity, gated, FLIM, 1-bit)
├── core/
│   ├── __init__.py
│   ├── queue.py         # Command queue + consumer task
│   ├── state.py         # Instrument state manager
│   └── ws_hub.py        # WebSocket client registry + broadcast
├── routes/
│   ├── __init__.py
│   ├── health.py        # GET /api/health, /api/status
│   ├── system.py        # GET /api/system/info, /api/system/triggers
│   └── ws.py            # WS /ws endpoint
└── models/
    ├── __init__.py
    └── responses.py     # Pydantic response models
```

### Validation gate

- [x] Bridge starts, connects to mock server, `GET /api/status` returns `vendor_connected: true`
- [x] `GET /api/system/info` returns parsed FPGA serials, versions, features
- [x] `GET /api/system/triggers` returns laser/frame frequencies
- [x] WebSocket connects, receives state broadcasts
- [x] Mock server restart → bridge auto-reconnects
- [x] `pre_dev_tests/test_01_connection_and_sysinfo.py` — all 14 tests pass
- [x] `pre_dev_tests/test_12_bridge_reliability.py` — `TestAutoReconnect` (3 tests) pass

---

## Phase 3 — Intensity mode (vertical slice)

**Goal:** First complete end-to-end path: configure intensity acquisition in the browser → bridge sends command to mock → binary data decoded → preview sent to browser → files saved on host. This proves the full stack works before adding more modes.

### Tasks

- [x] Bridge: intensity acquisition endpoint
  - [x] `POST /api/acquire/intensity` accepting all parameters (+ `timeout_s`)
  - [x] Validate parameters against device capabilities (valid bit depths, ROI widths)
  - [x] Auto-switch integration time units (µs for 1/4-bit, ms for ≥6-bit) → `integration_time_unit`
  - [x] Build and send `PU` + `I` command strings
  - [x] Decode binary response using the correct path per bit depth
  - [x] Generate downsampled preview
  - [x] Broadcast busy + preview over WebSocket
  - [x] Return result (`host_path`, `preview`, `total_frames`, `integration_time_unit`)
- [~] Bridge: progress tracking — coarse (busy at start, idle/preview at end); per-iteration progress deferred (single `I` command streams all frames) to Phase 9
- [x] Front-end: intensity mode panel (form, Acquire, progress bar, busy indicator)
- [x] Front-end: image canvas component (render, colormap grayscale/viridis/inferno/plasma, server-side auto-stretch, wheel-zoom + drag-pan)
- [x] Basic file saving — minimal `movie_arr.npy` per `acqNNNNN/`; full PNG folder + sidecar in Phase 10
- [x] **Background acquisition runner** (busy guard, per-op `timeout_s`, result grace) — new; required by `test_13` serialization/timeout semantics

### Files (new/modified)

```
bridge/routes/
    └── acquire.py           # POST /api/acquire/intensity (and later other modes)
bridge/core/
    └── acquisition.py       # Acquisition runner (common logic)
bridge/services/
    ├── __init__.py
    ├── intensity.py         # Intensity-specific logic
    └── preview.py           # Downsampling + preview encoding

frontend/src/
    ├── api/
    │   ├── client.ts        # HTTP + WebSocket client
    │   └── types.ts         # API response types
    ├── components/
    │   ├── AcquireButton.tsx
    │   ├── ImageCanvas.tsx   # 512×512 canvas with colormap/zoom
    │   ├── ProgressBar.tsx
    │   └── StatusBanner.tsx  # Busy/idle/error state
    ├── pages/
    │   └── IntensityPage.tsx
    └── hooks/
        ├── useWebSocket.ts
        └── useAcquisition.ts
```

### Validation gate

- [x] `pre_dev_tests/test_02_acquisition_intensity.py` — all 26 tests pass
- [x] `pre_dev_tests/test_13_concurrency_and_serialization.py` — 4/5 (serialization, busy rejection, busy broadcast ×2); `test_health_polling_during_busy` deferred to Phase 8
- [x] Acquire 8-bit/100ms/1-iter → `done` + 256×256 preview returned (verified e2e via curl; GUI renders it)
- [x] Acquire while busy → `{"status":"error","message":"instrument busy"}`
- [~] WebSocket receives busy + preview frames during acquisition (per-iteration progress deferred to Phase 9)
- [x] Files saved on host: `data/intensity_images/acqNNNNN/movie_arr.npy`, shape `(nframes, 512, 512)` uint16

---

## Phase 4 — Gated time-resolved mode

**Goal:** Add gated acquisition, including arbitrary steps and optimal parameter helper.

### Tasks

- [x] Bridge: gated acquisition endpoint `POST /api/acquire/gated`
  - [x] All gated parameters (direction `forward/reverse`→0/1, trigger `internal/external`→0/1)
  - [x] Arbitrary step array support (Ga command before G; gate_steps = len(array))
  - [x] Decode gated binary data (iterations × gate_steps frames)
  - [x] Send preview per gate step over WebSocket (`previews_sent` count, index/count in message)
- [x] Bridge: optimal parameters endpoint `GET /api/acquire/gated/optimal-params` (wraps Gf → steps/offset/min_step)
- [x] Front-end: gated mode panel (all params, Auto-fill optimal, comma-separated arbitrary steps)
- [x] Gate step scrubber: slider browses per-step previews (collected from WS, reset each acquire)
- [x] Mode tabs (Intensity / Gated) in `App.tsx`

### Files (new/modified)

```
bridge/services/
    └── gated.py             # Gated-specific logic
frontend/src/pages/
    └── GatedPage.tsx
frontend/src/components/
    └── GateStepSlider.tsx
```

### Validation gate

- [x] `pre_dev_tests/test_03_acquisition_gated.py` — all 12 tests pass
- [x] Browser: acquire 20 gate steps → scrub through them on canvas (slider over WS previews)
- [x] Optimal params button fills form → acquire succeeds (verified e2e: steps 56/offset 50/min_step 18)
- [x] Arbitrary steps array accepted and produces correct number of frames (e2e: 6 steps)

---

## Phase 5 — FLIM mode

**Goal:** FLIM IRF calibration + FLIM acquisition + phasor data extraction.

### Tasks

- [x] Bridge: FLIM calibration endpoint `POST /api/calibrate/flim-irf`
  - Mono/bi-exponential, expected τ, gate width (short/medium/long → 0/1/2)
  - Store calibration state (`app.state.flim_irf_calibrated`; generalized in Phase 7)
- [x] Bridge: FLIM acquisition endpoint `POST /api/acquire/flim`
  - Warns (status `done` + `warning`) if no prior IRF calibration
  - Decode FLIM text data (CSV lines → pixel arrays → frames)
  - Extract phasor components (g, s); compute lifetime map host-side
  - Gate subsampling, image vs raw output
- [x] Front-end: FLIM mode panel
  - IRF calibration section
  - Acquisition parameters
  - Phasor scatter (basic SVG over the semicircle; full visualization in Phase 11)
  - Lifetime map via `ImageCanvas`

### Files (new/modified)

```
bridge/services/
    └── flim.py              # FLIM calibration + acquisition logic
bridge/protocol/
    └── decoder.py           # Add FLIM text decoder
frontend/src/pages/
    └── FLIMPage.tsx
```

### Validation gate

- [x] `pre_dev_tests/test_04_acquisition_flim.py` — all 11 tests pass (9 cases; gate_width parametrized ×3)
- [x] IRF calibration completes → calibration state updated
- [x] FLIM acquisition without calibration → warning shown (status `done` + `warning`)
- [x] Phasor g/s components returned in response

---

## Phase 6 — Raw 1-bit single-photon mode

**Goal:** Dedicated 1-bit path with binary unpacking for photon-statistics work.

### Tasks

- [ ] Bridge: raw 1-bit endpoint `POST /api/acquire/raw-1bit`
  - Uses intensity path with bit_depth=1
  - Distinct binary unpacking (np.unpackbits, rot90)
  - Tag decode_method as "binary_unpack"
- [ ] Front-end: raw 1-bit panel (lightweight — reuses intensity panel with locked bit depth)

### Files (new/modified)

```
bridge/services/
    └── raw_1bit.py
frontend/src/pages/
    └── Raw1BitPage.tsx
```

### Validation gate

- [ ] `pre_dev_tests/test_05_acquisition_raw_1bit.py` — all 5 tests pass
- [ ] Decode produces 512×512 binary images
- [ ] Multiple iterations produce correct frame count

---

## Phase 7 — Calibration system

**Goal:** Guided calibration flows, state tracking, staleness detection, DCR QA curves.

### Tasks

- [x] Bridge: calibration state store (SQLite or in-memory with persistence)
  - Per-calibration: state (none/running/done/failed), timestamp, stale flag
  - Staleness rules (e.g., noise cal stale after 24h or Vex change)
- [x] Bridge: calibration endpoints
  - `POST /api/calibrate/breakdown` — auto on connect
  - `POST /api/calibrate/noise` — requires dark, returns setup prompt
  - `POST /api/calibrate/dead-pixel` — requires dark
  - `POST /api/calibrate/master-slave-offset` — requires uniform pulsed illumination
  - `GET /api/calibration/status` — all calibration states
  - `GET /api/calibration/dcr-curve` — sorted DCR curve data after noise/dead cal
- [x] Bridge: uncalibrated warning logic
  - Before any acquisition, check calibration state
  - Return warning field if noise/dead-pixel calibration is missing or stale
- [x] Bridge: DCR curve computation
  - After noise/dead calibration, take a short dark measurement
  - Sort pixel values, compute DCR vs percentage curve
- [x] Front-end: calibration dashboard page
  - Status cards for each calibration type (with timestamp, stale badge)
  - Guided prompts: "Cap the objective", "Provide uniform pulsed source"
  - DCR curve chart (before/after, as in `cSPAD_example_script.py`)
  - Warning banner on mode pages when uncalibrated

### Files (new/modified)

```
bridge/services/
    └── calibration.py       # Calibration runner + state store
bridge/routes/
    └── calibration.py       # Calibration REST endpoints
bridge/core/
    └── calibration_state.py # Persistence + staleness logic

frontend/src/pages/
    └── CalibrationPage.tsx
frontend/src/components/
    ├── CalibrationCard.tsx
    ├── DCRCurveChart.tsx
    └── UncalibratedWarning.tsx
```

### Validation gate

- [x] `pre_dev_tests/test_07_calibration.py` — all 13 tests pass
- [x] Breakdown calibration runs on bridge startup
- [x] Noise calibration returns setup prompt, completes, updates state
- [x] DCR curve data available after noise calibration
- [x] Intensity acquisition with no noise cal → response includes warning
- [x] Browser: calibration page shows status cards, DCR chart renders

---

## Phase 8 — Safety, health & auto-protect

**Goal:** Continuous health monitoring, alarm system, auto-protect with configurable thresholds.

### Tasks

- [ ] Bridge: health poller background task
  - Poll `R` (temps + freq), `V` (voltages), `S` (cooling) on configurable interval
  - Store latest readings
  - Do not interleave with in-flight acquisitions (wait for idle or use read-only bypass)
- [ ] Bridge: alarm evaluation engine
  - Over-temperature (per sensor, configurable thresholds)
  - Cooling failure/disabled
  - Missing laser trigger (freq ≈ 0)
  - Abnormal laser trigger (freq outside expected range)
  - Suspected overexposure (pixel saturation metric)
- [ ] Bridge: auto-protect actions
  - Abort acquisition on threshold breach
  - Optionally reduce Vex to safe value
  - Require confirmation for high Vex settings
- [ ] Bridge: health REST + WebSocket
  - `GET /api/health/readings` — latest temps, voltages, cooling, freqs, alarms
  - `GET /api/health/config` — current thresholds
  - `PUT /api/health/config` — update thresholds
  - `POST /api/settings/vex` — set Vex with confirmation requirement
  - Alarms broadcast over WebSocket to all clients
- [ ] Front-end: health dashboard
  - Temperature gauges / readouts
  - Voltage display
  - Cooling status
  - Alarm list with severity levels
  - Threshold configuration form
  - Alarm toast/notification overlay

### Files (new/modified)

```
bridge/services/
    └── health.py            # Health poller + alarm engine
bridge/core/
    └── auto_protect.py      # Auto-protect logic (abort, reduce bias)
bridge/routes/
    └── health.py            # Health REST endpoints

frontend/src/pages/
    └── HealthPage.tsx
frontend/src/components/
    ├── TemperatureGauge.tsx
    ├── AlarmBanner.tsx
    └── ThresholdConfig.tsx
```

### Validation gate

- [ ] `pre_dev_tests/test_08_safety_and_health.py` — all 17 tests pass
- [ ] Health readings update on interval
- [ ] Mock server: set chip temp to 85°C → alarm fires → WebSocket receives alarm
- [ ] Running acquisition + over-temp → acquisition aborts with reason
- [ ] Health polling continues during acquisition
- [ ] High Vex setting → confirmation required

---

## Phase 9 — Sweeps, scheduling & resilience

**Goal:** Parameter sweeps with checkpointing, scheduled/overnight jobs, and resilient execution that survives browser disconnects.

### Tasks

- [ ] Bridge: sweep runner
  - `POST /api/acquire/sweep` — iterate parameters over range/list
  - Checkpoint after each completed point (write to SQLite)
  - Label each result with parameter value
  - Support single-parameter and multi-parameter (cartesian product) sweeps
  - Continue running if browser disconnects
  - `POST /api/acquire/sweep/resume` — resume from last checkpoint after failure
- [ ] Bridge: scheduled job runner
  - `POST /api/acquire/schedule` — queue a job with a start time
  - `GET /api/acquire/schedule/<job_id>` — job status
  - Time-triggered execution (asyncio scheduler or APScheduler)
  - Jobs visible in experiment log
  - Run unattended, persist results
- [ ] Bridge: acquisition status endpoint
  - `GET /api/acquire/status` — current operation state, progress, mode, ETA
  - Reports running/completed even after browser reconnect
- [ ] Bridge: safe-boundary stop (refine from Phase 2)
  - Between iterations, between sweep points, between gate steps
  - In-flight frame always completes
  - Report stop boundary in response
  - Hardware left in idle state after stop

### Files (new/modified)

```
bridge/services/
    ├── sweep.py             # Sweep runner + checkpoint logic
    └── scheduler.py         # Scheduled job runner
bridge/core/
    └── checkpoint.py        # Checkpoint persistence (SQLite)
bridge/routes/
    └── acquire.py           # Add sweep, schedule, status endpoints
bridge/models/
    └── sweep.py             # Sweep config + result models

frontend/src/pages/
    └── SweepPage.tsx
frontend/src/components/
    ├── SweepConfig.tsx      # Parameter range/list input
    ├── SweepProgress.tsx    # Per-point progress
    └── ScheduleForm.tsx
```

### Validation gate

- [ ] `pre_dev_tests/test_06_acquisition_styles.py` — all 14 tests pass
- [ ] `pre_dev_tests/test_12_bridge_reliability.py` — all 9 tests pass
- [ ] 5-point sweep completes → 5 labeled results with checkpoints
- [ ] Sweep survives browser disconnect → reconnect shows progress/completion
- [ ] Sweep resume after simulated crash → skips completed points
- [ ] Scheduled job triggers at specified time
- [ ] Stop during sweep → stops at next safe boundary

---

## Phase 10 — Data handling & reducer integration

**Goal:** File organization matching lab conventions, reducer pipeline producing `meta_*.json` + `movie_arr_*.npy`, JSON sidecar with full metadata.

### Tasks

- [ ] Bridge: save path management
  - `POST /api/settings/save-path` — set host save directory
  - `D,<path>` command to vendor server
- [ ] Bridge: file organization
  - `data/intensity_images/acqXXXXX/` with `IMGxxxxx.png`
  - `data/gated_images/acqXXXXX/` with `IMGxxxxx.png`
  - Auto-incrementing acquisition numbers
  - PNG files with embedded metadata (Author, Mode, Integration time, Laser frequency, gate params, triggers, SW version)
- [ ] Bridge: JSON sidecar writer
  - Full parameter set
  - Calibration state snapshot
  - Temperatures at acquisition time
  - Timestamps (start, end)
  - Sample/experiment name and notes
  - Superset aligned with reducer's meta format
- [ ] Bridge: reducer integration
  - Port `Reduce_size_512SPAD.py` logic as a callable service
  - Input: PNG folder → output: `meta_acqXXXXX.json` + `movie_arr_acqXXXXX.npy`
  - 3D array shape: `nframes × x × y` (matching existing pipeline)
  - Optional: run automatically after acquisition or on-demand
- [ ] Bridge: data listing + download endpoints
  - `GET /api/data/list?path=<path>` — list files in a host directory
  - `GET /api/data/download?path=<path>` — download file/folder from host
  - `GET /api/data/sidecar?path=<path>` — read JSON sidecar
- [ ] Compatibility verification
  - Load `movie_arr_*.npy` with `512^2_*.py` reference code
  - Load `meta_*.json` and verify keys match expectations
  - Run `SEP_D.py` analysis functions on test data

### Files (new/modified)

```
bridge/services/
    ├── file_writer.py       # PNG saving with metadata, folder structure
    ├── sidecar.py           # JSON sidecar generation
    └── reducer.py           # Port of Reduce_size_512SPAD.py
bridge/routes/
    └── data.py              # Data listing, download, sidecar endpoints

tests/
    └── test_data_compat.py  # Verify output is loadable by downstream scripts
```

### Validation gate

- [ ] `pre_dev_tests/test_09_data_handling.py` — all 18 tests pass
- [ ] Intensity acquisition → PNG folder created in correct layout
- [ ] PNGs contain expected metadata keys
- [ ] JSON sidecar contains params, calibration state, temps, timestamps
- [ ] Reducer produces `meta_acqXXXXX.json` + `movie_arr_acqXXXXX.npy`
- [ ] `movie_arr` shape is `(nframes, x, y)`
- [ ] Downstream script `SEP_D.py` loads the data without modification
- [ ] Full data download from browser works

---

## Phase 11 — Front-end visualization

**Goal:** All in-browser visualization: image canvas with ROI, per-ROI decay curves, phasor scatter, lifetime map, pixel histogram, DCR curve.

### Tasks

- [ ] Image canvas (enhance from Phase 3)
  - Rectangular ROI drawing (click + drag)
  - Freehand ROI drawing
  - Multiple simultaneous ROIs with labels
  - ROI pixel statistics (mean, sum, area)
  - Intensity scaling controls (min/max sliders, auto-stretch button)
- [ ] Per-ROI decay curve
  - For gated acquisitions: extract counts vs gate offset for ROI pixels
  - Plot with Plotly or lightweight chart library
  - Update when ROI moves/resizes
- [ ] FLIM visualization
  - Phasor scatter plot (g vs s, semi-circle reference)
  - False-color lifetime map (τ → color)
  - Colorbar with lifetime scale
- [ ] Histograms
  - Pixel value histogram for any acquisition
  - Sorted DCR curve (already in calibration page — link here too)
- [ ] Layout: mode-specific visualization presets
  - Intensity: image + histogram
  - Gated: image + gate slider + decay curve
  - FLIM: lifetime map + phasor scatter

### Files (new/modified)

```
frontend/src/components/
    ├── ImageCanvas.tsx       # Enhanced with ROI
    ├── ROIOverlay.tsx        # ROI drawing + selection layer
    ├── DecayCurve.tsx        # Counts vs gate offset chart
    ├── PhasorPlot.tsx        # Phasor scatter with semi-circle
    ├── LifetimeMap.tsx       # False-color lifetime image
    ├── PixelHistogram.tsx    # Pixel value distribution
    └── DCRCurveChart.tsx     # (from Phase 7, enhanced)
frontend/src/hooks/
    └── useROI.ts            # ROI state management
frontend/src/utils/
    ├── colormap.ts          # Colormap lookup tables
    ├── phasor.ts            # Phasor computation from gated data
    └── imageProcessing.ts   # Downscaling, stretching, statistics
```

### Validation gate

- [ ] `pre_dev_tests/test_10_visualization.py` — all 12 tests pass (via Playwright/browser automation)
- [ ] Browser: draw rectangular ROI on intensity image → see pixel stats
- [ ] Browser: gated acquisition → draw ROI → decay curve updates
- [ ] Browser: FLIM acquisition → phasor scatter renders with semi-circle
- [ ] Browser: lifetime map shows false-color pixels
- [ ] Browser: pixel histogram visible after intensity acquisition

---

## Phase 12 — Experiment log, presets & reproducibility

**Goal:** Persistent experiment log, named presets, sample/experiment tagging, re-run from history.

### Tasks

- [ ] Bridge: SQLite database schema
  - `experiments` table: id, mode, params (JSON), result_path, sidecar_path, calibration_state (JSON), temperatures (JSON), timestamp, sample_name, experiment_name, notes, scheduled (bool)
  - `presets` table: id, name, mode, params (JSON), created_at
- [ ] Bridge: experiment log endpoints
  - `GET /api/experiment-log` — list (with pagination: limit, offset)
  - `GET /api/experiment-log?search=<query>` — search by sample/experiment name
  - `POST /api/experiment-log/<id>/rerun` — re-run with optional overrides
  - Auto-log every acquisition (single-shot, sweep point, scheduled)
- [ ] Bridge: preset endpoints
  - `POST /api/presets` — save preset (name, mode, params)
  - `GET /api/presets?mode=<mode>` — list presets for a mode
  - `DELETE /api/presets/<id>` — delete preset
  - `GET /api/presets/<id>` — load preset
- [ ] Bridge: sample/experiment naming
  - Accept `sample_name`, `experiment_name`, `notes` on all acquire endpoints
  - Store in sidecar + experiment log
  - Optionally drive folder organization (sample subfolder)
- [ ] Front-end: experiment log page
  - Table with sortable columns (date, mode, sample, experiment)
  - Search bar
  - Click row → see full details + re-run button
  - Re-run dialog: shows original params, allows editing before re-run
- [ ] Front-end: preset panel (per mode page)
  - Save current config as preset
  - Load preset dropdown
  - Delete preset

### Files (new/modified)

```
bridge/services/
    └── experiment_log.py    # Log + preset CRUD
bridge/routes/
    └── experiments.py       # Log + preset REST endpoints
bridge/db/
    ├── __init__.py
    ├── schema.py            # SQLite schema + migration
    └── repository.py        # DB access layer

frontend/src/pages/
    └── ExperimentLogPage.tsx
frontend/src/components/
    ├── ExperimentTable.tsx
    ├── RerunDialog.tsx
    ├── PresetSelector.tsx
    └── SampleNameInput.tsx
```

### Validation gate

- [ ] `pre_dev_tests/test_11_reproducibility_and_workflow.py` — all 16 tests pass
- [ ] Every acquisition auto-logged → visible in experiment log
- [ ] Save preset → load preset → parameters match
- [ ] Re-run from log → identical acquisition succeeds
- [ ] Re-run with overrides → modified parameters used
- [ ] Search by sample name returns matching entries
- [ ] Browser: experiment log page renders, search works, re-run dialog opens

---

## Phase 13 — Integration, polish & hardware bring-up

**Goal:** Full integration testing, E2E scenarios, UI polish, and validation on real hardware.

### Tasks

- [ ] Wire `pre_dev_tests/conftest.py` fixtures to real implementations
- [ ] Run full pre-dev test suite — target: all 185 tests pass
- [ ] E2E test suite with Playwright (browser automation against bridge+mock)
  - All scenarios from `pre_dev_tests/test_15_end_to_end.py`
- [ ] Front-end: navigation & layout
  - Mode tab bar (Intensity, Gated, FLIM, Raw 1-bit)
  - Side panel: calibration status summary + health indicators
  - Top bar: connection status, busy state, sample name
  - Responsive layout for various screen sizes
- [ ] Front-end: error handling & edge cases
  - Connection lost → reconnect banner
  - Acquisition failure → error display with details
  - Form validation (out-of-range params, required fields)
- [ ] Production build & deployment
  - Bridge serves SPA static files in production
  - Single-command startup: `python -m bridge` (starts bridge + serves frontend)
  - Startup checks: vendor server reachable, port available
- [ ] Documentation
  - README: setup, configuration, usage
  - Host PC setup guide (Windows)
  - API reference (auto-generated from FastAPI OpenAPI spec)
- [ ] Hardware bring-up on Windows host
  - [ ] Install Python + Node on host PC
  - [ ] Start vendor software
  - [ ] Start bridge → verify connection
  - [ ] One intensity acquisition → verify image
  - [ ] One gated acquisition → verify stack
  - [ ] One FLIM acquisition → verify phasor data
  - [ ] Calibration flow → verify all types
  - [ ] Health monitoring → verify real temperatures
  - [ ] Verify produced files match pipeline expectations

### Validation gate

- [ ] All 185 pre-dev spec tests pass
- [ ] E2E test suite passes against mock
- [ ] Bridge starts and serves SPA from a single command
- [ ] On Windows host with real camera: one successful acquisition per mode
- [ ] Produced `meta_*.json` + `movie_arr_*.npy` load in downstream scripts

---

## Dependency graph

```
Phase 0 (setup)
    │
    ▼
Phase 1 (mock server) ─────────────────────────────────────┐
    │                                                       │
    ▼                                                       │
Phase 2 (bridge core)                                       │
    │                                                       │
    ▼                                                       │
Phase 3 (intensity — vertical slice) ◄──────────────────────┘
    │
    ├──► Phase 4 (gated)
    │       │
    │       ├──► Phase 5 (FLIM)
    │       │
    │       └──► Phase 6 (raw 1-bit)
    │
    ├──► Phase 7 (calibration)
    │       │
    │       └──► Phase 8 (safety/health)
    │
    ├──► Phase 9 (sweeps/scheduling)
    │
    ├──► Phase 10 (data/reducer)
    │
    ├──► Phase 11 (visualization)
    │
    └──► Phase 12 (experiment log/presets)
            │
            ▼
        Phase 13 (integration + hardware)
```

Phases 4–12 can be parallelized after Phase 3, but the recommended order above minimizes rework. Specifically:
- **Phases 4–6** (modes) build on the intensity vertical slice pattern
- **Phase 7** (calibration) should precede **Phase 8** (safety) since safety checks reference calibration state
- **Phase 10** (data) can run in parallel with visualization/log work
- **Phase 13** must come last

---

## Mapping to pre-dev tests

| Phase | Pre-dev test files | Test count |
|---|---|---|
| 1 | `test_14_mock_vendor_server.py` | 19 |
| 2 | `test_01_connection_and_sysinfo.py`, `test_12_bridge_reliability.py` (partial) | 14 + 5 |
| 3 | `test_02_acquisition_intensity.py`, `test_13_concurrency_and_serialization.py` | 11 + 5 |
| 4 | `test_03_acquisition_gated.py` | 12 |
| 5 | `test_04_acquisition_flim.py` | 9 |
| 6 | `test_05_acquisition_raw_1bit.py` | 5 |
| 7 | `test_07_calibration.py` | 13 |
| 8 | `test_08_safety_and_health.py` | 17 |
| 9 | `test_06_acquisition_styles.py`, `test_12_bridge_reliability.py` (remaining) | 14 + 4 |
| 10 | `test_09_data_handling.py` | 18 |
| 11 | `test_10_visualization.py` | 12 |
| 12 | `test_11_reproducibility_and_workflow.py` | 16 |
| 13 | `test_15_end_to_end.py` | 11 |
| **Total** | | **185** |

---

## Notes & decisions log

> Add entries here as decisions are made during implementation.

| Date | Decision | Rationale |
|---|---|---|
| 2026-06-27 | Target Python 3.11 (via `~/.local/bin/python3.11`), not system 3.9 | Pydantic v2 / modern FastAPI; `.venv` created with 3.11 |
| 2026-06-27 | Frontend uses Vite's current React-TS template (React 19, oxlint, vitest) | Default modern toolchain; oxlint replaces ESLint, faster |
| 2026-06-27 | Config via `pydantic-settings` with `SPAD_` env prefix | Typed settings, env-overridable for host deployment |
| 2026-06-27 | Vite dev proxy forwards `/api` + `/ws` to bridge at `127.0.0.1:8080` | SPA dev server talks to bridge without CORS friction |
| 2026-06-27 | Repo: public GitHub `nirrafa/SPAD512S-remote-gui` | Per user request |
| 2026-06-27 | Mock = shared pure protocol core + two front-ends (in-process harness, asyncio TCP) | One source of truth exercised by both spec tests and the real cSPAD client |
| 2026-06-27 | `F,i` returns phasor data only in Phase 1; CSV-line FLIM text format deferred to Phase 5 | test_14 only needs `last_phasor_data`; text decoder belongs with FLIM work |
| 2026-06-28 | Phase 5 FLIM: bridge always requests **raw** FLIM and computes phasor/lifetime host-side | Avoids the vendor's image-vs-raw file-path duality; cleaner architecture, satisfies the spec |
| 2026-06-28 | Mock streams real FLIM CSV shape but with a small gate-frame count (8, reduced by subsampling) | Full-res 512×512×frames CSV is too heavy for the suite; full format validated on hardware (Phase 13) |
| 2026-06-28 | FLIM IRF calibration tracked by a minimal `app.state.flim_irf_calibrated` flag | Phase 7 replaces it with a persistent calibration store |
| 2026-06-27 | Bridge detects disconnect *passively* via an idle EOF watcher (read(1) between commands) | `/api/status` must report disconnected with no retry and no health poll; the protocol is request/response so an idle read only returns on EOF |
| 2026-06-27 | Mock TCP server closes active connections on `stop()` and rebinds the **same port** on restart | Needed for the bridge to observe the drop and to reconnect to a stable address |
| 2026-06-27 | Phase 2 command "queue" = protocol-client asyncio lock + instrument busy guard; formal queue deferred | Lock already serializes; busy-rejection queue + health bypass are driven by `test_13` (Phase 3) and Phase 8 |
| 2026-06-27 | Added `pytest-timeout` (default 60s, thread method) | A blocked WebSocket/lifespan can hang the suite; per-test timeout surfaces *where* |
| 2026-06-27 | Fleshed out stub test `test_01::test_bridge_configurable_port` | Spec stub raised `NotImplementedError`; gate requires all 14 — implemented faithfully (connect on a non-9999 port) |
| 2026-06-28 | Acquisitions run as a **background task** with a result-grace window (`done` if fast, else `running`) | `test_13` rejects a second acquire while busy via *sequential* blocking calls — only possible if the first returns before completing; also yields the `timeout_s` semantics |
| 2026-06-28 | Mock tiles one frame ×iterations and paces the chunked wire write | Generating N distinct frames blocked the mock loop (teardown timeouts); tiling is O(1) and pacing keeps a large acquisition reliably longer than the grace so busy-rejection is deterministic |
| 2026-06-28 | Runner owns busy/idle WS broadcasts; instrument state changes are **not** auto-pushed | `test_13` expects the first WS frame after an acquire to be `type:"busy"`; an auto `state` broadcast on the ACQUIRING transition arrived first |
| 2026-06-28 | Preview = base64 uint8 (≤256², server auto-stretched); colormap applied client-side | Keeps the WS/HTTP payload small (full arrays stay on host per constraints); browser owns grayscale/viridis/inferno/plasma + zoom/pan |
| 2026-06-28 | `test_13::test_health_polling_during_busy` deferred to Phase 8 | `/api/health/readings` is Phase 8 (Safety & Health); chosen with the user |
| 2026-06-28 | Gated acquisitions run **synchronously** (request awaits completion) | No gated busy/timeout spec (cf. `test_13` for intensity); awaiting guarantees the response carries `total_gate_steps`/`previews_sent` |
| 2026-06-28 | Per-gate-step previews broadcast over WS with `index`/`count`; front-end collects + scrubs | Spec requires a preview per gate step; the GUI scrubber reconstructs the stack from these (full arrays stay on host) |
