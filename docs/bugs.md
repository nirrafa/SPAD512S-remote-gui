# Known Bugs & Deferred Fixes

> **Living document.** Tracks confirmed bugs and deferred cleanups, primarily
> from code reviews (`/code-review`). Each entry has a stable ID so commits and
> tests can reference it. When a bug is fixed, move it to **Fixed** with the
> commit and the regression test that locks it down.

**References:** [Plan](plan.md) · [Learnings](learnings.md) · [Constraints](constraints.md)

Severity: **S1** breaks correctness for a supported path · **S2** correctness
gap on an edge/unsupported path or a hang under fault injection · **S3** cleanup
(efficiency / duplication / maintainability) with no functional impact.

---

## Open

### B-04 — Mock TCP read loop assumes one `read()` == exactly one command · S2

**Where:** [`mock_server/server.py`](../mock_server/server.py) `_handle_client` read loop.
**Mechanism:** The loop treats each `reader.read(8192)` as a complete command.
There is no length/newline framing, so two pipelined commands coalesced into one
TCP segment (`b"PU,0I,8,..."`) mis-parse, and a command split across two segments
dispatches as two malformed `ERROR` replies.
**Why it hasn't bitten yet:** On loopback, small single commands arrive whole,
and both real consumers (`cSPAD.py`, the bridge `ProtocolClient`) send one command
and await its response before sending the next — so coalescing doesn't occur in
practice.
**Trigger to confirm:** A client that pipelines commands, or a command large
enough to fragment (none currently exist; arbitrary-step `Ga` arrays are the most
likely future candidate).
**Suggested fix:** Accumulate into a buffer and frame commands explicitly (the
vendor protocol is request/response, so "one outstanding command" is a safe
contract to document and assert), or delimit on a terminator.

### B-05 — `gated_stack` regenerates the full frame pattern per gate step · S3

**Where:** [`mock_server/synthetic_data.py`](../mock_server/synthetic_data.py) `gated_stack`.
**Mechanism:** Each gate step calls `intensity_frame`, which rebuilds `np.mgrid`,
re-runs the sin/cos gradient, and draws fresh Poisson noise, then merely scales the
result by a scalar `decay`. The expensive base pattern is recomputed `n_frames`
times.
**Cost:** A gated/sweep acquisition with hundreds of frames does hundreds of full
512×W trig passes; needlessly slow in the test suite and bridge integration runs.
**Suggested fix:** Compute the base gradient once, then apply per-frame Poisson +
decay (or vectorize over the frame axis). Fold into the Phase 4 gated work where
this path is actually exercised.

### B-06 — Intensity and gated duplicate the encode + `CommandResult` construction · S3

**Where:** [`mock_server/protocol.py`](../mock_server/protocol.py) `_handle_intensity` and `_handle_gated`.
**Mechanism:** Both build `encode_intensity_frames(...)` and a wire/image
`CommandResult` with near-identical structure.
**Cost:** Raw-1bit (Phase 6) and FLIM (Phase 5) acquisition paths will copy it a
third and fourth time; a fix to encoding/pileup handling must be applied in every
copy.
**Suggested fix:** Extract an `_acquisition_result(text, frames, bit_depth, state, image)`
helper. Best done when the raw-1bit/FLIM handlers land.

### B-07 — `_coerce_int(args[N], d) if len(args) > N else d` duplicated ~6× · S3

**Where:** [`mock_server/protocol.py`](../mock_server/protocol.py) `_handle_intensity`, `_handle_gated`, `_handle_optimal_params`.
**Mechanism:** The bounds-check-plus-coerce idiom is hand-written with literal
indices in six places.
**Cost:** This is the exact fragile pattern that produced **B-01** (an off-by-one
index). Every new hand-indexed arg is a fresh opportunity for the same bug.
**Suggested fix:** Extract `arg_int(args, n, default)` collapsing the length check
and coercion into one call; convert the existing sites.

### B-21 — `/api/acquire/stop` is cosmetic; no safe-boundary abort · S1/S2

**Where:** [`bridge/routes/acquire.py`](../bridge/routes/acquire.py) `stop`, [`bridge/core/acquisition.py`](../bridge/core/acquisition.py).
**Mechanism:** `stop` sets `stop_requested` then forces `IDLE`, but the running
background acquisition task is never cancelled and the runner never reads
`stop_requested` (grep: unused in the runner). So a stop flips the busy flag while
the task still streams → a second acquire can start and issue a second command onto
the socket → protocol desync. Violates constraints.md "stop must respect safe
boundaries; in-flight frames finish".
**Deferred:** entangled with Phase 8 auto-protect / Phase 9 safe-boundary stop — fix
as part of that work (runner consults `stop_requested` between iterations/gate steps;
`stop` observes the task rather than blindly setting IDLE).

### B-22 — `flim_irf_calibrated` global flag never goes stale · S2

