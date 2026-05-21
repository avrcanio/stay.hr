#!/usr/bin/env bash
# Import Booking.com .xls export into stay.hr.
# See docs/development/booking-xls-import.md for modes: skip (default), --fill-empty, --allow-update.
#
# Usage:
#   ./scripts/import_booking_xls.sh "/path/to/Reservation 2026-05-20 to 2026-05-21.xls"
#   ./scripts/import_booking_xls.sh --dry-run "/path/to/export.xls"
#   ./scripts/import_booking_xls.sh --tenant-id 2 --property-slug uzorita "/path/to/export.xls"
#
# Requires: docker compose stack in repo root (stay.hr).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TENANT_ID=2
PROPERTY_SLUG=uzorita
DRY_RUN=""
ALLOW_UPDATE=""
FILL_EMPTY=""
XLS_PATH=""

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --dry-run) DRY_RUN="--dry-run" ;;
    --allow-update) ALLOW_UPDATE="--allow-update" ;;
    --fill-empty) FILL_EMPTY="--fill-empty" ;;
    --tenant-id) TENANT_ID="$2"; shift ;;
    --property-slug) PROPERTY_SLUG="$2"; shift ;;
    -*) echo "Unknown option: $1" >&2; usage 1 ;;
    *)
      if [[ -z "$XLS_PATH" ]]; then
        XLS_PATH="$1"
      else
        echo "Unexpected argument: $1" >&2
        usage 1
      fi
      ;;
  esac
  shift
done

if [[ -z "$XLS_PATH" ]]; then
  echo "Error: path to .xls file is required." >&2
  usage 1
fi

if [[ ! -f "$XLS_PATH" ]]; then
  echo "Error: file not found: $XLS_PATH" >&2
  exit 1
fi

case "$XLS_PATH" in
  "$REPO_ROOT"/*) HOST_PATH="$XLS_PATH" ;;
  *) HOST_PATH="$(cd "$(dirname "$XLS_PATH")" && pwd)/$(basename "$XLS_PATH")" ;;
esac

CONTAINER_PATH="/host/stay/${HOST_PATH#$REPO_ROOT/}"

echo "== Booking XLS import =="
echo "File:       $HOST_PATH"
echo "Tenant:     $TENANT_ID"
echo "Property:   $PROPERTY_SLUG"
echo "Container:  $CONTAINER_PATH"
[[ -n "$DRY_RUN" ]] && echo "Mode:       dry-run"
[[ -n "$ALLOW_UPDATE" ]] && echo "Mode:       allow-update (overwrite existing)"
[[ -n "$FILL_EMPTY" ]] && echo "Mode:       fill-empty (only blank fields on existing)"
[[ -z "$ALLOW_UPDATE" && -z "$FILL_EMPTY" ]] && echo "Mode:       skip existing (default)"

docker compose run --rm \
  -v "$REPO_ROOT:/host/stay:ro" \
  django python manage.py import_booking_xls \
  "$CONTAINER_PATH" \
  --tenant-id "$TENANT_ID" \
  --property-slug "$PROPERTY_SLUG" \
  $DRY_RUN \
  $ALLOW_UPDATE \
  $FILL_EMPTY
