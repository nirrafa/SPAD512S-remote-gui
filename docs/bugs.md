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

### B-08 — Bridge `_read_binary(expected_bytes=…)` cannot detect a truncated/errored acquisition · S2 (bridge-side)

**Where:** [`bridge/protocol/client.py`](../bridge/protocol/client.py) `_read_binary`.
**Mechanism:** When `expected_bytes` is known, the reader does
`readexactly(expected_bytes + 4)`. If the vendor aborts an acquisition and returns
a short `…ERROR…DONE` frame instead of the full payload, `readexactly` blocks until
`read_timeout` and surfaces a `TimeoutError` rather than recognising the `ERROR`.
**Relation:** Discovered while fixing **B-02**. The mock now terminates errored
acquisitions with `DONE` (so the streaming read path breaks), but the
`expected_bytes` path still can't surface a clean error.
**Suggested fix:** Have `_read_binary` peek for a leading `ERROR` / short frame
before/while doing the exact read, or fall back to the streaming loop and validate
length afterward. Address in the Phase 2/9 reliability work.

---

## Fixed

| ID | Severity | Summary | Fixed in | Regression test |
|---|---|---|---|---|
| B-01 | S1 | `_handle_intensity` read ROI width from arg index 8; the `I` command places width at index 7, so any `im_width≠512` was silently ignored → `cSPAD` reshape `ValueError`. | Phase 1 review fixes | `tests/test_mock_tcp.py::test_intensity_honors_non_512_roi_width` (+ cSPAD `im_width=256` smoke) |
| B-02 | S2 | Fault injected during a binary acquisition returned text with no terminator → `cSPAD`/bridge read-until-`DONE` loops hung. Mock now terminates errors with `DONE` while keeping `ERROR` in the text (matches `bridge/protocol/decoder.py`). | Phase 1 review fixes | `tests/test_mock_tcp.py::test_fault_injected_acquisition_terminates_with_done` |
| B-03 | S2 | `GATED_BIT_DEPTHS` was unused and gated validated against `INT_BIT_DEPTHS`, wrongly accepting 1/4-bit (vendor: gated is 6–12 only). Added `_resolve_gated_bit_depth`. | Phase 1 review fixes | `tests/test_mock_tcp.py::test_gated_rejects_sub_six_bit_depth` |

---

## By design / not a bug

- **Gated mode is always 512-wide.** The vendor `G` command string carries no
  `im_width` field (see `cSPAD.get_gated_intensity`), so the mock cannot vary
  gated frame width and emits 512. A caller passing `im_width≠512` to gated is a
  caller error; the bridge must constrain gated ROI width to 512 (or full sensor
  width) in Phase 4.
