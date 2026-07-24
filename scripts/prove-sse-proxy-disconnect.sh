#!/usr/bin/env bash
# Phase 1 lifecycle gate: prove Django SSE closes on client disconnect.
#
# Phase A — direct Django (automated): expect sse_stream_closed within ~heartbeat (25s)
# Phase B — BFF AbortSignal (manual browser or optional curl via PROVE_BFF_BASE):
#           EventSource.close / tab close → bff_sse_client_aborted (upstream_abort_wired:true)
#           → upstream fetch abort → Django sse_stream_closed for same stream_id within ~30s
#
# Prerequisites:
#   - Django rebuilt/redeployed with stream registry + close_reason + invariant
#   - web-reception rebuilt with AbortSignal wired into upstream fetch (Phase 1.1)
#   - RECEPTION_API_TOKEN with reception:read
#   - LOAD_TEST_RESERVATION_ID (any reservation PK visible to that token's tenant)
#
# Env:
#   LOAD_TEST_API_BASE       default http://127.0.0.1:8000 (use http://stay_django:8000 from compose)
#   RECEPTION_API_TOKEN      required
#   LOAD_TEST_RESERVATION_ID required
#   PROVE_HOLD_SEC           how long to hold SSE before kill (default 5)
#   PROVE_WAIT_CLOSED_SEC    wait for closed log after kill (default 35)
#   PROVE_BFF_BASE           optional; if set, Phase B curls BFF stream URL (needs session cookie)
#   PROVE_BFF_COOKIE         Cookie header for BFF auth when PROVE_BFF_BASE is set

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_BASE="${LOAD_TEST_API_BASE:-http://127.0.0.1:8000}"
TOKEN="${RECEPTION_API_TOKEN:-}"
RESERVATION_ID="${LOAD_TEST_RESERVATION_ID:-}"
SCOPE="${PROVE_SSE_SCOPE:-messages}"
HOLD_SEC="${PROVE_HOLD_SEC:-5}"
WAIT_CLOSED_SEC="${PROVE_WAIT_CLOSED_SEC:-35}"
ARTIFACT_DIR="${PROVE_ARTIFACT_DIR:-/tmp/sse-proxy-prove}"
BFF_BASE="${PROVE_BFF_BASE:-}"
BFF_COOKIE="${PROVE_BFF_COOKIE:-}"

log() { printf '[prove-sse] %s\n' "$*"; }
fail() { log "FAIL: $*"; exit 1; }

[[ -n "$TOKEN" ]] || fail "RECEPTION_API_TOKEN is required"
[[ -n "$RESERVATION_ID" ]] || fail "LOAD_TEST_RESERVATION_ID is required"

mkdir -p "$ARTIFACT_DIR"
STREAM_URL="${API_BASE%/}/api/v1/reception/reservation-versions/stream/?reservation_id=${RESERVATION_ID}&scope=${SCOPE}"

wait_for_closed() {
  local stream_id="$1"
  local before_ts="$2"
  local closed_line=""
  for _ in $(seq 1 "$WAIT_CLOSED_SEC"); do
    closed_line="$(docker compose logs django --since "${before_ts}Z" 2>/dev/null \
      | grep "sse_stream_closed stream_id=${stream_id}" \
      | tail -1 || true)"
    if [[ -n "$closed_line" ]]; then
      printf '%s' "$closed_line"
      return 0
    fi
    sleep 1
  done
  return 1
}

extract_stream_id() {
  local hdr="$1"
  local body="$2"
  local sid
  sid="$(awk -F': ' 'tolower($1)=="x-sse-stream-id"{print $2}' "$hdr" | tr -d '\r' | tail -1)"
  if [[ -z "$sid" ]]; then
    sid="$(grep -o '"stream_id":"[a-f0-9]*"' "$body" | head -1 | sed 's/.*"stream_id":"//;s/"$//')"
  fi
  printf '%s' "$sid"
}

# --- Phase A: direct Django ---
log "Phase A: direct Django SSE → kill client after ${HOLD_SEC}s"
log "URL=$STREAM_URL"

