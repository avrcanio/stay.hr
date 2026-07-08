#!/usr/bin/env bash
# Load test: parallel SSE streams + health GETs under Gunicorn worker pressure.
# Required before production sign-off after Gunicorn worker changes.
#
# With sync workers, health probes may queue while all workers serve SSE (expected).
# Pass criteria: enough SSE connect (up to worker count), no WORKER TIMEOUT, API
# recovers immediately after SSE teardown, and health succeeds under partial load.
#
# Env:
#   LOAD_TEST_API_BASE          — default http://127.0.0.1:8000
#   RECEPTION_API_TOKEN         — Bearer token with reception:read (required for SSE)
#   LOAD_TEST_RESERVATION_ID    — reservation PK for SSE (required)
#   LOAD_TEST_SSE_COUNT         — default 20
#   LOAD_TEST_HEALTH_CONCURRENCY — parallel health GETs per tick (default 4)
#   LOAD_TEST_DURATION_SEC      — default 180 (3 min)
#   LOAD_TEST_HEALTH_P95_MS     — default 2000 (successful requests only)
#   LOAD_TEST_LIGHT             — 1 for reduced CI smoke (shorter duration, fewer requests)
#   OPS_CI_ARTIFACT_DIR         — when set, tee full output to timestamped artifact file

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck source=ops-common.sh
source "$ROOT_DIR/scripts/ops-common.sh"

API_BASE="${LOAD_TEST_API_BASE:-http://127.0.0.1:8000}"
SSE_COUNT="${LOAD_TEST_SSE_COUNT:-20}"
HEALTH_CONCURRENCY="${LOAD_TEST_HEALTH_CONCURRENCY:-4}"
DURATION_SEC="${LOAD_TEST_DURATION_SEC:-180}"
HEALTH_P95_MS="${LOAD_TEST_HEALTH_P95_MS:-2000}"
RESERVATION_ID="${LOAD_TEST_RESERVATION_ID:-}"
TOKEN="${RECEPTION_API_TOKEN:-}"
HEALTH_TIMEOUT_SEC="${LOAD_TEST_HEALTH_TIMEOUT_SEC:-15}"
PARTIAL_SSE_COUNT="${LOAD_TEST_PARTIAL_SSE_COUNT:-6}"
PHASE_C_ENABLED="${LOAD_TEST_PHASE_C:-1}"
PHASE_C_GET_COUNT="${LOAD_TEST_PHASE_C_GET_COUNT:-100}"
PHASE_C_PATCH_COUNT="${LOAD_TEST_PHASE_C_PATCH_COUNT:-20}"
SYNC_VERSIONS_URL="${API_BASE%/}/api/v1/reception/sync-versions/?reservation_id=${RESERVATION_ID}&scope=messages"
RESERVATION_URL="${API_BASE%/}/api/v1/reception/reservations/${RESERVATION_ID}/"
BENCHMARK_FILE="${LOAD_TEST_BENCHMARK_FILE:-$ROOT_DIR/data/ops/health-latency-benchmark.txt}"

if is_truthy "${LOAD_TEST_LIGHT:-}"; then
  SSE_COUNT="${LOAD_TEST_SSE_COUNT:-8}"
  PARTIAL_SSE_COUNT="${LOAD_TEST_PARTIAL_SSE_COUNT:-4}"
  DURATION_SEC="${LOAD_TEST_DURATION_SEC:-45}"
  PHASE_C_GET_COUNT="${LOAD_TEST_PHASE_C_GET_COUNT:-20}"
  PHASE_C_PATCH_COUNT="${LOAD_TEST_PHASE_C_PATCH_COUNT:-5}"
fi

PASS=1
TMP_DIR="$(mktemp -d)"
INITIAL_ARRIVAL_JSON=""
INITIAL_ARRIVAL_CAPTURED=0

