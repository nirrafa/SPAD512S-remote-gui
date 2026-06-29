# Progress Log

> **Update this file at the end of every work session.** Each entry records what was done, what was decided, what blocked, and what comes next. This is the single source of truth for project status.

**References:** [Plan](plan.md) · [PRD](PRD.md) · [Constraints](constraints.md) · [Learnings](learnings.md)

---

## Status summary

| Phase | Description | Status | Tests passing |
|---|---|---|---|
| 0 | Project setup & tooling | ✅ Done | gate ✓ |
| 1 | Mock vendor server | ✅ Done | 19 / 19 |
| 2 | Bridge core | ✅ Done | test_01 14/14, test_12 reconnect 4/9 (rest of test_12 → Phase 9) |
| 3 | Intensity mode (vertical slice) | ✅ Done | test_02 26/26, test_13 4/5 (health-poll → Phase 8) |
| 4 | Gated time-resolved mode | ✅ Done | 12 / 12 |
| 5 | FLIM mode | ✅ Done | test_04 11/11 |
| 6 | Raw 1-bit single-photon | ✅ Done | test_05 5/5 |
| 7 | Calibration system | Not started | 0 / 13 |
| 8 | Safety, health & auto-protect | Not started | 0 / 17 |
| 9 | Sweeps, scheduling & resilience | Not started | 0 / 18 |
| 10 | Data handling & reducer | Not started | 0 / 18 |
| 11 | Front-end visualization | Not started | 0 / 12 |
| 12 | Experiment log & presets | Not started | 0 / 16 |
| 13 | Integration & hardware bring-up | Not started | 0 / 11 |
| **Total** | Phases 0–6 done | | **102 / 202 pre-dev tests passing** |

> Note: the 202 collected pre-dev tests exceed the plan's original 185 estimate; per-file counts (e.g. `test_02` = 26, not 11) differ from the plan's mapping table. The remaining failures are Phases 5–13 plus the two in-scope deferrals (`test_13` health-poll → Phase 8; `test_12` sweep/disconnect → Phase 9).

---

## Session log

### Template

Copy this block for each new entry. Most recent session goes on top.

```
### YYYY-MM-DD — Session title

**Phase(s):** #
**Duration:** ~Xh
**Who:** name

#### Done
- bullet points of completed work

#### Decisions made
- any choices made and why (also add to plan.md decisions log)

#### Bugs / issues encountered
- description → resolution (also add to learnings.md if non-trivial)

#### Blocked on
- anything that prevents further progress

#### Next session
- what to pick up next
```

---

<!-- Add new entries below this line, most recent first -->

### 2026-06-29 — Phase 6: Raw 1-bit single-photon mode

**Phase(s):** 6
**Duration:** ~1h
**Who:** Nir + Claude

#### Done
- Bridge: `POST /api/acquire/raw-1bit` (`Raw1BitRequest`) in `bridge/routes/acquire.py`.
  Reuses `AcquisitionRunner.run_intensity` with `bit_depth=1` and integration time
  in µs; tags the result with `decode_method:"binary_unpack"` and `bit_depth:1`.
- Front-end: `Raw1BitPage` + `Raw1BitPanel` (bit depth locked to 1, integration
  time in µs), `acquireRaw1Bit` client + `Raw1BitParams` type, and a "Raw 1-bit"
  tab in `App.tsx`.
- `pre_dev_tests/test_05_acquisition_raw_1bit.py` → 5/5. No regressions
  (`tests/` 17/17, `test_02` 26/26). ruff + mypy clean; frontend build/lint/test green.

#### Decisions made
- No `bridge/services/raw_1bit.py` (plan had stubbed one). The existing 1-bit
  decode (`decoder.decode_intensity`) and intensity acquisition path already do
  the binary unpacking, so a separate service module would be dead indirection;
  the endpoint reuses `run_intensity`.

#### Bugs / issues encountered
- None.

#### Blocked on
- Nothing.

#### Next session
- Phase 7 (calibration) — being developed in parallel.

### 2026-06-28 — Phase 5: FLIM mode

**Phase(s):** 5
**Duration:** ~2h
**Who:** Nir + Claude

