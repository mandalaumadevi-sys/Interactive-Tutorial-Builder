#!/usr/bin/env bash
# Start the BACKEND API only (FastAPI on http://127.0.0.1:8000).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "No .venv found. Create it once with:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -e backend"
  exit 1
fi

source .venv/bin/activate
echo "Backend API → http://127.0.0.1:8000   (health: /api/health)"
exec tutorial-builder serve --host 127.0.0.1 --port 8000