restore_initial_arrival_text() {
  [[ "$INITIAL_ARRIVAL_CAPTURED" != "1" ]] && return 0
  local payload code
  payload="$(printf '{"guest_stated_arrival_text":%s}' "$INITIAL_ARRIVAL_JSON")"
  code="$(auth_curl_code PATCH "$RESERVATION_URL" 15 "$payload")"
  log "Restored guest_stated_arrival_text (HTTP ${code})"
}

cleanup_load_test() {
  restore_initial_arrival_text
  rm -rf "$TMP_DIR"
}

trap cleanup_load_test EXIT

log() {
  printf '[load-test] %s\n' "$*"
}

fail() {
  log "FAIL: $*"
  PASS=0
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "Missing required command: $1"
    exit 1
  fi
}

require_cmd curl
require_cmd python3

if [[ -z "$TOKEN" ]]; then
  log "RECEPTION_API_TOKEN is required for SSE portion of the test."
  exit 1
fi

if [[ -z "$RESERVATION_ID" ]]; then
  log "LOAD_TEST_RESERVATION_ID is required."
  exit 1
fi

HEALTH_URL="${API_BASE%/}/api/v1/reception/health/"
STATUS_URL="${API_BASE%/}/api/v1/reception/system/status/"
SSE_URL="${API_BASE%/}/api/v1/reception/reservation-versions/stream/?reservation_id=${RESERVATION_ID}&scope=messages"

if [[ -n "${OPS_CI_ARTIFACT_DIR:-}" ]]; then
  setup_ci_artifact_tee "load-test-gunicorn-sse"
fi

log "API base: ${API_BASE}"
is_truthy "${LOAD_TEST_LIGHT:-}" && log "mode: light (CI smoke)"
log "Stress SSE: ${SSE_COUNT}, partial-load SSE: ${PARTIAL_SSE_COUNT}, health concurrency: ${HEALTH_CONCURRENCY}, duration: ${DURATION_SEC}s"

health_curl() {
  curl -sS --max-time "$1" -o /dev/null -w '%{http_code}' "$HEALTH_URL" || echo "000"
}

auth_curl_code() {
  local method="$1"
  local url="$2"
  local timeout="$3"
  local data="${4:-}"
  if [[ -n "$data" ]]; then
    curl -sS --max-time "$timeout" -X "$method" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$data" \
      -o /dev/null -w '%{http_code}' "$url" || echo "000"
  else
    curl -sS --max-time "$timeout" \
      -H "Authorization: Bearer ${TOKEN}" \
      -o /dev/null -w '%{http_code}' "$url" || echo "000"
  fi
}

capture_initial_arrival_text() {
  INITIAL_ARRIVAL_JSON="$(curl -sS --max-time 10 -H "Authorization: Bearer ${TOKEN}" "$RESERVATION_URL" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('guest_stated_arrival_text')))")"
  INITIAL_ARRIVAL_CAPTURED=1
}

print_latency_percentiles() {
  local label="$1"
  local file="$2"
  python3 - "$label" "$file" <<'PY'
import sys
from pathlib import Path

label, path = sys.argv[1], Path(sys.argv[2])
values = [int(x) for x in path.read_text().splitlines() if x.strip().isdigit()] if path.exists() else []
if not values:
    print(f"[benchmark] {label}: no successful samples")
    raise SystemExit(0)
values.sort()
n = len(values)

def pct(p):
    return values[max(0, min(n - 1, int(n * p) - 1))]

print(f"[benchmark] {label} n={n} p50={pct(0.50)}ms p95={pct(0.95)}ms p99={pct(0.99)}ms")
PY
}

append_benchmark_snapshot() {
  local phase_label="$1"
  local latency_file="$2"
  mkdir -p "$(dirname "$BENCHMARK_FILE")"
  {
    echo "---"
    benchmark_header "$phase_label" "$ROOT_DIR"
    echo "phase=${phase_label}"
    print_latency_percentiles "$phase_label" "$latency_file"
  } >>"$BENCHMARK_FILE"
}