#### Done
- **Mock:** `synthetic_data.flim_decay_csv` emits the vendor raw-FLIM CSV (one int/line, frames concatenated, `DONE`-terminated); `_handle_flim` streams it for `F,i` (gate-frame count reduced by `gate_subsampling`), keeps phasor for the harness path.
- **Bridge:** `commands.flim_calibrate`/`flim_acquire`; decoder `decode_flim_csv` + `flim_phasor` (first-harmonic g/s) + `phasor_to_lifetime`; `services/flim.py` (decode → phasor → lifetime map, downsampled g/s for transport); `routes/calibration.py` (`POST /api/calibrate/flim-irf`); `POST /api/acquire/flim` in `acquire.py` (busy-guard, warning-if-uncalibrated); `flim_irf_calibrated` app state.
- **Front-end:** FLIM tab + `FLIMPanel` (calibration + acquire), `FLIMPage`, `PhasorScatter` (basic SVG over the semicircle), lifetime map via `ImageCanvas`.
- **Tests:** `test_04` → 11/11. Full regression green (default 17, phases 1–4 71). ruff + mypy clean; frontend build/lint/test green. Suite writes no `./data`.
- Manual e2e (mock+bridge): uncalibrated acquire → `done` + warning + 8 gate steps + 4096 phasor points + 256×256 lifetime map; after calibrate → no warning; `gate_subsampling=2` → 4 gate steps.

#### Decisions made
- Bridge requests raw FLIM and computes phasor/lifetime host-side; mock streams the real CSV shape but bounded (small gate-frame count); minimal `flim_irf_calibrated` flag (Phase 7 generalizes). See plan.md decisions log.

#### Bugs / issues encountered
- None blocking. Logged B-16 (mock bounded FLIM payload; full-res raw line validated on hardware in Phase 13).

#### Blocked on
- Nothing.

#### Next session
- Phase 6 (raw 1-bit) or Phase 7 (calibration system). Real-hardware FLIM validation when convenient (camera on hand).

### 2026-06-28 — Phase 4: gated time-resolved mode

**Phase(s):** 4
**Duration:** ~1.5h
**Who:** Nir + Claude

#### Done
- **Backend:** `commands.gated/arbitrary_steps/optimal_gated_params`; `decoder.parse_optimal_gated`; `AcquisitionRunner.run_gated/_gated_op` (synchronous — no busy/timeout spec for gated — with per-gate-step preview broadcasts carrying index/count); `POST /api/acquire/gated` (+ direction/trigger/bit-depth validation) and `GET /api/acquire/gated/optimal-params`. Gated reuses the intensity decode (always 512-wide). `ws_hub.broadcast_preview` extended with index/count.
- **Front-end:** `GatedPanel` (all params, Auto-fill optimal, comma-separated arbitrary steps), `GateStepSlider` scrubbing per-step previews collected from WS (reset on each `busy`), `GatedPage`, mode tabs (Intensity/Gated) in `App.tsx`.
- **Gate:** `test_03` 12/12. Default suite + Phases 1–3 gates green (74 spec tests total); ruff + mypy clean; `npm run build/lint/test` green. E2E curl: optimal-params `{56,50,18}`; 20-step acquire → `done` + `total_gate_steps/previews_sent = 20` + saved `gated_images/acqNNNNN/movie_arr.npy`; arbitrary `[0,5,10,20,50,100]` → 6 steps.

#### Decisions made
- Gated runs synchronously (awaits completion) — no `test_13`-style busy/timeout requirement for gated, so the request returns the full result with counts. Per-step previews are broadcast with `index`/`count` for the scrubber.

#### Bugs / issues encountered
- mypy: `TypedDict` is not assignable to `dict[str, Any]` (invariance) → typed `broadcast_preview` param as `Mapping[str, Any]`; returned `OptimalGated` from the route instead of `dict(...)`.

#### Blocked on
- Nothing.

#### Next session
- Phase 5: FLIM (IRF calibration + acquisition + phasor g/s). `test_04` (9). Adds the CSV-line FLIM text decoder deferred from Phase 1.

### 2026-06-28 — Phase 3: intensity vertical slice + first GUI

**Phase(s):** 3
**Duration:** ~3h
**Who:** Nir + Claude