**Where:** [`bridge/main.py`](../bridge/main.py), [`bridge/routes/calibration.py`](../bridge/routes/calibration.py), [`bridge/routes/acquire.py`](../bridge/routes/acquire.py).
**Mechanism:** Once any FLIM IRF calibration runs, every later FLIM acquire is
treated as calibrated forever — the flag survives Vex changes and reconnects, so the
"IRF not calibrated" safety warning is wrongly suppressed. The `CalibrationStore`
already models staleness for the other kinds; FLIM IRF is the odd one out.
**Suggested fix:** fold FLIM IRF into `CalibrationStore` with a stale-on-Vex-change /
clear-on-reconnect rule (aligns with the Phase 13 staleness work).

### B-23 — raw-1bit validates a `roi_width` the 1-bit path ignores · S2 (minor)

**Where:** [`bridge/routes/acquire.py`](../bridge/routes/acquire.py) raw-1bit, `decoder.decode_intensity` 1-bit path.
**Mechanism:** raw-1bit validates `roi_width` against the valid list, but the 1-bit
decode always uses `rows*rows//8` → full 512×512. A user picking `roi_width=256`
silently gets a full frame. **Suggested fix:** reject non-512 width for 1-bit, or drop
`roi_width` from the raw-1bit request model.

### B-24 — intensity vs gated disagree on integration-time precedence · S3

**Where:** [`bridge/routes/acquire.py`](../bridge/routes/acquire.py) `IntensityRequest.resolved_integration_time` vs `GatedRequest.resolved_integration_time`.
**Mechanism:** intensity prefers `integration_time` over `integration_time_ms`; gated
prefers the opposite. A caller sending both gets different behavior per endpoint.
**Suggested fix:** one shared precedence helper.

### B-25 — `_read_binary` premature-DONE on exact-length payloads ending in `DONE` bytes · S2 (edge)

**Where:** [`bridge/protocol/client.py`](../bridge/protocol/client.py) `_read_binary`.
**Mechanism:** termination fires on `buffer.endswith(b"DONE") and len >= target`. If
real 2-byte pixel data ends in the ASCII bytes `DONE` exactly at the
`expected_bytes+4` boundary before the true trailing sentinel arrives, the read stops
4 bytes early → spurious length-mismatch `ProtocolError`. Data-dependent, low
probability. **Suggested fix:** when `expected_bytes` is known, read exactly `target`
and verify the last 4 are `DONE`; sentinel-scan only for the unknown-length/error case.

### B-26 — dead `'busy'` status branch in the front-end · S3 (nitpick)

**Where:** [`frontend/src/hooks/useAcquisition.ts`](../frontend/src/hooks/useAcquisition.ts), `AcquireResult` in `api/types.ts`.
**Mechanism:** checks `result.status === 'busy'`, but the bridge returns busy as
`{"status":"error","message":"instrument busy"}`; the `'busy'` variant is never
emitted. Harmless (falls through to the error branch). **Suggested fix:** drop
`'busy'` from the union + check, or make the bridge emit it.

> **Test coverage gap (from both reviews):** there are no bridge-level tests for
> gated, FLIM, raw-1bit, calibration, `/api/acquire/stop`, or the busy guard — only
> plain 8-bit intensity + status + reconnect. B-18 in particular would be caught by a
> single "calibration rejected while acquiring" test. Address alongside Phase 8/9.

---

## Fixed