# --- Preflight ---
HEALTH_CODE="$(health_curl 5)"
if [[ "$HEALTH_CODE" != "200" ]]; then
  fail "health preflight returned HTTP ${HEALTH_CODE}"
  exit 1
fi
log "Preflight health OK"

GUNICORN_WORKERS="$(curl -sS --max-time 5 -H "Authorization: Bearer ${TOKEN}" "$STATUS_URL" | python3 -c "import json,sys; print(json.load(sys.stdin)['gunicorn']['workers'])")"
log "Gunicorn workers (from status): ${GUNICORN_WORKERS}"

# --- Phase A: partial SSE load — health must stay responsive ---
PARTIAL_PIDS=()
for i in $(seq 1 "$PARTIAL_SSE_COUNT"); do
  curl -sS -N --max-time "$((DURATION_SEC + 30))" \
    -H "Authorization: Bearer ${TOKEN}" \
    "$SSE_URL" \
    >"$TMP_DIR/partial-sse-${i}.log" 2>&1 &
  PARTIAL_PIDS+=("$!")
done
sleep 2

PARTIAL_HEALTH_OK=0
PARTIAL_LAT="$TMP_DIR/latencies_phase_a.txt"
: >"$PARTIAL_LAT"
for _ in $(seq 1 10); do
  START_MS="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"
  CODE="$(health_curl 5)"
  END_MS="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"
  if [[ "$CODE" == "200" ]]; then
    PARTIAL_HEALTH_OK=$((PARTIAL_HEALTH_OK + 1))
    echo $((END_MS - START_MS)) >>"$PARTIAL_LAT"
  fi
done
log "Phase A (partial SSE=${PARTIAL_SSE_COUNT}): ${PARTIAL_HEALTH_OK}/10 health probes returned 200"
if [[ "$PARTIAL_HEALTH_OK" -lt 8 ]]; then
  fail "phase A health degraded with partial SSE load (${PARTIAL_HEALTH_OK}/10)"
fi
print_latency_percentiles "phase_a_partial_sse" "$PARTIAL_LAT"
append_benchmark_snapshot "phase_a_partial_sse" "$PARTIAL_LAT"

for pid in "${PARTIAL_PIDS[@]}"; do
  kill "$pid" 2>/dev/null || true
done
wait 2>/dev/null || true
sleep 2

RECOVERY_CODE="$(health_curl 5)"
if [[ "$RECOVERY_CODE" != "200" ]]; then
  fail "health did not recover after partial SSE teardown (HTTP ${RECOVERY_CODE})"
fi

# --- Phase B: stress — many SSE clients; workers saturate, then recover ---
STRESS_PIDS=()
for i in $(seq 1 "$SSE_COUNT"); do
  curl -sS -N --max-time "$((DURATION_SEC + 30))" \
    -H "Authorization: Bearer ${TOKEN}" \
    "$SSE_URL" \
    >"$TMP_DIR/sse-${i}.log" 2>&1 &
  STRESS_PIDS+=("$!")
done
log "Phase B: started ${SSE_COUNT} SSE streams"
sleep 3

