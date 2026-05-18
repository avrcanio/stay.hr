#!/bin/sh
set -e

cd /app/backend

mkdir -p media

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
