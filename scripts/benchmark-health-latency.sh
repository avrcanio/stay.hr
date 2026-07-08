#!/usr/bin/env bash
# Health latency benchmark — run before and after Gunicorn/SSE changes.
#
# Usage:
#   ./scripts/benchmark-health-latency.sh | tee -a data/ops/health-latency-benchmark.txt
#
# CI light mode:
#   BENCHMARK_LIGHT=1 OPS_CI_ARTIFACT_DIR=./ci-artifacts ./scripts/benchmark-health-latency.sh
#
# Env:
#   LOAD_TEST_API_BASE   — default http://127.0.0.1:8000
#   BENCHMARK_SAMPLES    — default 200 (50 when BENCHMARK_LIGHT=1)
#   BENCHMARK_LABEL      — optional label (e.g. "before-8-workers")
#   BENCHMARK_LIGHT      — 1 for reduced CI smoke (fewer samples)
#   OPS_CI_ARTIFACT_DIR  — when set, tee full output to timestamped artifact file
#   STAY_GIT_SHA         — optional; auto-detected from git when available

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=ops-common.sh
source "$ROOT_DIR/scripts/ops-common.sh"

API_BASE="${LOAD_TEST_API_BASE:-http://127.0.0.1:8000}"
SAMPLES="${BENCHMARK_SAMPLES:-200}"
LABEL="${BENCHMARK_LABEL:-}"
HEALTH_URL="${API_BASE%/}/api/v1/reception/health/"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if is_truthy "${BENCHMARK_LIGHT:-}"; then
  SAMPLES="${BENCHMARK_SAMPLES:-50}"
  LABEL="${BENCHMARK_LABEL:-ci-light}"
fi

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing: $1" >&2
    exit 1
  }
}

require_cmd curl
require_cmd python3

if [[ -n "${OPS_CI_ARTIFACT_DIR:-}" ]]; then
  setup_ci_artifact_tee "benchmark-health"
fi

echo "Health latency benchmark"
benchmark_header "$LABEL" "$ROOT_DIR"
echo "  api_base=${API_BASE}"
echo "  samples=${SAMPLES}"
is_truthy "${BENCHMARK_LIGHT:-}" && echo "  mode=light"
echo

for _ in $(seq 1 "$SAMPLES"); do
  curl -sS --max-time 10 -o /dev/null -w '%{time_total}\n' "$HEALTH_URL" >>"$TMP" || echo "10.000" >>"$TMP"
done

python3 - "$TMP" <<'PY'
import sys
from pathlib import Path

values = []
for line in Path(sys.argv[1]).read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        values.append(float(line) * 1000.0)
    except ValueError:
        continue

if not values:
    print("No samples collected.")
    raise SystemExit(1)

values.sort()
n = len(values)

def pct(p: float) -> float:
    idx = max(0, min(n - 1, int(n * p) - 1))
    return values[idx]

print(f"samples={n}")
print(f"p50_ms={pct(0.50):.1f}")
print(f"p95_ms={pct(0.95):.1f}")
print(f"p99_ms={pct(0.99):.1f}")
print(f"min_ms={values[0]:.1f}")
print(f"max_ms={values[-1]:.1f}")
PY
