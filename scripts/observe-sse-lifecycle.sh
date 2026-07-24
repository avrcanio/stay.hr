#!/usr/bin/env bash
# SSE lifecycle observation — permanent instrumentation health check (ADR 0005).
#
# Captures:
#   - docker log signals (opened/closed/breach/WORKER TIMEOUT)
#   - GET /system/status SSE invariant fields (per hit worker)
#   - optional rise/fall canary (open one stream, kill client, expect close)
#
# Not a calendar gate for Phase 2a: if leak/saturation returns → stop and analyze;
# if not → continue Redis/Uvicorn work with this instrumentation still on.
#
# Writes:
#   data/ops/sse-lifecycle-observation/YYYY-MM-DD.jsonl  (one sample per run)
#   data/ops/sse-lifecycle-observation/latest.json
#   docs/operations/sse-lifecycle-observation-log.md     (append when --append-log)
#
# Usage:
#   ./scripts/observe-sse-lifecycle.sh
#   ./scripts/observe-sse-lifecycle.sh --canary --append-log
#   OBSERVE_SINCE=24h ./scripts/observe-sse-lifecycle.sh
#
# Env:
#   RECEPTION_API_TOKEN          required for /system/status (+ canary)
#   LOAD_TEST_API_BASE           default https://api.stay.hr
#   LOAD_TEST_RESERVATION_ID     required for --canary
#   OBSERVE_SINCE                docker compose logs --since window (optional)
#   OBSERVE_HOST                 Host header for API (default app.stay.hr)
#   OBSERVE_SKIP_DOCKER_SIGNALS  set 1 to skip collect-docker-gunicorn-signals.sh
#
# Host cron (optional, with daily ops):
#   50 9 * * * cd /opt/stacks/stay.hr && ./scripts/observe-sse-lifecycle.sh --append-log

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/ops-common.sh
source "${ROOT}/scripts/ops-common.sh"

APPEND_LOG=0
RUN_CANARY=0
for arg in "$@"; do
  case "$arg" in
    --append-log) APPEND_LOG=1 ;;
    --canary) RUN_CANARY=1 ;;
    -h|--help)
      sed -n '2,32p' "$0"
      exit 0
      ;;
  esac
done

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

TOKEN="${RECEPTION_API_TOKEN:-}"
API_BASE="${LOAD_TEST_API_BASE:-https://api.stay.hr}"
STATUS_URL="${API_BASE%/}/api/v1/reception/system/status/"
HOST_HDR="${OBSERVE_HOST:-app.stay.hr}"
RESERVATION_ID="${LOAD_TEST_RESERVATION_ID:-}"
OUT_DIR="${ROOT}/data/ops/sse-lifecycle-observation"
DAY="$(date +%F)"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_SHA="$(resolve_git_sha "$ROOT")"
LOG_MD="${ROOT}/docs/operations/sse-lifecycle-observation-log.md"
JSONL="${OUT_DIR}/${DAY}.jsonl"
LATEST="${OUT_DIR}/latest.json"

mkdir -p "$OUT_DIR"

log() { printf '[observe-sse] %s\n' "$*"; }
fail() { log "FAIL: $*"; exit 1; }

[[ -n "$TOKEN" ]] || fail "RECEPTION_API_TOKEN is required"

# --- Status + optional canary first; docker log totals collected after ---
# (so canary open/close is included in opened/closed counts)

