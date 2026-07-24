#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# Prefer env file (chmod 600) over ephemeral /tmp creds.
if [[ -f /etc/stay/sse-observe.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/stay/sse-observe.env
  set +a
elif [[ -f /tmp/load-test-creds.txt ]]; then
  export RECEPTION_API_TOKEN="$(head -1 /tmp/load-test-creds.txt | tr -d '\r\n')"
fi
export LOAD_TEST_API_BASE="${LOAD_TEST_API_BASE:-https://api.stay.hr}"
export LOAD_TEST_RESERVATION_ID="${LOAD_TEST_RESERVATION_ID:-1036}"
exec "$ROOT/scripts/observe-sse-lifecycle.sh" --append-log "$@"
