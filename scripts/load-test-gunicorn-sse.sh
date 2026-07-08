#!/usr/bin/env bash
# Load test: parallel SSE streams + health GETs under Gunicorn worker pressure.
#
# Phase A: partial SSE load + health probes (workers not fully saturated).
# Phase B: full SSE stress (all workers on long-lived streams) + recovery check.
#
# Env:
#   LOAD_TEST_API_BASE           — default http://127.0.0.1:8000
#   RECEPTION_API_TOKEN          — Bearer token with reception:read (required for SSE)
#   LOAD_TEST_RESERVATION_ID     — reservation PK for SSE (required)
#   LOAD_TEST_SSE_COUNT          — default 20
#   LOAD_TEST_PARTIAL_SSE_COUNT  — default 6
#   LOAD_TEST_HEALTH_CONCURRENCY — parallel health GETs per tick (default 4)
#   LOAD_TEST_DURATION_SEC       — default 180

set -euo pipefail

API_BASE="${LOAD_TEST_API_BASE:-http://127.0.0.1:8000}"
SSE_COUNT="${LOAD_TEST_SSE_COUNT:-20}"
PARTIAL_SSE_COUNT="${LOAD_TEST_PARTIAL_SSE_COUNT:-6}"
HEALTH_CONCURRENCY="${LOAD_TEST_HEALTH_CONCURRENCY:-4}"
DURATION_SEC="${LOAD_TEST_DURATION_SEC:-180}"
RESERVATION_ID="${LOAD_TEST_RESERVATION_ID:-}"
TOKEN="${RECEPTION_API_TOKEN:-}"
HEALTH_TIMEOUT_SEC="${LOAD_TEST_HEALTH_TIMEOUT_SEC:-15}"

PASS=1
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

log() {
  printf '[load-test] %s\n' "$*"
}

fail() {
  log "FAIL: $*"
  PASS=0
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_cmd curl
require_cmd python3

if [[ -z "$TOKEN" || -z "$RESERVATION_ID" ]]; then
  echo "RECEPTION_API_TOKEN and LOAD_TEST_RESERVATION_ID are required." >&2
  exit 1
fi

SSE_URL="${API_BASE%/}/api/v1/reception/reservation-versions/stream/?reservation_id=${RESERVATION_ID}&scope=messages"
HEALTH_URL="${API_BASE%/}/api/v1/reception/health/"
STATUS_URL="${API_BASE%/}/api/v1/reception/system/status/"

health_once() {
  curl -sf --max-time "$HEALTH_TIMEOUT_SEC" "$HEALTH_URL" >/dev/null
}

health_burst() {
  local i
  for ((i = 0; i < HEALTH_CONCURRENCY; i++)); do
    health_once &
  done
  wait
}

start_sse() {
  local id="$1"
  curl -sN --max-time "$((DURATION_SEC + 30))" \
    -H "Authorization: Bearer ${TOKEN}" \
    "$SSE_URL" >"$TMP_DIR/sse-${id}.log" 2>&1 &
  echo $! >"$TMP_DIR/sse-${id}.pid"
}

stop_all_sse() {
  local pidfile pid
  for pidfile in "$TMP_DIR"/sse-*.pid; do
    [[ -f "$pidfile" ]] || continue
    pid="$(cat "$pidfile")"
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}

active_sse_connections() {
  curl -sf "$STATUS_URL" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sse"]["active_connections"])'
}

log "Phase A: ${PARTIAL_SSE_COUNT} SSE + health bursts for ${DURATION_SEC}s"
for ((i = 0; i < PARTIAL_SSE_COUNT; i++)); do
  start_sse "a-${i}"
done
sleep 2
END=$((SECONDS + DURATION_SEC / 2))
while ((SECONDS < END)); do
  health_burst || fail "health failed during phase A"
  sleep 2
done
stop_all_sse
sleep 3
health_once || fail "health did not recover after phase A"

log "Phase B: ${SSE_COUNT} SSE stress + recovery"
for ((i = 0; i < SSE_COUNT; i++)); do
  start_sse "b-${i}"
done
sleep 5
ACTIVE="$(active_sse_connections || echo 0)"
log "active_connections=${ACTIVE} (worker-local sample)"
END=$((SECONDS + DURATION_SEC / 2))
while ((SECONDS < END)); do
  health_burst || log "WARN: health slow/queued during full SSE (expected with sync workers)"
  sleep 2
done
stop_all_sse
sleep 5
health_once || fail "health did not recover after phase B teardown"
ACTIVE_AFTER="$(active_sse_connections || echo 0)"
if [[ "$ACTIVE_AFTER" != "0" ]]; then
  fail "active_connections=${ACTIVE_AFTER} after teardown (expected 0 on this worker)"
fi

if [[ "$PASS" == "1" ]]; then
  log "PASS"
  exit 0
fi
log "FAIL — see messages above"
exit 1