STATUS_FILE="${OUT_DIR}/status-${DAY}-$(date -u +%H%M%S).json"
# -L: Traefik may 308 redirect; Host header only for direct docker targets.
CURL_HOST_ARGS=()
if [[ "$API_BASE" == http://stay_django* || "$API_BASE" == http://127.0.0.1* || "$API_BASE" == http://localhost* ]]; then
  CURL_HOST_ARGS=(-H "Host: ${HOST_HDR}")
fi
curl -sS -L --max-time 15 \
  -H "Authorization: Bearer ${TOKEN}" \
  "${CURL_HOST_ARGS[@]}" \
  -H "Accept: application/json" \
  "$STATUS_URL" >"$STATUS_FILE" || printf '{}\n' >"$STATUS_FILE"

eval "$(python3 - "$STATUS_FILE" <<'PY'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    print('INV_DELTA=')
    print('INV_OK=')
    print('ACTIVE=')
    print('ACTIVE_STREAMS=')
    print('OPENED_TOTAL=')
    print('CLOSED_TOTAL=')
    raise SystemExit(0)
sse = data.get("sse") or {}
def emit(k, v):
    print(f"{k}={v if v is not None else ''}")
emit("INV_DELTA", sse.get("invariant_delta"))
emit("INV_OK", sse.get("invariant_ok"))
emit("ACTIVE", sse.get("active_connections"))
emit("ACTIVE_STREAMS", sse.get("active_stream_count"))
emit("OPENED_TOTAL", sse.get("connections_opened_total"))
emit("CLOSED_TOTAL", sse.get("connections_closed_total"))
PY
)"

# --- Optional rise/fall canary ---
# Heartbeat probe is 25s; client kill typically closes within ~2 heartbeats (~50s).
CANARY_RESULT="skipped"
CANARY_STREAM_ID=""
if [[ "$RUN_CANARY" -eq 1 ]]; then
  [[ -n "$RESERVATION_ID" ]] || fail "LOAD_TEST_RESERVATION_ID required for --canary"
  HOLD_SEC="${OBSERVE_CANARY_HOLD_SEC:-5}"
  WAIT_SEC="${OBSERVE_CANARY_WAIT_SEC:-70}"
  SCOPE="${OBSERVE_CANARY_SCOPE:-checkin}"
  CANARY_API_BASE="${OBSERVE_CANARY_API_BASE:-$API_BASE}"
  STREAM_URL="${CANARY_API_BASE%/}/api/v1/reception/reservation-versions/stream/?reservation_id=${RESERVATION_ID}&scope=${SCOPE}"
  BEFORE_TS="$(date -u +%Y-%m-%dT%H:%M:%S)"
  CURL_OUT="${OUT_DIR}/canary-body.txt"
  CURL_HDR="${OUT_DIR}/canary-headers.txt"
  CANARY_HOST_ARGS=()
  CANARY_CURL=(curl -sS -L -N)
  if [[ "$CANARY_API_BASE" == http://stay_django* || "$CANARY_API_BASE" == http://127.0.0.1* || "$CANARY_API_BASE" == http://localhost* ]]; then
    CANARY_HOST_ARGS=(-H "Host: ${HOST_HDR}")
    CANARY_CURL=(curl -sS -N)
  fi
  log "Canary: open SSE ${HOLD_SEC}s then kill client (scope=${SCOPE} base=${CANARY_API_BASE})"
  set +e
  "${CANARY_CURL[@]}" \
    -H "Authorization: Bearer ${TOKEN}" \
    "${CANARY_HOST_ARGS[@]}" \
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
  CANARY_STREAM_ID="$(awk -F': ' 'tolower($1)=="x-sse-stream-id"{print $2}' "$CURL_HDR" | tr -d '\r' | tail -1 || true)"
  if [[ -z "$CANARY_STREAM_ID" ]]; then
    CANARY_STREAM_ID="$(docker compose logs django --since "${BEFORE_TS}Z" 2>/dev/null \
      | grep "sse_stream_opened" | grep "reservation_id=${RESERVATION_ID}" | grep "scope=${SCOPE}" \
      | tail -1 | grep -oE 'stream_id=[a-f0-9]+' | head -1 | cut -d= -f2 || true)"
  fi
  if [[ -z "$CANARY_STREAM_ID" ]]; then
    CANARY_STREAM_ID="$(grep -oE '"stream_id":"[a-f0-9]+"' "$CURL_OUT" 2>/dev/null | head -1 | sed 's/.*"stream_id":"//;s/"$//' || true)"
  fi
  CLOSED_LINE=""
  if [[ -n "$CANARY_STREAM_ID" ]]; then
    for _ in $(seq 1 "$WAIT_SEC"); do
      CLOSED_LINE="$(docker compose logs django --since "${BEFORE_TS}Z" 2>/dev/null \
        | grep "sse_stream_closed stream_id=${CANARY_STREAM_ID}" | tail -1 || true)"
      if [[ -n "$CLOSED_LINE" ]]; then
        break
      fi
      sleep 1
    done
  fi
  if [[ -n "$CANARY_STREAM_ID" && -n "$CLOSED_LINE" ]]; then
    CANARY_RESULT="pass"
  else
    CANARY_RESULT="fail"
  fi
  log "Canary stream_id=${CANARY_STREAM_ID:-none} result=${CANARY_RESULT}"
fi

# --- Docker log signals (after canary so totals include open/close) ---
if ! is_truthy "${OBSERVE_SKIP_DOCKER_SIGNALS:-0}"; then
  "${ROOT}/scripts/collect-docker-gunicorn-signals.sh" >/dev/null
fi

DOCKER_SIGNALS="${ROOT}/data/media/ops/daily_ops_report/docker_signals.json"
OPENED=0
CLOSED=0
BREACH=0
WORKER_TIMEOUT=0
if [[ -f "$DOCKER_SIGNALS" ]]; then
  read -r OPENED CLOSED BREACH WORKER_TIMEOUT < <(
    python3 - "$DOCKER_SIGNALS" <<'PY'
import json, sys
p = json.loads(open(sys.argv[1], encoding="utf-8").read())
m = p.get("metrics") or {}
print(
    int(m.get("sse_stream_opened", 0)),
    int(m.get("sse_stream_closed", 0)),
    int(m.get("sse_invariant_breach", 0)),
    int(m.get("worker_timeout_count", 0)),
)
PY
  )
fi

SINCE_ARGS=()
if [[ -n "${OBSERVE_SINCE:-}" ]]; then
  SINCE_ARGS=(--since "$OBSERVE_SINCE")
fi
count_log() {
  local pattern="$1"
  docker compose logs django "${SINCE_ARGS[@]}" 2>/dev/null | rg -c "$pattern" || true
}
RECENT_BREACH="$(count_log 'sse_invariant_breach')"
RECENT_BREACH="${RECENT_BREACH:-0}"
RECENT_OPENED="$(count_log 'sse_stream_opened')"
RECENT_OPENED="${RECENT_OPENED:-0}"
RECENT_CLOSED="$(count_log 'sse_stream_closed')"
RECENT_CLOSED="${RECENT_CLOSED:-0}"

# Refresh /system/status after canary (idle worker should show delta=0).
curl -sS -L --max-time 15 \
  -H "Authorization: Bearer ${TOKEN}" \
  "${CURL_HOST_ARGS[@]}" \
  -H "Accept: application/json" \
  "$STATUS_URL" >"$STATUS_FILE" || true
eval "$(python3 - "$STATUS_FILE" <<'PY'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    raise SystemExit(0)
sse = data.get("sse") or {}
def emit(k, v):
    print(f"{k}={v if v is not None else ''}")
emit("INV_DELTA", sse.get("invariant_delta"))
emit("INV_OK", sse.get("invariant_ok"))
emit("ACTIVE", sse.get("active_connections"))
emit("ACTIVE_STREAMS", sse.get("active_stream_count"))
emit("OPENED_TOTAL", sse.get("connections_opened_total"))
emit("CLOSED_TOTAL", sse.get("connections_closed_total"))
PY
)"

# --- Verdict ---
NOTES=()
CHECKS_FAIL=0

if [[ "$BREACH" != "0" || "$RECENT_BREACH" != "0" ]]; then
  CHECKS_FAIL=1
  NOTES+=("sse_invariant_breach present (docker=${BREACH} recent=${RECENT_BREACH})")
fi
if [[ "$WORKER_TIMEOUT" != "0" ]]; then
  CHECKS_FAIL=1
  NOTES+=("WORKER TIMEOUT count=${WORKER_TIMEOUT}")
fi
if [[ -n "${INV_DELTA:-}" && "$INV_DELTA" != "0" ]]; then
  CHECKS_FAIL=1
  NOTES+=("invariant_delta=${INV_DELTA}")
fi
if [[ -n "${INV_OK:-}" ]]; then
  case "$(printf '%s' "$INV_OK" | tr '[:upper:]' '[:lower:]')" in
    true|1|yes) ;;
    *)
      CHECKS_FAIL=1
      NOTES+=("invariant_ok=${INV_OK}")
      ;;
  esac
