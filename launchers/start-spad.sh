#!/bin/bash
# Start the SPAD GUI with the mock camera.
#   Run from a terminal:   ./launchers/start-spad.sh
#   (or double-click "Start SPAD (Mock + GUI).command", which calls this)
# Launches: mock vendor server + bridge + web GUI, then opens your browser.
# Press Ctrl+C (or close the terminal) to stop everything.

cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
echo "Project: $ROOT"

if [ ! -d ".venv" ]; then
  echo
  echo "No Python environment (.venv) found. First-time setup, run once:"
  echo "  python3.11 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
  echo
  read -r -p "Press Enter to close."
  exit 1
fi
source .venv/bin/activate

if [ ! -d "frontend/node_modules" ]; then
  echo "Installing web GUI dependencies (first run only)..."
  ( cd frontend && npm install ) || { read -r -p "npm install failed. Press Enter."; exit 1; }
fi

# Open a URL in the default browser (macOS uses `open`, Linux uses `xdg-open`).
open_url() {
  if command -v open >/dev/null 2>&1; then open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1"
  fi
}

echo "Starting mock camera, bridge, and GUI..."
python -m mock_server --port 9999 &
MOCK=$!
uvicorn bridge.main:app --port 8080 &
BRIDGE=$!
( cd frontend && npm run dev ) &
FRONT=$!

cleanup() {
  echo
  echo "Stopping SPAD..."
  kill "$MOCK" "$BRIDGE" "$FRONT" 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "Waiting for the GUI to be ready (first run can take ~10s)..."
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "http://localhost:5173/"; then break; fi
  sleep 1
done
open_url "http://localhost:5173"

echo
echo "============================================================"
echo "  SPAD GUI is running."
echo "  Browser:  http://localhost:5173"
echo "  API docs: http://localhost:8080/docs"
echo "  Press Ctrl+C (or close this window) to stop everything."
echo "============================================================"
wait
