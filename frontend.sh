#!/usr/bin/env bash
# Start the FRONTEND only (React + Vite dev server). Default port 5173 (override: ./frontend.sh 3000).
# The UI talks to the backend API at http://127.0.0.1:8000 (start backend.sh too).
set -euo pipefail
cd "$(dirname "$0")/frontend"

# One-time (or after dependency changes): install node modules.
if [ ! -d node_modules ]; then
  echo "Installing frontend dependencies (npm install)…"
  npm install
fi

PORT="${1:-5173}"
echo "Frontend → http://127.0.0.1:${PORT}   (expects backend API at http://127.0.0.1:8000)"
exec npm run dev -- --port "$PORT" --host 127.0.0.1
