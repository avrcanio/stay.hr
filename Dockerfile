FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

COPY scripts/run-gunicorn.sh /app/scripts/run-gunicorn.sh
RUN chmod +x /app/scripts/run-gunicorn.sh

COPY backend/ ./backend/

RUN groupadd --gid 1000 stay \
    && useradd --uid 1000 --gid stay --create-home --shell /usr/sbin/nologin stay \
    && chown -R stay:stay /app

WORKDIR /app/backend

USER stay

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["/app/scripts/run-gunicorn.sh"]
