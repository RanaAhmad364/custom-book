#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PYTHON="$BACKEND/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Backend virtual environment not found. Create it and install backend[dev] first." >&2
  exit 1
fi
if [[ ! -f "$BACKEND/.env" ]]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  echo "Created backend/.env. Set PostgreSQL credentials and unique signing keys, then rerun." >&2
  exit 1
fi
if [[ ! -d "$FRONTEND/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run npm install in frontend first." >&2
  exit 1
fi

cd "$BACKEND"
"$PYTHON" -m flask --app wsgi config-check
"$PYTHON" -m flask --app wsgi db-check
"$PYTHON" -m flask --app wsgi db upgrade
"$PYTHON" -m flask --app wsgi seed-demo-catalog --apply --confirm-local-database
"$PYTHON" -m flask --app wsgi dev-provision-admin

"$PYTHON" run.py &
API_PID=$!
cleanup() {
  kill "$API_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting MemoryBook API at http://127.0.0.1:5000 and Vite at http://127.0.0.1:5173."
cd "$FRONTEND"
npm run dev -- --host 127.0.0.1
