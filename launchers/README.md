# Clickable launchers

Start the **mock camera + bridge** and open your browser at
`http://localhost:8080`, without typing CLI commands. The launcher builds the web
GUI once and the **bridge serves it** — there is no separate dev server, so it's
just one URL and one process.

| File | How to run |
|---|---|
| `start-spad.sh` | From a terminal: `./launchers/start-spad.sh`. Works on macOS and Linux. Ctrl+C (or close the terminal) to stop. |
| `Start SPAD (Mock + GUI).command` | macOS Finder double-click — a thin wrapper that runs `start-spad.sh`. |

Both run the same logic (`start-spad.sh` is the single source of truth).

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
