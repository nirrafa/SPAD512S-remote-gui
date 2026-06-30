#!/bin/bash
# Start the SPAD GUI with the mock camera.
#   Run from a terminal:   ./launchers/start-spad.sh
#   (or double-click "Start SPAD (Mock + GUI).command", which calls this)
# Builds the web GUI, then starts the mock camera + bridge. The bridge serves
# the GUI at http://localhost:8080 (no separate dev server). Ctrl+C to stop.

cd "$(dirname "$0")/.." || exit 1
echo "Project: $(pwd)"

if [ ! -d ".venv" ]; then
  echo
  echo "No Python environment (.venv) found. First-time setup, run once:"
  echo "  python3.11 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
  echo
  read -r -p "Press Enter to close."
  exit 1
fi
source .venv/bin/activate

# Build the GUI if npm is available; otherwise fall back to an existing build.
# (Double-clicking in Finder can launch with a minimal PATH where npm is absent,
# so we must not hard-depend on it when frontend/dist already exists.)
if command -v npm >/dev/null 2>&1; then
  echo "Building the web GUI (first run installs dependencies, ~1 min)..."
  (
    cd frontend || exit 1
    [ -d node_modules ] || npm install || exit 1
    npm run build
  ) || echo "Build step failed; will serve the existing GUI build if present."
else
  echo "npm not found; will serve the existing GUI build if present."
fi

if [ ! -f frontend/dist/index.html ]; then
  echo
  echo "The web GUI is not built yet. Run this once from a terminal where 'npm'"
  echo "works (e.g. your normal Terminal app) to build it:"
  echo "  cd \"$(pwd)/frontend\" && npm install && npm run build"
  read -r -p "Press Enter to close."
  exit 1
fi

open_url() {
  if command -v open >/dev/null 2>&1; then open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1"
  fi
}

echo "Starting mock camera + bridge..."
python -m mock_server --port 9999 >/dev/null 2>&1 &
MOCK=$!
uvicorn bridge.main:app --port 8080 &
BRIDGE=$!

cleanup() {
  echo
  echo "Stopping SPAD..."
  kill "$MOCK" "$BRIDGE" 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "Waiting for the GUI to be ready..."
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "http://localhost:8080/api/health"; then break; fi
  sleep 1
done
open_url "http://localhost:8080"

echo
echo "============================================================"
echo "  SPAD GUI:  http://localhost:8080"
echo "  API docs:  http://localhost:8080/docs"
echo "  Press Ctrl+C (or close this window) to stop everything."
echo "============================================================"
wait