fi
if [[ "$CANARY_RESULT" == "fail" ]]; then
  CHECKS_FAIL=1
  NOTES+=("rise/fall canary failed")
fi

OPEN_CLOSE_DELTA=$((OPENED - CLOSED))
if [[ "$OPEN_CLOSE_DELTA" -lt 0 ]]; then
  CHECKS_FAIL=1
  NOTES+=("closed > opened (opened=${OPENED} closed=${CLOSED})")
fi

VERDICT="PASS"
if [[ "$CHECKS_FAIL" -ne 0 ]]; then
  VERDICT="FAIL"
fi

export OBSERVE_TS="$TS" OBSERVE_DAY="$DAY" OBSERVE_GIT_SHA="$GIT_SHA" OBSERVE_VERDICT="$VERDICT"
export OBSERVE_INV_DELTA="${INV_DELTA:-}" OBSERVE_INV_OK="${INV_OK:-}"
export OBSERVE_ACTIVE="${ACTIVE:-}" OBSERVE_ACTIVE_STREAMS="${ACTIVE_STREAMS:-}"
export OBSERVE_OPENED_TOTAL="${OPENED_TOTAL:-}" OBSERVE_CLOSED_TOTAL="${CLOSED_TOTAL:-}"
export OBSERVE_OPENED="$OPENED" OBSERVE_CLOSED="$CLOSED" OBSERVE_OPEN_CLOSE_DELTA="$OPEN_CLOSE_DELTA"
export OBSERVE_BREACH="$BREACH" OBSERVE_RECENT_OPENED="$RECENT_OPENED" OBSERVE_RECENT_CLOSED="$RECENT_CLOSED"
export OBSERVE_RECENT_BREACH="$RECENT_BREACH" OBSERVE_WORKER_TIMEOUT="$WORKER_TIMEOUT"
export OBSERVE_CANARY_RESULT="$CANARY_RESULT" OBSERVE_CANARY_STREAM_ID="$CANARY_STREAM_ID"
export OBSERVE_STATUS_BASENAME
OBSERVE_STATUS_BASENAME="$(basename "$STATUS_FILE")"
NOTES_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${NOTES[@]+"${NOTES[@]}"}")"
export NOTES_JSON

