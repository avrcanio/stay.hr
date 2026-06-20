#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker cp backend/apps/reservations/management/commands/ops_res22_bottcher.py \
  stay_django:/app/backend/apps/reservations/management/commands/ops_res22_bottcher.py
docker compose exec -T django python manage.py ops_res22_bottcher "$@"
