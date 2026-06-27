# PRD — SPAD512² Remote Control GUI (Suchowski Lab)

## Context

The Suchowski (FemtoNano) lab at TAU operates a **Pi Imaging SPAD512²** single-photon avalanche-diode array camera (512×512). Today it is driven only by Pi Imaging's vendor software running on the host PC physically wired to the camera (2× USB3 + 5 V). That vendor app exposes an **ASCII command server over TCP bound to `127.0.0.1`** (ports 9998/9999); the lab's existing `cSPAD` Python client speaks this protocol locally.

The need: a **remote web GUI** so lab members can operate the camera across all its functions from their own machines on the lab network — without sitting at the host PC and without learning the vendor app or writing Python each time. The intended outcome is a maintainable web application that wraps the vendor software, exposes every acquisition mode and calibration, guides safe operation of shared hardware, and feeds the lab's existing analysis pipeline unchanged.

### Why a bridge is required
The vendor command server binds to `localhost` only and is effectively single-connection. A browser cannot reach it directly. Therefore the system is two parts: a **bridge service on the host PC** that owns the single TCP connection and re-exposes it as a network API, and a **browser front-end** that lab members use.

---

## Decisions captured in the requirements interview

| Area | Decision |
|---|---|
| Topology | **Web app + host bridge** — browser front-end, Python bridge on host |
| Network reach | **Lab LAN only** (no public internet, minimal auth) |
| Concurrency | **No formal locking** ("free-for-all"), but bridge **serializes** commands (see below) |
| Build scope | **Wrap vendor software** (vendor app keeps owning the camera) |
| Modes (v1) | **Intensity, Gated time-resolved, FLIM, Raw 1-bit single-photon** — all four |
| Acquisition styles | **Single-shot, parameter sweeps, scheduled/overnight** (no free-running viewfinder) |
| Data flow | **Host saves full data; browser receives downsampled previews + metadata**; full download on demand |
| File formats | **Match existing analysis repo** (PNG folders → `meta_*.json` + `movie_arr_*.npy`) + **JSON sidecar** |
| Instrument scope | **SPAD only**, but with **trigger awareness** (surface/validate laser sync) |
| Calibration UX | **Guided + state-aware** (track status, prompt for physical setup, warn if uncalibrated) |
| Safety/health | **Alarms + auto-protect** (poll temps/voltages; alert and optionally abort/reduce bias) |
| Reliability | **Resilient bridge** (auto-reconnect, checkpoint sweeps, survive browser disconnect) |
| Visualization | Image+ROI, per-ROI decay curve, phasor+lifetime map, histogram/DCR |
| Reproducibility | Parameter presets, experiment log, sample/experiment naming, re-run from history |
| Identity | **Fully anonymous** (shared workspace, no auth, no per-user notifications) |
| Host | **Windows host; vendor app must be running** (bridge runs alongside; not responsible for auto-starting vendor app in v1) |
| Abort | **Stop at safe boundaries** (between steps/iterations; in-flight frame finishes) |
| Dev | **Build a simulator/mock** of the cSPAD TCP server for hardware-free development |

### Recommendations for the two "you advise" items
- **Stack → FastAPI (Python) + React + TypeScript SPA.** The required visuals (interactive ROI, phasor scatter, false-color lifetime map, live decay/progress over WebSocket) are awkward in Streamlit/Dash. Keep all acquisition logic in pure Python (reusing `cSPAD`) so physicists can extend it; keep the React layer thin and well-documented. Charts via Plotly/lightweight canvas; image rendering on `<canvas>`.
- **Serialization → serialize at the bridge and broadcast a "busy" state.** The bridge is the sole owner of the cSPAD socket. All control commands go through one async queue; while an acquisition runs, every client sees `busy {sample, mode, progress}`, and new control commands are rejected with a clear "instrument busy" message. Read-only health polling stays available. This prevents protocol corruption without imposing formal locking.

---

## System architecture

```
 Browser (React/TS SPA)  ──HTTP/WebSocket(LAN)──►  Bridge service (FastAPI, host PC)
   - mode panels                                     - single owner of cSPAD TCP socket
   - image canvas + ROI                              - command queue / serialization
   - plots (decay/phasor/hist)                       - acquisition runner (single-shot/sweep/scheduled)
   - health dashboard + alarms                       - health poller + auto-protect
   - experiment log / presets                        - data writer (PNG folders) + reducer
                                                      - experiment log / preset store (SQLite + files)
                                                            │ TCP 127.0.0.1:9999
                                                            ▼
                                                   Vendor software ──USB3──► SPAD512²
```

