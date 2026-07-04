#!/usr/bin/env bash
# Create stay_platform_test_db on shared PostGIS if missing (idempotent).
#
# Usage:
#   ./scripts/ensure-test-db.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TEST_DB_NAME="${TEST_DB_NAME:-stay_platform_test_db}"
DB_USER="${DB_USER:-stay}"
POSTGIS_CONTAINER="${POSTGIS_CONTAINER:-postgis}"

log() { printf '==> %s\n' "$*"; }

if ! docker ps --format '{{.Names}}' | grep -qx "$POSTGIS_CONTAINER"; then
  printf 'ERROR: PostGIS container %q is not running.\n' "$POSTGIS_CONTAINER" >&2
  exit 1
fi

exists="$(docker exec "$POSTGIS_CONTAINER" psql -U postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname = '${TEST_DB_NAME}'" | tr -d '[:space:]')"

if [[ "$exists" == "1" ]]; then
  log "Test database ${TEST_DB_NAME} already exists"
else
  log "Creating test database ${TEST_DB_NAME} (owner ${DB_USER})"
  docker exec "$POSTGIS_CONTAINER" psql -U postgres -v ON_ERROR_STOP=1 -c \
    "CREATE DATABASE \"${TEST_DB_NAME}\" OWNER \"${DB_USER}\";"
fi

log "Ensuring postgis extension on ${TEST_DB_NAME}"
docker exec "$POSTGIS_CONTAINER" psql -U postgres -d "$TEST_DB_NAME" -v ON_ERROR_STOP=1 -c \
  "CREATE EXTENSION IF NOT EXISTS postgis;"

log "Test database ready: ${TEST_DB_NAME}"