#### Done
- **Backend:** `decoder.decode_intensity` (3 cSPAD paths) + `integration_time_unit`; `services/preview.py` (≤256² auto-stretched base64 uint8); `services/file_writer.py` (`acqNNNNN/movie_arr.npy`); **`core/acquisition.py` background runner** (busy guard, per-op `timeout_s`, result-grace, busy/preview broadcasts, `ProtocolClient.reset()` for resync on timeout). Rewrote `/api/acquire/intensity` to validate + delegate; flat `broadcast_busy`; dropped the WS initial-state send.
- Mock: tile one frame ×iterations (cheap) + paced chunked wire write (responsive loop, deterministic busy timing); cancel in-flight handler tasks on stop.
- **Front-end GUI (first usable UI):** api client/types, `useWebSocket`/`useAcquisition`, `IntensityPanel`, `ImageCanvas` (colormap + zoom/pan), `ProgressBar`, `StatusBanner`, `IntensityPage`, `utils/colormap.ts`. vitest for colormap/base64.
- **Gate:** `test_02` 11/11; `test_13` 4/5 (serialization, busy rejection, busy broadcast ×2). Default suite + Phase 1/2 gate green; ruff + mypy clean; `npm run build/lint/test` green. E2E curl: acquire → `done` + 256² preview + `(3,512,512)` uint16 `.npy` saved.

#### Decisions made
- Background runner + result-grace; mock tiling + write pacing; runner-owned busy broadcasts; base64 preview + client colormap; health-poll test deferred to Phase 8. (See plan.md decisions log.)

#### Bugs / issues encountered
- First WS frame was `state` not `busy` (instrument auto-broadcast on ACQUIRING) → runner now owns busy/idle broadcasts.
- 1000-iteration acquire blocked the mock loop (teardown timeout) → tile + paced chunked write.
- `ImageData(rgba, w, h)` rejected `Uint8ClampedArray<ArrayBufferLike>` under strict TS → construct by dims and `.data.set(rgba)`.

#### Blocked on
- Nothing.

#### Next session
- Phase 4: gated time-resolved mode (`POST /api/acquire/gated`, arbitrary steps, optimal-params helper, gate-step scrubber). `test_03` (12).

### 2026-06-27 — Phase 2: bridge core

**Phase(s):** 2
**Duration:** ~2h
**Who:** Nir + Claude

#### Done
- **Protocol layer** (`bridge/protocol/`): `client.py` async TCP client (banner + double-D breakdown handshake, `send_command`/`send_acquire`, asyncio-lock serialization, **passive idle-EOF disconnect detection**, auto-reconnect with backoff on a fixed port); `decoder.py` (`strip_done`, `parse_system_info`, `parse_readout`, `bytes_per_frame`); `commands.py` builders.
- **Core** (`bridge/core/`): `instrument.py` (idle/acquiring/calibrating/stopping + busy guard) and `ws_hub.py` (registry + broadcast_*; drops dead clients).
- **Routes**: `/api/health`, `/api/status`, `/api/system/info`, `/api/system/triggers`, `/api/acquire/stop`, `/api/acquire/intensity` (connection-guarded minimal acquire), `WS /ws`. Rewrote `main.py` with a lifespan that connects on startup; `create_app(settings)` for port override.
- Extended the mock: TCP server closes active connections on `stop()`; `MockVendorServer` gained `start()/stop()/port` (same-port rebind) so it serves both the in-process harness (test_14) and bridge integration.
- Wired `pre_dev_tests` `bridge_client` fixture (HTTP/WS wrapper) and the `mock_vendor_server` TCP lifecycle.
- **Gate green:** `test_01` 14/14, `test_12::TestAutoReconnect` 3/3. Default `tests/` suite expanded (bridge API + mock TCP regressions) → all pass. ruff + mypy(strict) clean. Added `pytest-timeout` (default 60s).

#### Decisions made
- Passive idle-EOF disconnect detection; same-port mock rebind; Phase-2 "queue" = lock + busy guard (formal queue deferred to Phase 3/8); fleshed out the `test_bridge_configurable_port` stub. (See plan.md decisions log.)

#### Bugs / issues encountered
- FastAPI on Py3.11 requires `typing_extensions.TypedDict` (not `typing.TypedDict`) for response models → fixed import.
- TestClient lifespan hung on teardown when a `/ws` connection was left open, and surfaced a `CancelledError` when the bridge was disconnected at shutdown. Fixed by closing tracked WS handles in the client wrapper and making `protocol.stop()` cancel+await all tasks without `wait_closed`. Recorded in learnings.md.
- Latent bug: intensity ROI width is arg index 7 (not 8) of the `I` command — corrected in the mock.

#### Blocked on
- Nothing.

#### Next session
- Phase 3: intensity vertical slice. Full intensity endpoint (param validation, µs/ms unit switch, decode all bit depths, downsampled preview over WS, file save) + the front-end intensity panel + image canvas. Targets `test_02` (11) and `test_13` concurrency/busy (the formal queue lands here).

### 2026-06-27 — Phase 1: mock vendor server

