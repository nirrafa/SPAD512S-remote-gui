# Constraints

> **Keep this file up to date.** Every time a new constraint is discovered or decided — hardware, protocol, regulatory, or architectural — add it here.

## Hardware

- Camera is **Pi Imaging SPAD512²** (512×512 sensor), connected via 2× USB3 + 5V to a dedicated Windows host PC.
- Only one TCP connection to the vendor command server at a time.
- Vendor command server binds to `127.0.0.1` only (ports 9998/9999) — no remote access without a bridge.

## Network & Security

- LAN-only deployment; no public internet exposure.
- No authentication in v1 — anonymous shared workspace. Because of this, CORS is `allow_origins=["*"]` with `allow_credentials=False`, and any host-file endpoint (`/api/data/*`) must resolve+constrain every path under `data_root` (traversal rejected).
- Bridge must run on the same Windows host as the vendor software.
- **Deployment:** the bridge serves the built SPA at `http://<host>:8080` (same origin as the API — no Vite dev server in production). Run `npm run build` once; the launcher (`launchers/start-spad.sh`) does this and starts mock + bridge.

## Protocol

- Vendor protocol is ASCII over TCP, single-connection, request–response with `DONE`/`ERROR` framing.
- All camera commands must be serialized through one async queue in the bridge; concurrent commands corrupt the protocol. (Implemented as the protocol-client `asyncio.Lock` + the instrument busy guard.)
- Health polling (`R`, `V`) is read-only and may run when idle, but must **not** interleave with an in-flight acquisition; during acquisitions the monitor serves cached readings. The acquisition runner force-polls at batch boundaries (socket transiently free).
- **`STOPPING` is a busy state.** The in-flight batch keeps streaming until the runner's next safe boundary, so no new command may start during an abort window (`is_busy` includes `STOPPING`).

## Data & Compatibility

- Acquired data must match the existing analysis pipeline layout: `meta_acqXXXXX.json` + `movie_arr_acqXXXXX.npy` (3D array: `nframes × x × y`).
- Per-acquisition output is `<data_root>/<mode>_images/acqXXXXX/IMGxxxxx.png` with the exact vendor metadata keys as PNG text chunks (unit suffixes are load-bearing — downstream scripts parse them with `removesuffix`). A JSON sidecar carries params + calibration snapshot + temperatures + timestamps.
- Downstream scripts (`512^2_*.py`, `SEP_D.py`) must work unchanged on bridge-produced data (verified by `tests/test_data_compat.py`).
- The original reducer's hardcoded 512×256 crop is experiment-specific; the port defaults to **full frame** and takes an optional crop.

## Operational / Safety

- Vendor app must be running before the bridge starts; bridge does not auto-start the vendor app (v1).
- Stop/abort must respect safe boundaries (between steps/iterations/sweep points); in-flight frames must finish. **Currently batched (safe-boundary) only for intensity** — gated/FLIM run a single vendor command, so a stop/over-temp there takes effect only after the command completes (B-32, Phase 13 item).
- Auto-protect thresholds (temperature, voltage) may abort acquisitions — this is by design. Over-temp aborts at the next boundary with `abort_reason`; over-Vex commands the safe bias (`V,<vex_max>`) and raises `vex_reduced`.
- **Vex hard ceiling: 50 V**, refused even with explicit confirmation. This is a placeholder — the real per-chip breakdown-derived bound must replace it during hardware bring-up.

## Browser / Front-end

- Full data arrays stay on the host; browser receives downsampled previews only (base64 uint8, ≤256², server auto-stretched; colormap applied client-side).
- Full data download is on-demand, not automatic.
- The WebSocket is the live channel; the client reconnects with backoff and must tolerate malformed frames.
- **Live view (`/api/live/frame`)** is a spartan single-frame-per-request focus/alignment aid for hosts without the vendor GUI (e.g. macOS) — not a scientific acquisition. It writes nothing to disk, adds no experiment-log entry, and shares the same busy guard as every other acquisition. There is no vendor "streaming" command; the frontend drives the cadence itself (single click, or a recursive-`setTimeout` poll loop at 300 ms while a "live" toggle is on) so the single TCP socket is held only for each capture's duration, never continuously, and the loop always stops on tab-switch/unmount.

## Mock vs. real hardware — must be validated on the camera (Phase 13)

These hold against the mock but are **unconfirmed on the real vendor**; validate in order of likely first failure (see `docs/bugs.md` B-16/B-17/B-34/B-35):

1. `DONE` framing on **text** responses (`R`/`V`/`D`): if the real vendor omits it, `_read_text` times out on every text command → false-disconnect loop. Five-minute test — do it first.
2. Calibration durations vs the uniform 10s read timeout (noise/dead-pixel/breakdown likely exceed it).
3. Breakdown handshake banner phrases, ~15s duration, and the double-`D`-on-connect pattern.
4. The mock appends `cooling,saturated` to `R` (8 fields); the real vendor returns 6, so the cooling-failure and suspected-overexposure alarms are dead until a real readout is found. (This also breaks `cSPAD.get_freq()` `split(',')[4:]` against the mock — B-34.)
5. FLIM command format: the two vendor references disagree (comma vs no-comma after `c`/`i`); code follows `cSPAD.py` — test both. FLIM raw-CSV full gate-frame count + first-field-per-line assumption (B-16).
6. Vex bounds vs the real breakdown voltage (replace the 50 V placeholder).
7. A Windows launch path is needed on the vendor host (the current launcher is `.command`/`.sh`).
8. **Dark-correction physics** (Phase 15): mock dark frames are statistically identical to mock signal frames, so only the mechanics are proven. On the real camera: measure a dark reference (cap on), verify the subtracted residual is near-zero on a dark scene, then verify a real signal survives correction with the DCR pattern removed — for both gated and intensity modes, at the lab's divided trigger rate.
