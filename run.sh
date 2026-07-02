#!/usr/bin/env bash
# Start BOTH servers together (backend API + frontend UI) and stop both on Ctrl-C.
#   Frontend (open this):  http://127.0.0.1:5173
#   Backend API:           http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "No .venv found. Create it once with:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -e backend"
  exit 1
fi

source .venv/bin/activate

echo "Starting backend API on http://127.0.0.1:8000 ..."
tutorial-builder serve --host 127.0.0.1 --port 8000 &
BACK=$!

# Install the React app's dependencies once, then start the Vite dev server.
if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend dependencies (npm install)…"
  ( cd frontend && npm install )
fi
echo "Starting frontend (Vite) on http://127.0.0.1:5173 ..."
( cd frontend && exec npm run dev -- --port 5173 --host 127.0.0.1 ) &
FRONT=$!

cleanup(){ echo; echo "Stopping both servers..."; kill "$BACK" "$FRONT" 2>/dev/null || true; }
trap cleanup INT TERM EXIT

echo
echo "  ▸ Open the app:  http://127.0.0.1:5173"
echo "  ▸ API health:    http://127.0.0.1:8000/api/health"
echo "  (Press Ctrl-C to stop both.)"
echo
wait