**Phase(s):** 1
**Duration:** ~1h
**Who:** Nir + Claude

#### Done
- Built the mock vendor server as a shared protocol core feeding two front-ends:
  - `mock_server/state.py` — `MockState` (temps, voltages, freqs, toggles, calibration flags) + test hooks (`set_temperature`, `set_voltage`, `set_laser_frequency`, `fail_after_n_commands`, `set_next_response_delay`).
  - `mock_server/synthetic_data.py` — numpy generators (intensity frame, gated stack, FLIM phasor) + wire encoders for all three intensity byte layouts (1-bit packed, ≤8-bit 1 byte/px, ≥9-bit/pileup 2 byte/px little-endian).
  - `mock_server/protocol.py` — pure `handle(cmd, state) -> CommandResult` dispatching D, V, R, AE, S, PU, CALIB, I, G, Ga, Gf, F + unknown→ERROR.
  - `mock_server/harness.py` — `MockVendorServer` in-process API (`send_command`, `last_image_data`, `last_phasor_data`) used by the spec tests.
  - `mock_server/server.py` — asyncio TCP server (banner, read loop, binary+DONE framing); `cli.py` + `__main__.py` for `python -m mock_server --port 9999`.
- Wired `pre_dev_tests/conftest.py` `mock_vendor_server` fixture → `MockVendorServer`.
- **`test_14` → 19/19 pass.** Added `tests/test_mock_tcp.py` (3 fast asyncio TCP regression tests).
- Verified the **real `cSPAD.py`** connects over TCP and runs `get_info()`/`get_temps()`/`get_freq()`/`get_intensity()` → valid `(512,512,1)` uint16 array.
- ruff + mypy(strict) clean on `mock_server`.

#### Decisions made
- Shared pure-protocol core (`protocol.handle`) behind both the in-process harness and the TCP server, so the spec tests and the real client exercise the same logic.
- `F,i` returns phasor data only for now; the CSV-line FLIM **text** format is deferred to Phase 5.

#### Bugs / issues encountered
- `DONE` framing glues onto the last field of text responses (e.g. `get_freq()` → `'100.0\nDONE'`). Recorded in learnings.md; the bridge's `R`/`V` decoder (Phase 2) must strip a trailing `DONE` before parsing.

#### Blocked on
- Nothing.

#### Next session
- Phase 2: bridge core. Async protocol client wrapping cSPAD logic (with DONE-stripping decoder), command queue, instrument state, WebSocket hub, REST skeleton. Targets `test_01` (14) + `test_12` reconnect tests.

### 2026-06-27 — Phase 0: project setup & tooling

**Phase(s):** 0
**Duration:** ~1h
**Who:** Nir + Claude

#### Done
- Initialized git repo; created public GitHub repo [nirrafa/SPAD512S-remote-gui](https://github.com/nirrafa/SPAD512S-remote-gui) and pushed initial commit (docs, pre-dev tests, reference code).
- Installed Homebrew + `gh` CLI on the host; authenticated as `nirrafa`.
- Created Python bridge package skeleton: `bridge/{__init__,main,config}.py`, `py.typed`. FastAPI app with `GET /api/health` and CORS.
- `pyproject.toml` with runtime deps (FastAPI, uvicorn, pydantic, pydantic-settings, numpy, websockets) and dev extras (pytest, pytest-asyncio, httpx, ruff, mypy). Configured pytest (asyncio auto), ruff, mypy (strict).
- `mock_server/` and `tests/` skeletons; bridge smoke test (`tests/test_health.py`).
- Scaffolded `frontend/` (Vite React-TS): added `strict: true` + `noUncheckedIndexedAccess`, dev proxy for `/api` + `/ws`, vitest + Testing Library, Prettier. Replaced demo App with bridge-health shell + smoke test.
- Created `README.md` and root `.gitignore`.

#### Decisions made
- Python 3.11 over system 3.9; Vite default template (React 19 / oxlint / vitest); pydantic-settings with `SPAD_` env prefix. (See plan.md decisions log.)

#### Bugs / issues encountered
- Homebrew install needs interactive sudo → user ran it manually; same for `gh auth login`. Non-blocking.
- ruff flagged import order in `tests/conftest.py` → auto-fixed.

#### Blocked on
- Nothing.

#### Next session
- Phase 1: mock vendor server. Study `theoretical_info/piimaging_examples/cSPAD.py` + streaming examples, then implement the asyncio TCP server and pass `test_14_mock_vendor_server.py` (19 tests).
