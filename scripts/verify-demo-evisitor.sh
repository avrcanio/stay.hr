#!/usr/bin/env bash
# Post-deploy demo eVisitor bootstrap + connectivity check.
#
# Runs only when DEMO_EVISITOR_USERNAME is set in the django container env
# (typically via .env). Skips silently otherwise.
#
# Usage (called from deploy.sh):
#   ./scripts/verify-demo-evisitor.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SMOKE_CMD=(
  python manage.py smoke_evisitor
  --tenant-slug demo
  --property-slug demo
  --login-only
  --json
)

log() { printf '==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

format_smoke_cmd() {
  docker compose exec -T django python -c \
    'import shlex, sys; print(shlex.join(sys.argv[1:]))' \
    -- "${SMOKE_CMD[@]}"
}

print_failure_header() {
  printf '\nDemo eVisitor verification failed\n\nCommand:\n' >&2
  format_smoke_cmd >&2
  printf '\n' >&2
}

if ! docker compose exec -T django python -c \
  "import os, sys; sys.exit(0 if os.getenv('DEMO_EVISITOR_USERNAME', '').strip() else 1)" \
  >/dev/null 2>&1; then
  log "Demo eVisitor: skipped (DEMO_EVISITOR_USERNAME not set)"
  exit 0
fi

log "Demo eVisitor: seed_evisitor_config"
docker compose exec -T django python manage.py seed_evisitor_config

log "Demo eVisitor: smoke_evisitor --login-only --json"
smoke_stderr="$(mktemp)"
smoke_json="$(mktemp)"
validation_stderr="$(mktemp)"
trap 'rm -f "$smoke_stderr" "$smoke_json" "$validation_stderr"' EXIT

if ! docker compose exec -T django "${SMOKE_CMD[@]}" >"$smoke_json" 2>"$smoke_stderr"; then
  print_failure_header
  if [[ -s "$smoke_stderr" ]]; then
    printf 'stderr:\n' >&2
    cat "$smoke_stderr" >&2
  fi
  if [[ -s "$smoke_json" ]]; then
    printf 'stdout (JSON):\n' >&2
    cat "$smoke_json" >&2
    printf '\n' >&2
  fi
  exit 1
fi

if ! docker compose exec -T django python -c "
import json
import sys

with open('/dev/stdin', encoding='utf-8') as fh:
    payload = json.load(fh)

errors = []
if payload.get('status') != 'ok':
    errors.append(f\"status={payload.get('status')!r}, expected 'ok'\")
if payload.get('exit_code') != 0:
    errors.append(f\"exit_code={payload.get('exit_code')!r}, expected 0\")
if not payload.get('steps', {}).get('config'):
    errors.append(f\"steps.config={payload.get('steps', {}).get('config')!r}, expected True\")
if not payload.get('steps', {}).get('login'):
    errors.append(f\"steps.login={payload.get('steps', {}).get('login')!r}, expected True\")

if errors:
    print('Validation errors:', file=sys.stderr)
    for err in errors:
        print(f'- {err}', file=sys.stderr)
    print('Full payload:', file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    sys.exit(1)
" <"$smoke_json" 2>"$validation_stderr"; then
  print_failure_header
  cat "$validation_stderr" >&2
  exit 1
fi

log "Demo eVisitor: smoke passed"