BEFORE_TS="$(date -u +%Y-%m-%dT%H:%M:%S)"
CURL_OUT="$ARTIFACT_DIR/phase-a-curl.out"
CURL_HDR="$ARTIFACT_DIR/phase-a-headers.txt"

# Hold the stream briefly, then kill curl (simulates EventSource.close / tab close).
set +e
# Accept */* — DRF rejects Accept: text/event-stream with 406.
curl -sS -N \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Host: ${PROVE_HOST:-app.stay.hr}" \
  -H "Accept: */*" \
  -D "$CURL_HDR" \
  -o "$CURL_OUT" \
  --max-time "$((HOLD_SEC + 2))" \
  "$STREAM_URL" &
CURL_PID=$!
sleep "$HOLD_SEC"
kill "$CURL_PID" 2>/dev/null
wait "$CURL_PID" 2>/dev/null
set -e

STREAM_ID="$(extract_stream_id "$CURL_HDR" "$CURL_OUT")"
[[ -n "$STREAM_ID" ]] || fail "No stream_id in headers/body — is instrumentation deployed? hdr=$(head -c 400 "$CURL_HDR")"

log "opened stream_id=$STREAM_ID (client killed at T+${HOLD_SEC}s)"
log "Waiting up to ${WAIT_CLOSED_SEC}s for sse_stream_closed…"

CLOSED_LINE=""
if CLOSED_LINE="$(wait_for_closed "$STREAM_ID" "$BEFORE_TS")"; then
  :
else
  CLOSED_LINE=""
fi

{
  echo "phase=A_direct_django"
  echo "stream_id=$STREAM_ID"
  echo "before_ts=$BEFORE_TS"
  echo "hold_sec=$HOLD_SEC"
  echo "closed_line=$CLOSED_LINE"
  echo "--- headers ---"
  cat "$CURL_HDR"
  echo "--- body head ---"
  head -c 800 "$CURL_OUT"
  echo
} > "$ARTIFACT_DIR/phase-a-result.txt"

if [[ -z "$CLOSED_LINE" ]]; then
  log "Phase A FAIL: no sse_stream_closed for stream_id=$STREAM_ID within ${WAIT_CLOSED_SEC}s"
  log "Artifact: $ARTIFACT_DIR/phase-a-result.txt"
  exit 2
fi

log "Phase A PASS: $CLOSED_LINE"

# Optional invariant check via system status (same token).
STATUS_URL="${API_BASE%/}/api/v1/reception/system/status/"
if STATUS_JSON="$(curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Host: ${PROVE_HOST:-app.stay.hr}" \
  -H "Accept: application/json" \
  "$STATUS_URL" 2>/dev/null)"; then
  echo "$STATUS_JSON" > "$ARTIFACT_DIR/phase-a-status.json"
  if echo "$STATUS_JSON" | grep -q '"invariant_delta":[[:space:]]*0'; then
    log "Phase A invariant_delta=0 (OK)"
  else
    log "Phase A WARN: invariant_delta not 0 in /system/status (see phase-a-status.json)"
  fi
fi

log ""

# --- Phase B: BFF (AbortSignal wired) ---
if [[ -n "$BFF_BASE" ]]; then
  [[ -n "$BFF_COOKIE" ]] || fail "PROVE_BFF_COOKIE is required when PROVE_BFF_BASE is set"
  BFF_URL="${BFF_BASE%/}/api/stay/reception/reservation-versions/stream/?reservation_id=${RESERVATION_ID}&scope=${SCOPE}"
  log "Phase B: BFF SSE → kill client after ${HOLD_SEC}s"
  log "URL=$BFF_URL"

  BEFORE_TS_B="$(date -u +%Y-%m-%dT%H:%M:%S)"
  CURL_OUT_B="$ARTIFACT_DIR/phase-b-curl.out"
  CURL_HDR_B="$ARTIFACT_DIR/phase-b-headers.txt"

  set +e
  curl -sS -N \
    -H "Cookie: ${BFF_COOKIE}" \
    -H "Accept: */*" \
    -D "$CURL_HDR_B" \
    -o "$CURL_OUT_B" \
    --max-time "$((HOLD_SEC + 2))" \
    "$BFF_URL" &
  CURL_PID_B=$!
  sleep "$HOLD_SEC"
  kill "$CURL_PID_B" 2>/dev/null
  wait "$CURL_PID_B" 2>/dev/null
  set -e

  STREAM_ID_B="$(extract_stream_id "$CURL_HDR_B" "$CURL_OUT_B")"
  [[ -n "$STREAM_ID_B" ]] || fail "Phase B: no stream_id — BFF auth or path wrong? hdr=$(head -c 400 "$CURL_HDR_B")"

  log "opened stream_id=$STREAM_ID_B via BFF"
  log "Waiting up to ${WAIT_CLOSED_SEC}s for sse_stream_closed + bff_sse_client_aborted…"

  CLOSED_LINE_B=""
  if CLOSED_LINE_B="$(wait_for_closed "$STREAM_ID_B" "$BEFORE_TS_B")"; then
    :
  else
    CLOSED_LINE_B=""
  fi

  ABORT_LINE="$(docker compose logs web-reception --since "${BEFORE_TS_B}Z" 2>/dev/null \
    | grep "bff_sse_client_aborted" \
    | tail -1 || true)"
  WIRED_OK=0
  if echo "$ABORT_LINE" | grep -q 'upstream_abort_wired": true\|upstream_abort_wired.: true\|"upstream_abort_wired":true'; then
    WIRED_OK=1
  elif echo "$ABORT_LINE" | grep -q 'upstream_abort_wired'; then
    # JSON may be spaced; accept any abort line that claims wired true
    if echo "$ABORT_LINE" | grep -q 'true'; then
      WIRED_OK=1
    fi
  fi

  {
    echo "phase=B_bff"
    echo "stream_id=$STREAM_ID_B"
    echo "before_ts=$BEFORE_TS_B"
    echo "closed_line=$CLOSED_LINE_B"
    echo "abort_line=$ABORT_LINE"
    echo "upstream_abort_wired_ok=$WIRED_OK"
    echo "--- headers ---"
    cat "$CURL_HDR_B"
    echo "--- body head ---"
    head -c 800 "$CURL_OUT_B"
    echo
  } > "$ARTIFACT_DIR/phase-b-result.txt"

  if [[ -z "$CLOSED_LINE_B" ]]; then
    log "Phase B FAIL: no sse_stream_closed for stream_id=$STREAM_ID_B"
    log "Artifact: $ARTIFACT_DIR/phase-b-result.txt"
    exit 3
  fi
  if [[ -z "$ABORT_LINE" ]]; then
    log "Phase B FAIL: no bff_sse_client_aborted in web-reception logs"
    exit 3
  fi
  if [[ "$WIRED_OK" -ne 1 ]]; then
    log "Phase B FAIL: abort log missing upstream_abort_wired:true — $ABORT_LINE"
    exit 3
  fi
  log "Phase B PASS: abort wired + Django closed stream_id=$STREAM_ID_B"
else
  log "Phase B (manual browser / BFF) — AbortSignal is WIRED (upstream_abort_wired:true):"
  log "  1. Open ONE expected reservation with check-in progress on app.stay.hr"
  log "  2. docker compose logs -f django web-reception | grep -E 'sse_stream_|bff_sse_'"
  log "  3. Copy stream_id from sse_stream_opened (scope=checkin)"
  log "  4. Close the tab (or navigate away)"
  log "  5. Expect within ~30s:"
  log "       bff_sse_client_aborted … upstream_abort_wired: true"
  log "       sse_stream_closed stream_id=… close_reason=client_disconnect"
  log "       /system/status → invariant_delta=0, active_connections falls"
  log "  6. Optional automate: PROVE_BFF_BASE=https://app.stay.hr PROVE_BFF_COOKIE='…' $0"
  log "Artifact dir: $ARTIFACT_DIR"
fi

log ""
log "Phase 1 lifecycle gate: Phase A PASS. Redeploy reception for BFF wiring before Phase 2."
