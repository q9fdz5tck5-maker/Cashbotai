#!/usr/bin/env bash
# Self-healing build: starts the engine, waits for it, runs the build,
# and retries from the narration cache if either dies.
cd "$(dirname "$0")"
LOG="${1:-/tmp/forge-run.log}"
for attempt in $(seq 1 40); do
  if ! curl -s --noproxy '*' -m 5 http://127.0.0.1:5651/health >/dev/null 2>&1; then
    echo "[$(date +%T)] starting engine (attempt $attempt)" >> "$LOG"
    setsid env VOICE_HOST=127.0.0.1 ./engine/.venv/bin/python engine/engine.py >> "$LOG.engine" 2>&1 < /dev/null &
    for i in $(seq 1 30); do
      curl -s --noproxy '*' -m 5 http://127.0.0.1:5651/health >/dev/null 2>&1 && break
      sleep 5
    done
  fi
  echo "[$(date +%T)] build attempt $attempt" >> "$LOG"
  TTS_CONCURRENCY=1 node bin/webinar-forge build projects/forge-launch/project.json >> "$LOG" 2>&1
  if grep -q "=== Done ===" "$LOG"; then echo "[$(date +%T)] COMPLETE" >> "$LOG"; exit 0; fi
  sleep 5
done
