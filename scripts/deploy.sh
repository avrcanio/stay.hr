#!/usr/bin/env bash
# Deploy stay.hr: rebuild + up when migrations are pending or migration files
# changed since the image was built; otherwise restart only.
#
# Usage:
#   ./scripts/deploy.sh
#   ./scripts/deploy.sh --help
#
# Requires: docker compose stack in repo root (stay.hr).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

usage() {
  sed -n '2,9p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage 0 ;;
    *) echo "Unknown option: $arg" >&2; usage 1 ;;
  esac
done

log() { printf '==> %s\n' "$*"; }

django_image_id() {
  docker compose images -q django 2>/dev/null | head -n1
}

migration_files_newer_than_image() {
  local image_id created_ts file_ts
  image_id="$(django_image_id)"
  [[ -n "$image_id" ]] || return 0

  created_ts="$(docker inspect -f '{{.Created}}' "$image_id" 2>/dev/null || true)"
  [[ -n "$created_ts" ]] || return 0

  while IFS= read -r -d '' f; do
    file_ts="$(stat -c '%Y' "$f" 2>/dev/null || stat -f '%m' "$f")"
    image_ts="$(date -d "$created_ts" +%s 2>/dev/null || date -j -f '%Y-%m-%dT%H:%M:%S' "${created_ts%%.*}" +%s 2>/dev/null || echo 0)"
    if [[ "$file_ts" -gt "$image_ts" ]]; then
      return 0
    fi
  done < <(find backend/apps -path '*/migrations/*.py' ! -name '__init__.py' -print0 2>/dev/null)

  return 1
}

pending_migrations_in_db() {
  if docker compose ps --status running django -q 2>/dev/null | grep -q .; then
    ! docker compose exec -T django python manage.py migrate --check >/dev/null 2>&1
    return
  fi

  log "django not running; starting temporarily for migration check..."
  docker compose up -d django
  sleep 2
  ! docker compose exec -T django python manage.py migrate --check >/dev/null 2>&1
}

needs_rebuild=false
reason=""

if migration_files_newer_than_image; then
  needs_rebuild=true
  reason="migration files changed since last image build"
elif pending_migrations_in_db; then
  needs_rebuild=true
  reason="unapplied database migrations"
fi

if $needs_rebuild; then
  log "Rebuild required ($reason)"
  docker compose build
  docker compose up -d
else
  log "No migration work needed; restarting services"
  docker compose restart
fi

log "Running Django system check..."
docker compose exec -T django python manage.py check

log "Done."
docker compose ps