- **Bridge** = FastAPI app + a long-lived `cSPAD` connection wrapper. One asyncio task owns the socket; an async queue serializes commands; acquisitions run in a worker so the API/WebSocket stay responsive.
- **Front-end** = React + TypeScript SPA served by the bridge (or a static host). WebSocket channel for live progress, health, busy-state, and preview frames.
- **Persistence** = SQLite for experiment log/presets/schedule; acquired data on the host filesystem in the lab's existing folder layout.

---

## Functional requirements

### 1. Connection & system info
- Connect to the bridge; bridge connects to vendor server (port configurable, default 9999).
- Display system info (`D`): FPGA serials, SW/FW/HW versions, hardware flavour, sensor size (512 vs 1M), enabled features (intensity/gated/FLIM), valid bit depths and ROI widths derived from the device.
- Surface laser & frame clock frequencies (`R`) and validate against expected trigger source.

### 2. Acquisition modes (all v1)
Common controls per mode, mapped to existing `cSPAD` methods:
- **Intensity** (`get_intensity` / `I`): bit depth (1,4,6–12), integration time (auto unit: µs for 1/4-bit, ms for ≥6-bit — GUI handles unit switch), iterations, ROI width (4…512), read/exposure overlap, pileup correction, timeout-retry.
- **Gated time-resolved** (`get_gated_intensity` / `G`): bit depth, integration time, iterations, gate steps, gate step size (×~18 ps), arbitrary step arrays (`set_arbitrary_steps` / `Ga`), gate width, gate offset, gate direction, gate trigger source, overlap, stream, pileup. Include the **optimal-parameters helper** (`get_opt_gated_param` / `Gf`) to auto-fill steps/offset/min step for one full cycle.
- **FLIM** (`calib_FLIM` + `get_FLIM` / `F`): IRF calibration (mono/bi-exponential, expected τ, gate width short/med/long), integration time, gate subsampling, image vs raw output; phasor processing.
- **Raw 1-bit single-photon**: bit-depth-1 intensity path with binary unpacking (distinct decode), for high-speed/photon-statistics work.

### 3. Acquisition styles
- **Single-shot:** configure → Acquire → result.
- **Parameter sweeps:** auto-iterate one or more parameters (e.g. Vex, gate offset, integration time) over a range/list; collect a labeled series; **checkpoint each point** so a sweep survives client disconnect.
- **Scheduled / overnight:** queue jobs and/or time-trigger; run unattended; progress + completion/failure visible in-app and in the experiment log.
- **Stop = safe-boundary cancel** (between steps/iterations/sweep points); offer a separate "force stop" later if needed (out of v1 unless trivial).

### 4. Calibration (guided + state-aware)
- Track per-calibration status and staleness: **breakdown** (auto on connect, `calib_breakdown`), **hot-pixel/noise** (`calib_noise`, requires dark), **dead-pixel** (`calib_dead`, requires dark), **master/slave offset** (`calib_mst_slv_off`, requires uniform pulsed illumination), **FLIM IRF**.
- Guided prompts for physical setup ("cap the objective", "uniform pulsed source"); **warn before acquiring while uncalibrated**.
- Show **DCR-vs-percentage** curve before/after noise/dead calibration (as in the example script) for QA.

### 5. Detector safety & health (alarms + auto-protect)
- Poll temperatures (master/slave FPGA, PCB, chip) and voltages (Vq, Vex), cooling state, laser/frame freq on an interval (`R`, `V`, `S`).
- **Alarms** on over-temperature, cooling failure/disabled, missing/abnormal laser trigger, suspected overexposure.
- **Auto-protect:** configurable thresholds that can abort the acquisition and/or reduce bias to a safe value; require confirmation for high `Vex`.