# --- Phase C: reception workload under SSE saturation ---
if [[ "$PHASE_C_ENABLED" == "1" ]]; then
  capture_initial_arrival_text
  log "Phase C: ${PHASE_C_GET_COUNT} GET sync-versions + ${PHASE_C_PATCH_COUNT} PATCH (SSE active)"
  : >"$TMP_DIR/phase_c_get.txt"
  : >"$TMP_DIR/phase_c_patch.txt"
  PHASE_C_LAT="$TMP_DIR/latencies_phase_c.txt"
  : >"$PHASE_C_LAT"

  for _ in $(seq 1 "$PHASE_C_GET_COUNT"); do
    (
      START_MS="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"
      CODE="$(auth_curl_code GET "$SYNC_VERSIONS_URL" 15)"
      END_MS="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"
      if [[ "$CODE" == "200" || "$CODE" == "304" ]]; then
        echo ok >>"$TMP_DIR/phase_c_get.txt"
        echo $((END_MS - START_MS)) >>"$PHASE_C_LAT"
      else
        echo "fail:${CODE}" >>"$TMP_DIR/phase_c_get.txt"
      fi
    ) &
  done

  for i in $(seq 1 "$PHASE_C_PATCH_COUNT"); do
    (
      CODE="$(auth_curl_code PATCH "$RESERVATION_URL" 15 "{\"guest_stated_arrival_text\":\"load-test-${i}\"}")"
      if [[ "$CODE" == "200" ]]; then
        echo ok >>"$TMP_DIR/phase_c_patch.txt"
      else
        echo "fail:${CODE}" >>"$TMP_DIR/phase_c_patch.txt"
      fi
    ) &
  done
  wait || true

  PHASE_C_GET_OK="$(grep -c '^ok$' "$TMP_DIR/phase_c_get.txt" 2>/dev/null || echo 0)"
  PHASE_C_PATCH_OK="$(grep -c '^ok$' "$TMP_DIR/phase_c_patch.txt" 2>/dev/null || echo 0)"
  log "Phase C results: GET ok=${PHASE_C_GET_OK}/${PHASE_C_GET_COUNT} PATCH ok=${PHASE_C_PATCH_OK}/${PHASE_C_PATCH_COUNT}"
  print_latency_percentiles "phase_c_reception_workload" "$PHASE_C_LAT"
  append_benchmark_snapshot "phase_c_reception_workload" "$PHASE_C_LAT"

  MIN_GET=$((PHASE_C_GET_COUNT * 30 / 100))
  MIN_PATCH=$((PHASE_C_PATCH_COUNT * 30 / 100))
  [[ "$MIN_GET" -lt 1 ]] && MIN_GET=1
  [[ "$MIN_PATCH" -lt 1 ]] && MIN_PATCH=1
  if [[ "$PHASE_C_GET_OK" -lt "$MIN_GET" ]]; then
    fail "phase C GET success ${PHASE_C_GET_OK}/${PHASE_C_GET_COUNT} below ${MIN_GET}"
  fi
  if [[ "$PHASE_C_PATCH_OK" -lt "$MIN_PATCH" ]]; then
    fail "phase C PATCH success ${PHASE_C_PATCH_OK}/${PHASE_C_PATCH_COUNT} below ${MIN_PATCH}"
  fi
fi

END_TIME=$((SECONDS + DURATION_SEC))
HEALTH_OK=0
HEALTH_FAIL=0
LATENCY_OK_FILE="$TMP_DIR/latencies_ok_ms.txt"
: >"$LATENCY_OK_FILE"

while [[ $SECONDS -lt $END_TIME ]]; do
  START_MS="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"
  CODE="$(health_curl "${HEALTH_TIMEOUT_SEC}")"
  END_MS="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"
  if [[ "$CODE" == "200" ]]; then
    HEALTH_OK=$((HEALTH_OK + 1))
    echo $((END_MS - START_MS)) >>"$LATENCY_OK_FILE"
  else
    HEALTH_FAIL=$((HEALTH_FAIL + 1))
  fi
  sleep 2
done
log "Phase B health during saturation: ok=${HEALTH_OK} fail=${HEALTH_FAIL} (failures expected with sync workers)"

for pid in "${STRESS_PIDS[@]}"; do
  kill "$pid" 2>/dev/null || true
done
wait 2>/dev/null || true
sleep 1
for pid in "${STRESS_PIDS[@]}"; do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 5

POST_CODE="$(health_curl 10)"
for retry in 1 2 3 4 5; do
  if [[ "$POST_CODE" == "200" ]]; then
    break
  fi
  sleep 3
  POST_CODE="$(health_curl 10)"
