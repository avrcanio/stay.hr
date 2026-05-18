#!/bin/sh
set -e

cd /app/backend

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
