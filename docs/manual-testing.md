# Manual testing with the mock server

How to exercise the bridge yourself, end to end, with **no hardware** — using the
mock vendor server that pretends to be the SPAD512² camera.

**References:** [Plan](plan.md) · [Progress](progress.md) · [README](../README.md)

---

## First, two things that confuse everyone

**1. Some commands print nothing — that is success.**
`cd` and `source` are silent on success. The only sign they worked is your prompt
now starts with `(.venv)`. To confirm:

```
pwd
```

should print the project path.

**2. Servers "hang" on purpose.**
The mock and the bridge are *servers*: they start up and then **keep running
forever**, waiting for requests. The terminal will look **frozen** (no new prompt) —
that is correct, it means the server is alive. You do not wait for it to finish; you
leave it running and open a **new** terminal for the next step.

You will end up with up to three terminals:

| Terminal | Runs | Behavior |
|---|---|---|
| **A** | the mock camera | starts, prints one line, then "hangs" (running) |
| **B** | the bridge (the app) | starts, prints logs, then "hangs" (running) |
| **C** | your `curl` test commands | each returns immediately with output |

In **every** terminal, run this first (silent on success):

```
cd "/Users/nirs/Documents/TAU/FemtoNano Group/SPAD"
source .venv/bin/activate
```

---

## Option 1 — Run the automated tests (simplest)

One terminal, no servers to babysit. The tests start and stop the mock internally.

```
pytest tests/ pre_dev_tests/test_02_acquisition_intensity.py pre_dev_tests/test_14_mock_vendor_server.py
```

**Expect:** a stream of `PASSED` ending in a green line like `45 passed in 4.66s`.

---

## Option 2 — Drive it live yourself

### Terminal A — start the mock camera

```
python -m mock_server --port 9999
```

Pretends to be the SPAD512² on TCP port 9999.
**Expect:** one line, then it sits silently (running — leave it):

```
Mock vendor server listening on 127.0.0.1:9999
```

### Terminal B — start the bridge

```
uvicorn bridge.main:app --port 8080
```

The web app: connects to the mock on 9999 (camera handshake), serves the API on 8080.
**Expect:** log lines ending with these, then it "hangs" (running — leave it):

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

### Terminal C — test it

Run these one at a time; each returns JSON immediately.

**Is the bridge talking to the camera?**

```
curl -s localhost:8080/api/status
```

Expect: `{"vendor_connected":true,"instrument_state":"idle"}` — `vendor_connected:true`
is the key.

**Take an intensity image:**

```
curl -s -X POST localhost:8080/api/acquire/intensity -H 'Content-Type: application/json' -d '{"bit_depth":8,"integration_time_ms":100,"iterations":1,"roi_width":512}'
```

Expect a long line (the `preview` is a downsampled-image blob — normal):

```
{"status":"done","preview":"<long string>","host_path":"data/intensity_images/acq00001","total_frames":1,"integration_time_unit":"ms","bytes":262144}
```

`"status":"done"` and `"bytes":262144` (= 512×512) mean a full frame came back and was saved.

**Take a gated stack (20 gate steps):**

```
curl -s -X POST localhost:8080/api/acquire/gated -H 'Content-Type: application/json' -d '{"bit_depth":8,"gate_steps":20,"gate_step_size_ps":18}'
```

Expect `"status":"done"` with `"total_gate_steps":20` and `"total_frames":20`.

**System info / triggers:**

```
curl -s localhost:8080/api/system/info
curl -s localhost:8080/api/system/triggers
```

Expect parsed FPGA serials / sensor size / features, and laser + frame frequencies.

**See the saved data:**

```
ls data/intensity_images
```

Expect a folder like `acq00001` containing a saved `.npy` array.

### Easiest of all: the built-in API page

Open **http://localhost:8080/docs** — FastAPI auto-generates an interactive page with
every endpoint. Click "Try it out", fill the form, hit Execute, see the response. No
`curl` needed.

### Try the browser GUI (optional)

A fourth terminal:

```
cd frontend
npm run dev
```

Open the printed URL. Vite proxies `/api` and `/ws` to the bridge on 8080, so you can
drive intensity/gated acquisitions, watch the preview render on the canvas, and scrub
gate steps.

### When you're done

Press **Ctrl+C** in Terminal A and Terminal B to stop the servers.

---

## Troubleshooting

- **`vendor_connected:false`** — the mock (Terminal A) isn't running, or the bridge was
  started before it. Start the mock first, then the bridge.
- **`curl: connection refused`** — the bridge (Terminal B) isn't running, or you used the
  wrong port. The bridge is on **8080**, the mock on **9999**.
- **`command not found` / `ModuleNotFoundError`** — you forgot `source .venv/bin/activate`
  in that terminal.
- **`address already in use`** — a previous mock/bridge is still running. Find the old
  terminal and Ctrl+C it, or use a different `--port`.
