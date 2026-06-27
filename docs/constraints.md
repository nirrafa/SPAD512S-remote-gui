# Constraints

> **Keep this file up to date.** Every time a new constraint is discovered or decided — hardware, protocol, regulatory, or architectural — add it here.

## Hardware

- Camera is **Pi Imaging SPAD512²** (512×512 sensor), connected via 2× USB3 + 5V to a dedicated Windows host PC.
- Only one TCP connection to the vendor command server at a time.
- Vendor command server binds to `127.0.0.1` only (ports 9998/9999) — no remote access without a bridge.

## Network & Security

- LAN-only deployment; no public internet exposure.
- No authentication in v1 — anonymous shared workspace.
- Bridge must run on the same Windows host as the vendor software.

## Protocol

- Vendor protocol is ASCII over TCP, single-connection, request–response with `DONE`/`ERROR` framing.
- All camera commands must be serialized through one async queue in the bridge; concurrent commands corrupt the protocol.
- Health polling (`R`, `V`, `S`) is read-only and may bypass the command queue but must not interleave with in-flight acquisitions.

## Data & Compatibility

- Acquired data must match the existing analysis pipeline layout: `meta_acqXXXXX.json` + `movie_arr_acqXXXXX.npy` (3D array: `nframes × x × y`).
- PNG metadata keys must align with vendor conventions (Author, Mode, Integration time, etc.).
- Downstream scripts (`512^2_*.py`, `SEP_D.py`) must work unchanged on bridge-produced data.

## Operational

- Vendor app must be running before the bridge starts; bridge does not auto-start the vendor app (v1).
- Stop/abort must respect safe boundaries (between steps/iterations); in-flight frames must finish.
- Auto-protect thresholds (temperature, voltage) may abort acquisitions — this is by design.

## Browser / Front-end

- Full data arrays stay on the host; browser receives downsampled previews only.
- Full data download is on-demand, not automatic.
