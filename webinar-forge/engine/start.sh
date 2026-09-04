#!/usr/bin/env bash
# Start the voice engine, creating its venv on first run.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${VOICE_PORT:-5651}"

# Free a stale listener from a previous run.
if command -v lsof >/dev/null 2>&1; then
  PID="$(lsof -ti:"$PORT" 2>/dev/null || true)"
  if [ -n "$PID" ]; then
    echo "Stopping stale process on :$PORT (pid $PID)"
    kill "$PID" 2>/dev/null || true
    sleep 1
  fi
fi

if [ ! -d .venv ]; then
  echo "Creating virtualenv (first run — installing torch can take several minutes)…"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/python engine.py
