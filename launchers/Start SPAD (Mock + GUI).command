#!/bin/bash
# Double-click this file to start the SPAD GUI with the mock camera.
# It launches: mock vendor server + bridge + web GUI, then opens your browser.
# Close this window (or press Ctrl+C) to stop everything.

cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
echo "Project: $ROOT"

if [ ! -d ".venv" ]; then
  echo
  echo "No Python environment (.venv) found. First-time setup, run once in Terminal:"
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

sleep 4
open "http://localhost:5173"

echo
echo "============================================================"
echo "  SPAD GUI is running."
echo "  Browser:  http://localhost:5173"
echo "  API docs: http://localhost:8080/docs"
echo "  Close this window (or Ctrl+C) to stop everything."
echo "============================================================"
wait
