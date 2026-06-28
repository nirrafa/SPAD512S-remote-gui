# Learnings

> **Living document.** Record anything worth knowing for future work on this project, on the SPAD system, or on similar lab instrument control software. Each entry should be self-contained — a future reader (or a different lab project) should understand it without context from this codebase.

**References:** [Progress](progress.md) · [Constraints](constraints.md)

---

## Table of contents

- [Vendor protocol (cSPAD / Pi Imaging)](#vendor-protocol-cspad--pi-imaging)
- [Binary data decoding](#binary-data-decoding)
- [Hardware behavior](#hardware-behavior)
- [Architecture & design](#architecture--design)
- [Bugs & fixes](#bugs--fixes)
- [Python / FastAPI](#python--fastapi)
- [React / TypeScript](#react--typescript)
- [Data pipeline compatibility](#data-pipeline-compatibility)
- [Lab operations](#lab-operations)

---

## Vendor protocol (cSPAD / Pi Imaging)

### Connection handshake includes automatic breakdown calibration

When a TCP client first connects, the vendor server sends a welcome banner and may immediately begin a breakdown calibration. The client must watch for `"The breakdown calibration process will start soon."` or `"The breakdown calibration process has started."` in the initial response, then loop reading until it sees `"The breakdown is around"`. Only after this completes can the client send further commands. Sending commands during breakdown calibration will cause protocol corruption.

**Source:** `cSPAD.py` `__init__`, lines 50–72.

### The `D` command is sent twice on connect

The original `cSPAD.py` sends `D` once to get initial info (which may trigger breakdown calibration), then sends `D` again after calibration completes to get the actual system info. The bridge must replicate this two-step pattern.

### The `R` command returns both temperatures and frequencies

A single `R` command returns a comma-separated string: `T_MSTR,T_SLV,T_PCB,T_CHIP,laser_freq,frame_freq`. The first four fields are temperatures, the rest are frequencies. `cSPAD.py` has separate methods (`get_temps`, `get_freq`) that both send `R` — this is wasteful. The bridge should send `R` once and parse both.

### `DONE` framing glues onto the last field of text responses — strip it before parsing

The PRD spec (`test_14`) requires *every* command response to contain a `DONE` sentinel, including text commands like `R`/`V`/`D`. The mock appends `\nDONE` to text responses. `cSPAD.py`'s `get_temps()` survives this only by luck — it slices `split(',')[0:4]` and discards the tail — but `get_freq()` returns `['40000000.0', '100.0\nDONE']`, i.e. the trailing `DONE` is glued to the last frequency. **The bridge's `R`/`V` decoders must strip a trailing `DONE` line before splitting on commas**, otherwise the last numeric field (frame frequency, or `Vex`) will fail to parse. Discovered during Phase 1 mock bring-up.

It is unconfirmed whether the *real* vendor appends `DONE` to text responses; the mock follows the spec, and the bridge decoder is written defensively to strip it if present. Verify against real hardware in Phase 13.

### Calibration commands use numeric codes

| Code | Calibration type | Requirement |
|---|---|---|
| `CALIB,0` | Noise (hot pixel) | Sensor must be in the dark |
| `CALIB,1` | Dead pixel | Sensor must be in the dark |
| `CALIB,2` | Master/slave offset | Uniform pulsed illumination |
| `CALIB,3` | Breakdown | None (auto on connect) |

### FLIM command format quirk

The FLIM calibration command is `F,c<mode>,<intTime>,<expTau>,<gateWidth>` — note there is no comma between `c` and `<mode>`. Similarly, FLIM acquisition is `F,i<intTime>,<subsample>,<rawFlag>,1` with no comma between `i` and `<intTime>`. This is different from all other commands and easy to get wrong.

**Source:** `cSPAD.py` `calib_FLIM` line 694, `get_FLIM` line 722.

### Gate width mapping for FLIM

The `gateWidth` parameter in FLIM calibration is an integer, not a string: `0` = short, `1` = medium, `2` = long. The bridge API should accept human-readable strings and convert internally.

### Pileup correction is set separately

Pileup correction is toggled via a separate `PU,<0|1>` command sent *before* the actual acquisition command (`I` or `G`). The bridge must always send `PU` before any intensity or gated acquisition to ensure the state matches what the user requested.

### Socket timeout varies by calibration type

- Default: 30 seconds (`__init__`)
- Noise calibration: 1 second recv timeout in a loop, waiting for `"Noise calibration complete."`
- Dead pixel calibration: 15 seconds
- Breakdown calibration: fixed `time.sleep(15)` then recv

The bridge should handle these differently and not apply a uniform timeout.

---

## Binary data decoding

### Three distinct decode paths for intensity data

| Condition | Bytes per pixel | Decode method |
|---|---|---|
| `bit_depth == 1` | Packed bits (512×64 bytes per frame) | `np.unpackbits` → reshape (512, 512) → `np.rot90` |
| `bit_depth ≤ 8` and no pileup | 1 | Direct reshape to (rows, im_width) |
| `bit_depth ≥ 9` or pileup | 2 | Interleaved even/odd bytes: `(odd * 256) + even` |

Getting the decode path wrong produces garbage images or crashes. The mock server must produce data in exactly these formats.

### Binary data is terminated by `DONE` or `ERROR` as raw ASCII bytes

The client reads in a loop until the last 4 bytes of the accumulated buffer equal `bytearray("DONE", 'utf8')`. The `DONE` marker is then stripped before decoding. This is not a newline-terminated protocol — the `DONE` is appended directly after the binary pixel data with no separator.

### Gated data is `iterations × gate_steps` frames concatenated

The output array shape is `(rows, im_width, iterations * gate_steps)`. Frames are ordered: all gate steps for iteration 0, then all gate steps for iteration 1, etc. The downstream pipeline expects this ordering.

### FLIM data is text, not binary

Unlike intensity and gated modes, FLIM data comes as CSV text lines (one pixel per line), terminated by a `DONE` line. Each line contains comma-separated values, and the first value per line is used to reconstruct the 512×512 frames.

---

## Hardware behavior

### Integration time units depend on bit depth

- 1-bit and 4-bit: integration time is in **microseconds**
- 6-bit and above: integration time is in **milliseconds**

The GUI must display the correct unit and the bridge must not convert — the vendor server already expects the correct unit for the bit depth.

### Valid bit depths differ between intensity and gated modes

- Intensity: `[1, 4, 6, 7, 8, 9, 10, 11, 12]`
- Gated: `[6, 7, 8, 9, 10, 11, 12]` (no 1-bit or 4-bit)

The `cSPAD.py` class uses `self.intBitDepths` for both, but the gated streaming example only lists 6–12. Validate per mode.

### ROI width (im_width) affects data size

Valid widths depend on the sensor: 512-type → `[4, 8, 16, 32, 64, 128, 256, 512]`, 1M-type → `[8, 16, ..., 1024]`. The total pixel data per frame is `rows × im_width × bytes_per_pixel`. Getting this wrong means the decode reads past the buffer or leaves data behind.

### Breakdown voltage is hardware-specific

The breakdown calibration determines the actual breakdown voltage of the SPAD array. This value varies per chip and affects the valid range for Vex (excess bias). The bridge should store the breakdown value and use it to validate Vex settings.

---

## Architecture & design

### Single TCP connection is a hard constraint

The vendor server accepts only one TCP connection at a time. If the bridge loses its connection and a second process connects, the bridge cannot reconnect until that process disconnects. The bridge must be the sole owner of this connection — never expose the raw TCP port to other tools.

### Command serialization prevents protocol corruption

The vendor protocol has no request IDs or multiplexing. If two commands are sent before the first response arrives, the responses get interleaved and both are corrupted. All commands must go through a single queue with one consumer.

### Health polling must not interleave with acquisitions

The `R`, `V`, `S` commands are read-only, but they still go through the same TCP socket. During an acquisition, the socket is busy streaming binary data. Health polling must wait until the acquisition finishes or use cached values from the last poll.

### Long acquisitions need a background task + result-grace, not a blocking request

A single acquisition endpoint must serve two conflicting needs: return the full result (preview, saved path) for a quick acquire, *and* let a second request be rejected as "busy" while a long one is still running. With a blocking HTTP client these can't both hold if the endpoint awaits completion (the long call blocks the client, so a sequential second call never overlaps). Resolution: run the acquisition as a **background task**, set the busy state synchronously, then await the task for a short *result grace*; if it finishes, return its result, otherwise return `running` and let it complete unattended (pushing the final preview over WebSocket). A per-op timeout uses `max(grace, timeout_s)` so a timeout result is still captured by the awaiting request. The busy check + state-set must have no `await` between them so they're atomic under asyncio's cooperative scheduling.

For deterministic tests, the *mock* must make a large acquisition reliably outlast the grace without blocking its own event loop: generate one frame and tile its bytes ×iterations (O(1) work), then stream the wire payload in chunks with `await drain()` + a small per-chunk sleep. Generating N distinct frames synchronously blocks the loop and makes server shutdown/cancellation hang.

### Event-driven WebSocket state: let one component own a broadcast type

If both an `InstrumentState.on_change` hook and an acquisition runner broadcast on the same transition, clients receive two frames in an order that depends on call sequence (a generic `state` frame arrived before the intended `busy` frame). Have a single owner per semantic event (the runner emits `busy`/idle); don't auto-broadcast low-level state transitions that a higher layer already narrates.

### Previews must be downsampled before sending to browser

Full 512×512 16-bit images at high frame rates will saturate a LAN WebSocket. Downsample to ~256×256 8-bit for preview. Full data always stays on the host and is downloaded on demand.

---

## Bugs & fixes

> Add entries as bugs are found and fixed. Format:
>
> ### Short title
> **Symptom:** What was observed
> **Root cause:** Why it happened
> **Fix:** What was changed
> **Prevention:** How to avoid this class of bug in the future

<!-- Add entries below this line, most recent first -->

---

## Python / FastAPI

### Detect a passive TCP disconnect with an idle EOF watcher

For a request/response protocol on a single socket (like cSPAD), you cannot tell the connection dropped until your next send fails — but the UI needs `/api/status` to report disconnected *immediately*, with no polling of the hardware. Solution: between commands, run a background task that does `await reader.read(1)`. Since the peer never sends unsolicited data when idle, this only returns on EOF (`b""`) → mark disconnected. Before sending a command, cancel the watcher; after reading the response, restart it. The command lock guarantees the watcher and a command never read the socket concurrently. See `bridge/protocol/client.py`.

### `typing_extensions.TypedDict`, not `typing.TypedDict`, for FastAPI response models on Python < 3.12

If a route's return type is a `TypedDict` built from `typing.TypedDict`, pydantic v2 raises `PydanticUserError: Please use typing_extensions.TypedDict ... on Python < 3.12` when generating the schema. Import `TypedDict` from `typing_extensions` (already a pydantic dependency).

### Starlette `TestClient` lifespan can hang or raise on teardown

Two failure modes hit during Phase 2, both surfacing as a hung `portal thread.join()` or a `CancelledError` from the lifespan task on `client.__exit__()`:
1. **An open WebSocket** whose server handler is blocked in `await ws.receive_text()` prevents shutdown. The test/client wrapper must close every WebSocket it opened before exiting the `TestClient`.
2. **Background `asyncio.create_task` tasks** (e.g. a reconnect loop) left running when the bridge is disconnected at shutdown. The lifespan's shutdown must `cancel()` *and* `await` every such task (suppressing `BaseException`), and avoid `writer.wait_closed()` which can block. Orphaned tasks spawned outside an anyio task group surface as `CancelledError` through the lifespan.

Use `pytest-timeout` (`--timeout=60 --timeout-method=thread`) so a hang produces a traceback pointing at the blocked line instead of stalling the whole suite.

---

## React / TypeScript

<!-- Add entries as patterns and gotchas are discovered -->

---

## Data pipeline compatibility

### Reducer expects specific folder structure

The `Reduce_size_512SPAD.py` script expects:
- A directory containing PNG files named `IMGxxxxx.png`
- First PNG must have metadata (PIL `Image.info`) with at least `Frames` and optionally `Gate steps`
- Output: `movie_arr_<foldername>.npy` (3D: `nframes × rows × cols`) + `meta_<foldername>.json` (serialized metadata dict)

The bridge's file writer must produce this exact structure or the reducer will fail.

### Reducer hardcodes array dimensions

The reducer creates arrays with shape `(picture_amount, 512, 256)` — note the 256 column count is hardcoded to half the sensor width (a crop region). The bridge should make this configurable or match the existing convention. Verify with the lab which crop region they use.

### Metadata keys must match exactly

PNG metadata keys expected by the pipeline (from `python_image_metadata.py`):
`Author`, `System`, `Date taken`, `Time taken`, `Mode`, `Integration time`, `Laser frequency`, `Overlap`, `Frame`, `Frames`, `Gate step`, `Gate steps`, `Gate step arbitrary`, `Gate step size`, `Gate width`, `Gate offset`, `Gate increment`, `External frame trigger`, `External gate trigger`, `Software version`

Missing or renamed keys will cause silent data loss in downstream analysis.

---

## Lab operations

<!-- Add entries about lab-specific workflows, gotchas, or conventions discovered during hardware bring-up -->
