# Clickable launchers

Double-click instead of typing CLI commands. Each launcher starts the **mock
camera + bridge + web GUI** and opens your browser at `http://localhost:5173`.

| File | Platform | Notes |
|---|---|---|
| `Start SPAD (Mock + GUI).command` | macOS | Double-click. Runs in Terminal; close the window (or Ctrl+C) to stop. |
| `Start SPAD (Mock + GUI).bat` | Windows | Double-click. Opens three windows (mock, bridge, GUI); close them to stop. |

## First-time setup (once per machine)

The launchers expect the Python env and frontend deps to exist. If a launcher
tells you `.venv` is missing, run once in a terminal from the project root:

```
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

(The launcher installs the web GUI's `node_modules` automatically on first run.)

## Using the real camera instead of the mock

On the camera host, start the bridge pointed at the vendor software and skip the
mock. The bridge reads `SPAD_VENDOR_HOST` (default `127.0.0.1`) and
`SPAD_VENDOR_PORT` (default `9999`) — set these to the vendor's TCP endpoint.

## What "it just hangs" means

The mock and bridge are servers — they start and keep running. A window that
sits there with no new prompt is **working correctly**. See
[../docs/manual-testing.md](../docs/manual-testing.md) for the full mental model
and a troubleshooting table.

> A true standalone `.exe`/`.app` (no Python install required) can be built with
> PyInstaller if you need to hand the tool to someone without a dev setup — ask
> and it can be added.