SAMPLE="$(python3 <<'PY'
import json, os

def maybe_int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except ValueError:
        return None

def maybe_bool(v):
    if v is None or v == "":
        return None
    return str(v).lower() in ("true", "1", "yes")

sample = {
    "schema_version": 1,
    "observed_at": os.environ["OBSERVE_TS"],
    "day": os.environ["OBSERVE_DAY"],
    "git_sha": os.environ["OBSERVE_GIT_SHA"],
    "verdict": os.environ["OBSERVE_VERDICT"],
    "checks": {
        "invariant_delta": maybe_int(os.environ.get("OBSERVE_INV_DELTA")),
        "invariant_ok": maybe_bool(os.environ.get("OBSERVE_INV_OK")),
        "active_connections": maybe_int(os.environ.get("OBSERVE_ACTIVE")),
        "active_stream_count": maybe_int(os.environ.get("OBSERVE_ACTIVE_STREAMS")),
        "connections_opened_total": maybe_int(os.environ.get("OBSERVE_OPENED_TOTAL")),
        "connections_closed_total": maybe_int(os.environ.get("OBSERVE_CLOSED_TOTAL")),
        "docker_sse_opened": int(os.environ["OBSERVE_OPENED"]),
        "docker_sse_closed": int(os.environ["OBSERVE_CLOSED"]),
        "docker_open_close_delta": int(os.environ["OBSERVE_OPEN_CLOSE_DELTA"]),
        "docker_sse_invariant_breach": int(os.environ["OBSERVE_BREACH"]),
        "recent_sse_opened": int(os.environ["OBSERVE_RECENT_OPENED"]),
        "recent_sse_closed": int(os.environ["OBSERVE_RECENT_CLOSED"]),
        "recent_sse_invariant_breach": int(os.environ["OBSERVE_RECENT_BREACH"]),
        "worker_timeout_count": int(os.environ["OBSERVE_WORKER_TIMEOUT"]),
        "canary": os.environ["OBSERVE_CANARY_RESULT"],
        "canary_stream_id": os.environ.get("OBSERVE_CANARY_STREAM_ID") or None,
    },
    "notes": json.loads(os.environ.get("NOTES_JSON") or "[]"),
    "status_snapshot": os.environ["OBSERVE_STATUS_BASENAME"],
}
print(json.dumps(sample, indent=2))
PY
)"