### 6. Data handling & formats
- Set save path on host (`set_path` / `D,<path>`); organize as the lab convention: `data/intensity_images/acqXXXXX`, `data/gated_images/acqXXXXX` (vendor saves `IMGxxxxx.png` with embedded metadata: Author, Mode, Integration time, Laser frequency, gate params, triggers, SW version, etc.).
- After acquisition, optionally run the lab **reducer** to emit `meta_acqXXXXX.json` + `movie_arr_acqXXXXX.npy` (3D array `nframes × x × y`) — feeding `512^2_*.py` / `SEP_D.py` unchanged.
- Write a **JSON sidecar** per acquisition with the full parameter set, calibration state, temps, timestamps, sample/experiment tags (superset aligned with the reducer's meta).
- Browser receives **downsampled preview frames + metadata** over WebSocket; full arrays downloaded on demand.

### 7. Visualization (in-browser)
- 512×512 **image canvas**: colormaps, intensity scaling/auto-stretch, zoom/pan, rectangular + freehand **ROI**.
- **Per-ROI decay curve** (counts vs gate offset) from a gated stack.
- **FLIM phasor scatter** + false-color **lifetime map**.
- **Histogram** of pixel values and **sorted DCR curve** for calibration QA.

### 8. Reproducibility & workflow
- **Presets:** save/load named per-mode configurations.
- **Experiment log:** every acquisition recorded (parameters, result path, calibration state, temps, timestamp, sample/experiment, mode) — browsable/searchable.
- **Sample/experiment naming + notes** drive file organization and log.
- **Re-run from history:** one click to repeat a past acquisition (identical or tweaked).

---

## Non-functional requirements
- **Reliability:** bridge auto-reconnects to the vendor server; acquisitions and sweeps run server-side and survive browser tab closes; sweep checkpoints allow resume; guaranteed clean abort leaving hardware in a safe state.
- **Concurrency:** serialized command queue; broadcast busy/progress to all clients; reject conflicting control commands with clear messaging; health polling always allowed.
- **Security:** LAN-only bind; no auth in v1 (anonymous shared workspace); do not expose to public internet.
- **Maintainability:** acquisition logic in pure Python reusing `cSPAD`; documented API; thin React layer; README + setup docs for the host.
- **Performance:** previews kept small for responsive LAN updates; full data never forced through the browser.

---

## Testing / verification
- **Mock cSPAD server:** a Python TCP server implementing the vendor protocol (`D`,`V`,`R`,`AE`,`CALIB`,`S`,`I`,`G`,`PU`,`Ga`,`Gf`,`F`) and returning synthetic images/decays/phasor data, plus DONE/ERROR framing and breakdown-calibration handshake. Enables full hardware-free development and CI.
- **Bridge unit tests** against the mock: each command path, serialization/busy behavior, safe-boundary abort, reconnect, sweep checkpoint/resume, auto-protect thresholds.
- **End-to-end:** drive the SPA against the bridge+mock — run a single-shot, a sweep, a scheduled job, each calibration, trigger an alarm, verify preview/plots/log/presets/re-run, and confirm produced files match the reducer layout (`meta_*.json` + `movie_arr_*.npy`) so `512^2_*.py` reads them.
- **Hardware bring-up:** on the Windows host with the vendor app running, validate one acquisition per mode and the health/alarm path.

---

## Key references (existing code to reuse)
- `theoretical_info/piimaging_examples/cSPAD.py` — the TCP protocol client; the bridge wraps this.
- `theoretical_info/piimaging_examples/python_tcp_stream_{intensity,gated,flim}.py` — streaming/decoding patterns.
- `theoretical_info/piimaging_examples/python_image_metadata.py` — PNG metadata keys for the sidecar.
- `theoretical_info/Piimaging-512-2-analysis-main/` — `Reduce_size_512SPAD.py` (folder→`meta_*.json`+`movie_arr_*.npy`), `512^2_*.py`, `SEP_D.py` (downstream pipeline to remain compatible).

## Out of scope (v1)
- Controlling lasers/stages/filter wheels (trigger awareness only).
- Public-internet access, authentication, per-user notifications.
- Replacing the vendor software / direct low-level camera access.
- Free-running viewfinder preview; force-stop (deferred).
- Auto-starting/recovering the vendor app after host reboot.

## Proposed build phases
1. Bridge core: `cSPAD` wrapper, command queue, FastAPI skeleton, mock server.
2. Modes: intensity → gated → FLIM → 1-bit, with single-shot acquire + previews.
3. Calibration (guided) + health/alarms/auto-protect.
4. Sweeps + scheduling + resilient/checkpointed runner.
5. Front-end visualization (image/ROI/decay/phasor/histogram) + experiment log/presets/re-run.
6. Data writer + reducer integration + sidecar; end-to-end verification on mock then hardware.