| ID | Severity | Summary | Fixed in | Regression test |
|---|---|---|---|---|
| B-01 | S1 | `_handle_intensity` read ROI width from arg index 8; the `I` command places width at index 7, so any `im_width≠512` was silently ignored → `cSPAD` reshape `ValueError`. | Phase 1 review fixes | `tests/test_mock_tcp.py::test_intensity_honors_non_512_roi_width` (+ cSPAD `im_width=256` smoke) |
| B-02 | S2 | Fault injected during a binary acquisition returned text with no terminator → `cSPAD`/bridge read-until-`DONE` loops hung. Mock now terminates errors with `DONE` while keeping `ERROR` in the text (matches `bridge/protocol/decoder.py`). | Phase 1 review fixes | `tests/test_mock_tcp.py::test_fault_injected_acquisition_terminates_with_done` |
| B-03 | S2 | `GATED_BIT_DEPTHS` was unused and gated validated against `INT_BIT_DEPTHS`, wrongly accepting 1/4-bit (vendor: gated is 6–12 only). Added `_resolve_gated_bit_depth`. | Phase 1 review fixes | `tests/test_mock_tcp.py::test_gated_rejects_sub_six_bit_depth` |
| B-08 | S2 | Bridge `_read_binary(expected_bytes)` used `readexactly` and couldn't detect a short/errored frame (hung to timeout → false disconnect). Now reads until `DONE`, raises `ProtocolError` on a leading `ERROR`, and validates payload length. | Phase 2 review fixes | `tests/test_bridge_api.py::test_invalid_roi_width_rejected_without_desync` (length-mismatch path) |
| B-09 | S1 | `WebSocketHub.broadcast` iterated the live client set across an `await`; a concurrent connect/disconnect raised `RuntimeError: Set changed size during iteration`, aborting the broadcast. Now iterates a `list(...)` snapshot. | Phase 2 review fixes | `tests/test_ws_hub.py::test_broadcast_survives_concurrent_connect` |
| B-10 | S1 | `/api/acquire/intensity` did not validate `roi_width`/`bit_depth`; an out-of-range width made bridge `expected_bytes` disagree with the vendor's clamped width → wrong-sized read + leftover bytes corrupting the next command. Now validated against `ROI_WIDTHS_*`/`INT_BIT_DEPTHS` before sending. | Phase 2 review fixes | `tests/test_bridge_api.py::{test_invalid_roi_width_rejected_without_desync,test_invalid_bit_depth_rejected}` |
| B-11 | S2 | CORS used `allow_origins=["*"]` with `allow_credentials=True` — an invalid combination browsers reject for credentialed requests. Set `allow_credentials=False` (unauthenticated LAN tool). | Phase 2 review fixes | n/a (config) |
| B-12 | S3 | On passive disconnect, `_teardown` cancelled the running idle task then `await`ed `wait_closed()`, so the `CancelledError` skipped the `_reader`/`_writer = None` resets. Refs now cleared before the cancellable await. | Phase 2 review fixes | covered by `TestAutoReconnect` |
| B-13 | S2 | A vendor `ERROR` reply to a text command was returned as a normal string → downstream parser raised `ValueError` (HTTP 500). `send_command` now raises `ProtocolError`; `/api/system/triggers` returns 502. | Phase 2 review fixes | covered by `ProtocolError` path |
| B-14 | S3 | Default-suite `client` fixture built the app on vendor port 9999 with no mock, so tests could connect to a stray dev mock. Now uses an unused ephemeral port. | Phase 2 review fixes | n/a (isolation) |
| B-15 | S2 | Bridge test fixtures left `data_root` at its default `"data"`, so every acquisition test (and manual run) wrote a real multi-frame `.npy` into the shared `./data` tree and never cleaned up — 320 folders / 3.3 GB accumulated. Fixtures now set `data_root=str(tmp_path)` (per-test temp dir). | this session | `tests/test_bridge_api.py`, `pre_dev_tests/conftest.py`, `tests/conftest.py` fixtures + verified `./data` is not recreated by the suite |
| B-17 | S1 | FLIM command builders used the wrong wire format — `F,c,<mode>,…` / `F,i,<int>,…` (comma after the letter) and `flim_calibrate` omitted `intTime`. `cSPAD.py` (and learnings.md) use **no comma** after `c`/`i` and include `intTime`: `F,c<mode>,<intTime>,<expTau>,<gateWidth>` / `F,i<intTime>,<sub>,<raw>`. Mock + bridge agreed on the wrong format so tests passed but real hardware would mis-parse. Aligned to `cSPAD.py`; mock parser updated. **Note:** the two vendor references disagree (`python_tcp_stream_flim.py` uses the comma form) — must be validated on the real camera (Phase 13). | this session | `test_04`/`test_07`/`test_14` green post-change |
| B-18 | S1 | Calibration endpoints (`/api/calibrate/*`, incl. `flim-irf`) set `CALIBRATING` with no `is_busy` guard, so a calibration launched during an acquisition overwrote instrument state, contended for the single TCP socket, and its `finally: set(IDLE)` dropped the busy flag mid-acquisition. Added an atomic `is_busy` check to every calibration entry point. | this session | (add regression test — see coverage gaps) |
| B-19 | S2 | `/api/acquire/flim` and `/api/calibration/dcr-curve` only caught `NotConnectedError`/`ProtocolError`; a short/garbled payload raising `ValueError` from the decoder escaped as HTTP 500. Both now catch `ValueError` and return `{"status":"error",…}`. | this session | (add regression test) |
| B-20 | S1 | Front-end WebSocket never reconnected (`onclose` only flagged disconnected) → the GUI silently froze after any bridge restart/LAN blip; `onmessage` did an unguarded `JSON.parse`; `postJson`/acquire fetches ignored non-OK responses. Added exponential-backoff reconnect, a `JSON.parse` try/catch, and `res.ok` checks (acquire calls now route through `postJson`). | this session | frontend build/lint/test green |

---

## By design / not a bug

- **Gated mode is always 512-wide.** The vendor `G` command string carries no
  `im_width` field (see `cSPAD.get_gated_intensity`), so the mock cannot vary
  gated frame width and emits 512. A caller passing `im_width≠512` to gated is a
  caller error; the bridge must constrain gated ROI width to 512 (or full sensor
  width) in Phase 4.

- **B-16 — Mock FLIM payload is bounded (small gate-frame count) · S3 / Phase 13.**
  The vendor raw-FLIM format is CSV — `512×512×frames` text lines, first value per
  line = intensity (`python_tcp_stream_flim.py`). Full resolution × many gate frames
  is tens of MB of text, too heavy for the suite, so `mock_server/synthetic_data.flim_decay_csv`
  emits full 512×512 but a *small* gate-frame count (8, reduced by `gate_subsampling`).
  The bridge decoder (`decode_flim_csv`) derives `n_gates` from the value count, so it
  works for both the mock and real hardware. Two things to validate on the real camera
  (Phase 13): the full gate-frame count, and that each raw line's **first** field is the
  intensity (the bridge currently fast-parses one value per line via `np.fromstring`; real
  lines may carry extra comma-separated fields).
