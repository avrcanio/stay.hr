#!/usr/bin/env bash
# Experimental: collect Gunicorn docker log signals for the daily ops report.
# Writes JSON to data/media/ops/daily_ops_report/docker_signals.json
#
# Host cron (optional, 5 min before report):
#   55 9 * * * cd /opt/stacks/stay.hr && ./scripts/collect-docker-gunicorn-signals.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/ops-common.sh
source "${ROOT}/scripts/ops-common.sh"

OUTPUT_DIR="${ROOT}/data/media/ops/daily_ops_report"
OUTPUT_FILE="${OUTPUT_DIR}/docker_signals.json"
CONTAINER="${DAILY_OPS_DOCKER_CONTAINER:-stay_django}"

mkdir -p "$OUTPUT_DIR"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "collect-docker-gunicorn-signals: container ${CONTAINER} not running" >&2
  exit 1
fi

LOGS="$(docker logs "$CONTAINER" 2>&1 || true)"

count_pattern() {
  local pattern="$1"
  if command -v rg >/dev/null 2>&1; then
    printf '%s' "$LOGS" | rg -c "$pattern" 2>/dev/null || printf '0'
  else
    printf '%s' "$LOGS" | grep -c "$pattern" 2>/dev/null || printf '0'
  fi
}

WORKER_TIMEOUT_COUNT="$(count_pattern 'WORKER TIMEOUT')"
SSE_OPENED="$(count_pattern 'sse_stream_opened')"
SSE_CLOSED="$(count_pattern 'sse_stream_closed')"
SSE_INVARIANT_BREACH="$(count_pattern 'sse_invariant_breach')"

python3 - <<PY
import json
from pathlib import Path

payload = {
    "generated_at": "$(date -Iseconds)",
    "git_sha": "$(resolve_git_sha "$ROOT")",
    "container": "${CONTAINER}",
    "metrics": {
        "worker_timeout_count": int("${WORKER_TIMEOUT_COUNT}"),
        "sse_stream_opened": int("${SSE_OPENED}"),
        "sse_stream_closed": int("${SSE_CLOSED}"),
        "sse_invariant_breach": int("${SSE_INVARIANT_BREACH}"),
    },
}
Path("${OUTPUT_FILE}").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"wrote {payload['metrics']} -> ${OUTPUT_FILE}")
PY