printf '%s\n' "$SAMPLE" | tee "$LATEST"
printf '%s\n' "$SAMPLE" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), separators=(",",":")))' >>"$JSONL"

log "verdict=${VERDICT} opened=${OPENED} closed=${CLOSED} open-closed=${OPEN_CLOSE_DELTA} breach=${BREACH} invariant_delta=${INV_DELTA:-?} active=${ACTIVE:-?}"

if [[ "$APPEND_LOG" -eq 1 ]]; then
  if [[ ! -f "$LOG_MD" ]]; then
    cat >"$LOG_MD" <<'EOF'
# SSE lifecycle — observation log

Running log for Phase 1 lifecycle instrumentation (AbortSignal, disconnect, registry, invariant). Phase 1 lifecycle is **closed**; this log is optional ongoing diagnostics, not a Phase 2a lock.

**Window opened:** (set on first run)
**Invariant:** `opened − closed − active = 0` (`invariant_delta`).  
**Healthy (daily):** `invariant_delta == 0`, no `sse_invariant_breach`, no `WORKER TIMEOUT`, `opened ≈ closed + active`, active rises/falls on canary or real tab use.

**Rule (ADR 0005):** instrumentation stays **permanent** through Redis (2a) and Uvicorn (2b). There is **no** calendar “≥3 PASS days” gate that blocks Phase 2a. If leak/saturation returns → stop and analyze; if it does not recur → continue Phase 2a in parallel.

Runbook: [gunicorn-sse-monitoring.md](gunicorn-sse-monitoring.md)  
Collector: `./scripts/observe-sse-lifecycle.sh --canary --append-log`  
Artifacts: `data/ops/sse-lifecycle-observation/`

| Day | Observed (UTC) | Verdict | opened | closed | breach | invariant_delta | canary | Notes |
|-----|----------------|---------|--------|--------|--------|-----------------|--------|-------|

## Status

**Instrumentation:** keep on (registry, invariant, BFF/Django logs, `/system/status`).  
**Phase 2a:** not blocked by this log — blocked only by an **active** unresolved leak/saturation or missing instrumentation.

EOF
  fi
  NOTE_CELL="$(NOTES_JSON="$NOTES_JSON" python3 -c 'import json,os; n=json.loads(os.environ["NOTES_JSON"]); print("; ".join(n) if n else "—")')"
  NOTE_CELL="${NOTE_CELL//|/\/}"
  ROW="$(printf '| %s | %s | **%s** | %s | %s | %s | %s | %s | %s |' \
    "$DAY" "$TS" "$VERDICT" "$OPENED" "$CLOSED" "$BREACH" "${INV_DELTA:-?}" "$CANARY_RESULT" "$NOTE_CELL")"
  # Insert row before ## Status / ## Sign-off (keep table contiguous).
  python3 - "$LOG_MD" "$ROW" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
row = sys.argv[2]
text = path.read_text(encoding="utf-8")
marker = None
for candidate in ("\n## Status\n", "\n## Sign-off\n"):
    if candidate in text:
        marker = candidate
        break
if marker is None:
    path.write_text(text.rstrip() + "\n" + row + "\n", encoding="utf-8")
else:
    before, after = text.split(marker, 1)
    if not before.endswith("\n"):
        before += "\n"
    path.write_text(before + row + "\n" + marker + after, encoding="utf-8")
PY
  log "Appended row to ${LOG_MD}"
fi

if [[ "$VERDICT" != "PASS" ]]; then
  exit 1
fi
exit 0
