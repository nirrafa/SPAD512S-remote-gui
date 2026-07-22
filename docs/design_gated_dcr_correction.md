# Design: gated dark-count (DCR) reference & correction

> **Status: design only, not implemented.** This lives on the `gated-dcr-correction-design`
> branch until we decide to build it. Nothing here touches `main`.

## Problem (as described by the user, 2026-07-22)

The SPAD512² shows significant dark count rate (DCR) noise in gated time-resolved
acquisitions. Physically:

- Each gate opens the sensor for a few ns; DCR is heat-driven, so it's dominated by
  how much time each pixel gets to cool off between gates — i.e. it scales with the
  **trigger repetition rate** (80 MHz gives ~7.5 ns to cool; the lab's usual divided
  20 MHz trigger gives much more).
- Even at reduced rep rate, some DCR remains, and it **rises over the course of a
  measurement** as the sensor heats up, **saturating** once each pixel reaches a
  periodic thermal equilibrium (heats during the gate, cools between gates, converges
  to a steady-state average temperature).
- On **Live view** (Phase 14), the noise is barely visible without pulling the display
  range down — which surfaced a second, smaller gap: see [Related gap](#related-gap-no-manual-contrastwb-control) below.

The proposed workflow (user's own words, lightly edited): measure N "dark" frames
(cap closed / dark room) with the **exact same gate configuration** as the real
measurement, build a reference from the dark stack, then correct subsequent real
measurements against it.

## Proposed feature

### Step 1 — Acquire a dark reference

A dark reference is **just a normal gated acquisition**, run with the sensor covered,
using the exact gate configuration intended for the real measurement:
`gate_steps`, `gate_step_size_ps`, `gate_width`, `gate_offset`, `gate_direction`,
`gate_trigger_source`, `bit_depth`, `integration_time`, and `iterations`. No new
device-facing protocol code is needed — this reuses `AcquisitionRunner.run_gated`
(`bridge/core/acquisition.py:490`) as-is; only the post-processing and storage differ.

`iterations` matters because raw counts scale with it — the dark and signal runs
should use the same `iterations`, or the reference must be normalized per-iteration
before use. Recommend requiring an exact match for v1 (reject/warn on mismatch)
rather than trying to rescale.

**Capturing the saturated behavior "for free":** running the dark acquisition for a
duration comparable to the intended real acquisition means the resulting mean/median
dark map already reflects the saturated steady-state DCR level the user described —
no explicit thermal/time model is needed for v1. (A time-dependent model is listed
under [Later ideas](#later-ideas-not-v1) if empirical subtraction turns out to be
insufficient.)

### Step 2 — Build the reference from the dark stack

A gated acquisition with `iterations=1` decodes to a `(gate_steps, rows, cols)` stack
(`bridge/core/acquisition.py:537-545` — this is exactly the "time domain" stack shape
the user means by "300 images"). Recommendation:

- **Per-pixel, per-gate-step median** (not mean) across repeated dark acquisitions,
  or across `iterations` within one dark acquisition if several are taken — median is
  more robust than mean against occasional afterpulsing/hot-pixel bursts in a Poisson-ish
  process, at the cost of needing ≥3 dark repeats to be meaningful. If only one dark
  acquisition is practical, mean is the fallback.
- Also compute and store the **per-pixel, per-gate-step standard deviation** — not for
  v1 subtraction, but useful later for a "residual within noise floor" mask, or an
  SNR-aware subtraction variant (see below).

### Step 3 — Apply the correction to real signal acquisitions

- New gated-acquisition option: `subtract_dark_reference: <reference_id>` (or a
  "use the latest matching reference" toggle in the GUI).
- Before returning/persisting the corrected view, the runner:
  1. **Validates the fingerprint** — the stored reference's gate config must match the
     current acquisition's exactly (all fields listed in Step 1). Reject with a clear
     error if not; a mismatched reference is physically meaningless.
  2. **Subtracts**, clamped at zero: `corrected = clip(signal - reference, 0, None)`.
     Counts can't be negative, and the existing decode dtype (`uint16`,
     `bridge/protocol/decoder.py:decode_intensity`) can't represent negatives anyway —
     the correction should promote to a float/int32 working array and clip before
     casting back down.
  3. **Never destroys the raw data.** Per the project's existing "full data stays on
     host" principle (`docs/constraints.md` Browser/Front-end section), the vendor-raw
     stack is always the ground truth persisted to disk; the corrected stack is a
     derived, clearly-labeled output (e.g. an additional `movie_arr_corrected_*.npy`
     next to the existing raw one, or a `corrected: true` flag in the sidecar/response
     rather than overwriting anything).

### What "the function" should be — recommendation

**v1: per-pixel-per-gate-step median (or mean) dark map, subtracted and clamped at
zero**, as above. This is the standard "dark frame subtraction" technique from
imaging/astrophotography, directly matches what the user described, needs no fitting
or modeling, and is cheap to compute and apply (one array subtraction per acquisition).

## Architectural fit

- **Storage gap:** the existing `CalibrationStore` (`bridge/core/calibration_state.py`)
  only tracks a status enum per calibration kind (`none`/`running`/`done`/`failed` +
  a timestamp) — it holds no array data and isn't persisted across restarts. This
  feature needs real per-pixel-per-gate-step array storage, which is a different shape
  of problem. Proposed: a small `DcrReferenceStore`, following the same pattern
  `CheckpointStore` and `ExperimentLog` already use — lazy-initialized SQLite metadata
  under `data_root` (the fingerprint params, frame shape, creation time, file path),
  with the actual reference array saved as a `.npy` alongside it. No new persistence
  pattern needs inventing.
- **Backend surface (sketch, not final):**
  - `POST /api/calibrate/gated-dark-reference` — mirrors the shape of the existing
    `/api/calibrate/*` endpoints (`bridge/routes/calibration.py`); runs a gated
    acquisition tagged as a dark reference instead of a scientific run, computes and
    stores the reference.
  - `GET /api/calibrate/gated-dark-reference` — list stored references, so the GUI can
    show whether one already matches the currently-configured gate params.
  - Extend `GatedRequest`/`GatedParams` (`bridge/routes/acquire.py`,
    `bridge/core/acquisition.py`) with an optional `subtract_dark: bool` /
    `dark_reference_id`, consumed in `_gated_op`/`_postprocess` before the response is
    built.
- **Frontend (sketch):** a "measure dark reference" button on the Gated panel (reusing
  the gate-config fields already on screen — no duplicated UI), plus a checkbox
  "subtract dark reference," enabled only when a matching reference exists for the
  current params. The decay curve (Phase 11) would then plot the corrected stack when
  the checkbox is on.

## Related gap: no manual contrast/WB control

Asked separately by the user ("did we implement a WB movable bar"): **no, not fully.**
`ImageCanvas` (`frontend/src/components/ImageCanvas.tsx`) already accepts a `range`
prop that does a min/max stretch, and the Intensity page (`IntensityPage.tsx`) has a
one-shot **auto-stretch** button (percentile-based, `utils/imageProcessing.ts
autoStretchRange`) — but there is no manual draggable min/max slider anywhere, and
**Gated, FLIM, and Live pages don't wire up any stretch control at all** (confirmed by
grep — only `IntensityPage` passes a `range` prop to `ImageCanvas`). This is likely
why the DCR is "barely visible without the lowest WB" on Live view — there's currently
no way to pull the display range down there at all.

This is a small, independent, low-risk addition (a two-handle range slider + wiring
`range` through Gated/FLIM/Live) that would help *see* the DCR being characterized,
regardless of when the subtraction feature above lands. Not implemented here either,
per the "not implementing yet" instruction — flagged so it doesn't get lost, and it
could reasonably be grabbed as its own small task before or independent of the bigger
feature.

## Open questions for when we implement this

1. Median vs. mean for the reference — how many dark repeats are realistic to ask the
   user for in the lab workflow?
2. Should `iterations` mismatch between dark and signal be a hard reject, or should we
   normalize (divide by iterations) and allow it?
3. Where should the "measure dark" step live in the workflow — a dedicated calibration
   panel, or inline on the Gated page next to Acquire?
4. Do we need the corrected stack to flow into the reducer/downstream `.npy` output,
   or is display-only (preview + decay curve) correction enough for v1?

## Later ideas (not v1)

- Explicit time-dependent DCR model per pixel (e.g. saturating exponential
  `DCR(t) ≈ DCR_∞(1 - e^{-t/τ})`) if empirical dark-frame subtraction proves
  insufficient — e.g. if the real acquisition's duration/heating profile can't
  practically be matched by the dark reference's.
- SNR-aware subtraction using the stored per-pixel std (only subtract where the signal
  is statistically above the dark noise floor) instead of blind subtraction.
