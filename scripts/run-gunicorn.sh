#!/bin/sh
set -e

cd /app/backend

GUNICORN_WORKERS="${GUNICORN_WORKERS:-8}"
GUNICORN_WORKER_CLASS="${GUNICORN_WORKER_CLASS:-sync}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-3600}"
GUNICORN_KEEPALIVE="${GUNICORN_KEEPALIVE:-5}"
GUNICORN_GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-60}"
GUNICORN_MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-1000}"
GUNICORN_MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-100}"
GUNICORN_PRELOAD="${GUNICORN_PRELOAD:-false}"

echo "Gunicorn configuration:"
echo "  workers=${GUNICORN_WORKERS}"
echo "  worker_class=${GUNICORN_WORKER_CLASS}"
echo "  timeout=${GUNICORN_TIMEOUT}"
echo "  graceful_timeout=${GUNICORN_GRACEFUL_TIMEOUT}"
echo "  keepalive=${GUNICORN_KEEPALIVE}"
echo "  max_requests=${GUNICORN_MAX_REQUESTS}"
echo "  max_requests_jitter=${GUNICORN_MAX_REQUESTS_JITTER}"
echo "  preload=${GUNICORN_PRELOAD}"
echo "  access_log=stdout"

GUNICORN_ARGS="
  config.wsgi:application
  -b 0.0.0.0:8000
  --workers ${GUNICORN_WORKERS}
  --worker-class ${GUNICORN_WORKER_CLASS}
  --timeout ${GUNICORN_TIMEOUT}
  --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT}
  --keep-alive ${GUNICORN_KEEPALIVE}
  --max-requests ${GUNICORN_MAX_REQUESTS}
  --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER}
  --access-logfile -
"

case "$(echo "${GUNICORN_PRELOAD}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on)
    GUNICORN_ARGS="${GUNICORN_ARGS} --preload"
    ;;
esac

# shellcheck disable=SC2086
exec gunicorn ${GUNICORN_ARGS}
