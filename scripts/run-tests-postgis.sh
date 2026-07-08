#!/usr/bin/env bash
# Run Django tests against dedicated PostGIS test DB (stay_platform_test_db).
#
# Usage:
#   ./scripts/run-tests-postgis.sh
#   ./scripts/run-tests-postgis.sh apps.tenants.tests.test_seed_demo_guest -v 2
#   ./scripts/run-tests-postgis.sh apps.integrations.tests -v 2   # default (CI smoke)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { printf '==> %s\n' "$*"; }

print_test_summary() {
  local output_file="$1"
  local ran_line failed_line
  ran_line="$(grep -E '^Ran [0-9]+ tests in' "$output_file" | tail -1 || true)"
  failed_line="$(grep -E '^FAILED \(|^OK$' "$output_file" | tail -1 || true)"

  local total=0 failures=0 errors=0 duration="" passed=0

  if [[ "$ran_line" =~ Ran\ ([0-9]+)\ tests\ in\ ([0-9.]+)s ]]; then
    total="${BASH_REMATCH[1]}"
    duration="${BASH_REMATCH[2]}"
  fi

  if [[ "$failed_line" == "OK" ]]; then
    passed=$total
  elif [[ "$failed_line" =~ failures=([0-9]+)(,\ errors=([0-9]+))? ]]; then
    failures="${BASH_REMATCH[1]}"
    errors="${BASH_REMATCH[3]:-0}"
    passed=$((total - failures - errors))
  fi

  if [[ "$total" -eq 0 ]]; then
    return
  fi

  local label="Test"
  if grep -q 'apps\.integrations\.tests' <<<"$*"; then
    label="Integration test"
  fi

  printf '\n%s summary\n\n' "$label"
  printf 'Passed:  %s\n' "$passed"
  printf 'Failed:  %s\n' "$failures"
  printf 'Errors:  %s\n' "$errors"
  printf 'Duration: %ss\n\n' "$duration"
}

"${REPO_ROOT}/scripts/ensure-test-db.sh"

log "Building django image (code is baked into image, not bind-mounted)"
docker compose build django

DEFAULT_LABELS=(
  apps.integrations.tests
)

if [[ $# -eq 0 ]]; then
  set -- "${DEFAULT_LABELS[@]}" -v 2 --keepdb
else
  set -- "$@" --keepdb
fi

log "Running tests: DJANGO_SETTINGS_MODULE=config.settings.test_postgis $*"

output_file="$(mktemp)"
trap 'rm -f "$output_file"' EXIT

set +e
docker compose --profile test-run run --rm \
  -e DJANGO_SETTINGS_MODULE=config.settings.test_postgis \
  -e TEST_DB_NAME=stay_platform_test_db \
  django-run python manage.py test "$@" 2>&1 | tee "$output_file"
test_exit="${PIPESTATUS[0]}"
set -e

print_test_summary "$output_file" "$@"
exit "$test_exit"
