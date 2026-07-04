#!/usr/bin/env bash
# End-to-end demo eVisitor bootstrap for onboarding/QA.
#
# Default: seed tenant + config + guest, then login + dry-run payload validation.
# Does not modify deploy gate (verify-demo-evisitor.sh).
#
# Usage:
#   ./scripts/bootstrap-demo-evisitor.sh              # login + dry-run (default)
#   ./scripts/bootstrap-demo-evisitor.sh --login-only # steps 1–5 only
#   ./scripts/bootstrap-demo-evisitor.sh --submit     # includes real HTZ submit (opt-in)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TENANT_SLUG="demo"
PROPERTY_SLUG="demo"
LOGIN_ONLY=false
SUBMIT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --login-only)
      LOGIN_ONLY=true
      ;;
    --submit)
      SUBMIT=true
      ;;
    -h|--help)
      sed -n '2,10p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      exit 1
      ;;
  esac
  shift
done

log() { printf '==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

print_failure_header() {
  local step="$1"
  local cmd="$2"
  printf '\nDemo eVisitor bootstrap failed at: %s\n\nCommand:\n%s\n\n' "$step" "$cmd" >&2
}

django_exec() {
  docker compose exec -T django "$@"
}

has_demo_evisitor_env() {
  django_exec python -c \
    "import os, sys; sys.exit(0 if os.getenv('DEMO_EVISITOR_USERNAME', '').strip() else 1)" \
    >/dev/null 2>&1
}

validate_smoke_json() {
  local label="$1"
  local json_file="$2"
  local mode="$3"
  local validation_stderr
  validation_stderr="$(mktemp)"
  trap 'rm -f "$validation_stderr"' RETURN

  if ! django_exec python -c "
import json
import sys

mode = sys.argv[1]
with open('/dev/stdin', encoding='utf-8') as fh:
    payload = json.load(fh)

errors = []
if payload.get('status') != 'ok':
    errors.append(f\"status={payload.get('status')!r}, expected 'ok'\")
if payload.get('exit_code') != 0:
    errors.append(f\"exit_code={payload.get('exit_code')!r}, expected 0\")
steps = payload.get('steps', {})
if not steps.get('config'):
    errors.append(f\"steps.config={steps.get('config')!r}, expected True\")
if mode in ('login', 'dry-run', 'submit') and not steps.get('login'):
    errors.append(f\"steps.login={steps.get('login')!r}, expected True\")
if mode in ('dry-run', 'submit') and not steps.get('payload'):
    errors.append(f\"steps.payload={steps.get('payload')!r}, expected True\")

if errors:
    print('Validation errors:', file=sys.stderr)
    for err in errors:
        print(f'- {err}', file=sys.stderr)
    print('Full payload:', file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    sys.exit(1)
" "$mode" <"$json_file" 2>"$validation_stderr"; then
    print_failure_header "$label" "smoke_evisitor validation"
    cat "$validation_stderr" >&2
    exit 1
  fi
}

run_smoke() {
  local label="$1"
  shift
  local smoke_cmd=(python manage.py smoke_evisitor --tenant-slug "$TENANT_SLUG" --property-slug "$PROPERTY_SLUG" --json "$@")
  local smoke_stderr smoke_json
  smoke_stderr="$(mktemp)"
  smoke_json="$(mktemp)"

  local cmd_display
  cmd_display="$(django_exec python -c 'import shlex, sys; print(shlex.join(sys.argv[1:]))' -- "${smoke_cmd[@]}")"

  if ! django_exec "${smoke_cmd[@]}" >"$smoke_json" 2>"$smoke_stderr"; then
    print_failure_header "$label" "$cmd_display"
    if [[ -s "$smoke_stderr" ]]; then
      printf 'stderr:\n' >&2
      cat "$smoke_stderr" >&2
    fi
    if [[ -s "$smoke_json" ]]; then
      printf 'stdout (JSON):\n' >&2
      cat "$smoke_json" >&2
      printf '\n' >&2
    fi
    rm -f "$smoke_stderr" "$smoke_json"
    exit 1
  fi

  rm -f "$smoke_stderr"
  printf '%s' "$smoke_json"
}

log "Demo eVisitor bootstrap: seed_demo_tenant"
django_exec python manage.py seed_demo_tenant

EVISITOR_CONFIGURED=false
if has_demo_evisitor_env; then
  log "Demo eVisitor bootstrap: seed_evisitor_config"
  django_exec python manage.py seed_evisitor_config
  EVISITOR_CONFIGURED=true
else
  log "Demo eVisitor bootstrap: seed_evisitor_config skipped (DEMO_EVISITOR_USERNAME not set)"
fi

log "Demo eVisitor bootstrap: seed_demo_guest"
guest_json="$(mktemp)"
if ! django_exec python manage.py seed_demo_guest --json >"$guest_json"; then
  print_failure_header "seed_demo_guest" "python manage.py seed_demo_guest --json"
  exit 1
fi

GUEST_ID="$(django_exec python -c "
import json, sys
with open('/dev/stdin', encoding='utf-8') as fh:
    print(json.load(fh)['guest_id'])
" <"$guest_json")"
rm -f "$guest_json"
log "Demo eVisitor bootstrap: guest_id=$GUEST_ID"

if ! $EVISITOR_CONFIGURED; then
  log "Demo eVisitor bootstrap: smoke steps skipped (no DEMO_EVISITOR_* config)"
  log "Demo eVisitor bootstrap: done (tenant + guest only)"
  exit 0
fi

log "Demo eVisitor bootstrap: smoke_evisitor --list-config"
list_json="$(run_smoke "list-config" --list-config)"
validate_smoke_json "list-config" "$list_json" config
rm -f "$list_json"

log "Demo eVisitor bootstrap: smoke_evisitor --login-only"
login_json="$(run_smoke "login-only" --login-only)"
validate_smoke_json "login-only" "$login_json" login
rm -f "$login_json"

if $LOGIN_ONLY; then
  log "Demo eVisitor bootstrap: done (--login-only)"
  exit 0
fi

log "Demo eVisitor bootstrap: smoke_evisitor --guest-id $GUEST_ID --dry-run"
dry_run_json="$(run_smoke "dry-run" --guest-id "$GUEST_ID" --dry-run)"
validate_smoke_json "dry-run" "$dry_run_json" dry-run
rm -f "$dry_run_json"

if $SUBMIT; then
  log "Demo eVisitor bootstrap: smoke_evisitor --guest-id $GUEST_ID (submit)"
  submit_json="$(run_smoke "submit" --guest-id "$GUEST_ID")"
  validate_smoke_json "submit" "$submit_json" submit
  rm -f "$submit_json"
fi

log "Demo eVisitor bootstrap: done"