done
if [[ "$POST_CODE" != "200" ]]; then
  fail "health did not recover after stress SSE teardown (HTTP ${POST_CODE})"
else
  log "Post-stress health OK (workers released)"
fi

# --- SSE leak check: active_connections should return to 0 (sampled per worker) ---
sleep 3
MAX_ACTIVE_SSE=0
for _ in $(seq 1 30); do
  ACTIVE="$(status_active_sse "$STATUS_URL" "$TOKEN" 2>/dev/null || echo "999")"
  if [[ "$ACTIVE" =~ ^[0-9]+$ ]] && [[ "$ACTIVE" -gt "$MAX_ACTIVE_SSE" ]]; then
    MAX_ACTIVE_SSE="$ACTIVE"
  fi
  sleep 0.5
done
log "Post-teardown active_connections max (sampled across workers): ${MAX_ACTIVE_SSE}"
if [[ "$MAX_ACTIVE_SSE" -gt 0 ]]; then
  fail "active_connections still ${MAX_ACTIVE_SSE} after SSE teardown (subscriber leak?)"
fi

# --- Latency p95 for successful probes during stress (if any) ---
read -r P95_MS SAMPLE_COUNT <<EOF
$(python3 - "$LATENCY_OK_FILE" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
values = [int(x) for x in path.read_text().splitlines() if x.strip().isdigit()] if path.exists() else []
if not values:
    print("0 0")
else:
    values.sort()
    idx = max(0, int(len(values) * 0.95) - 1)
    print(f"{values[idx]} {len(values)}")
PY
)
EOF
if [[ "$SAMPLE_COUNT" -gt 0 ]]; then
  log "Phase B successful health p95=${P95_MS}ms (threshold ${HEALTH_P95_MS}ms)"
  print_latency_percentiles "phase_b_saturation" "$LATENCY_OK_FILE"
  append_benchmark_snapshot "phase_b_saturation" "$LATENCY_OK_FILE"
  if [[ "$P95_MS" -gt "$HEALTH_P95_MS" ]]; then
    fail "health p95 ${P95_MS}ms exceeds ${HEALTH_P95_MS}ms"
  fi
fi

# --- SSE connected events ---
CONNECTED_COUNT=0
for f in "$TMP_DIR"/sse-*.log; do
  if [[ -f "$f" ]] && grep -q 'event: connected' "$f" 2>/dev/null; then
    CONNECTED_COUNT=$((CONNECTED_COUNT + 1))
  fi
done
MIN_CONNECTED="$GUNICORN_WORKERS"
if [[ "$SSE_COUNT" -lt "$MIN_CONNECTED" ]]; then
  MIN_CONNECTED="$SSE_COUNT"
fi
log "Phase B SSE connected: ${CONNECTED_COUNT}/${SSE_COUNT} (require >= ${MIN_CONNECTED})"
if [[ "$CONNECTED_COUNT" -lt "$MIN_CONNECTED" ]]; then
  fail "only ${CONNECTED_COUNT}/${SSE_COUNT} SSE streams received connected event"
fi

# --- Worker timeout scan (host with docker compose) ---
if command -v docker >/dev/null 2>&1 && [[ -f docker-compose.yml ]] && docker compose ps django >/dev/null 2>&1; then
  TIMEOUT_HITS="$(docker compose logs django --since "$((DURATION_SEC + 60))s" 2>/dev/null | grep -c 'WORKER TIMEOUT' || true)"
  log "WORKER TIMEOUT in django logs: ${TIMEOUT_HITS}"
  if [[ "$TIMEOUT_HITS" -gt 0 ]]; then
    fail "found ${TIMEOUT_HITS} WORKER TIMEOUT log lines"
  fi
else
  log "Skipping docker log scan (run from repo root with docker compose for full check)"
fi

if [[ "$PASS" -eq 1 ]]; then
  log "PASS — load test completed successfully"
  exit 0
fi

log "FAIL — see messages above"
exit 1
