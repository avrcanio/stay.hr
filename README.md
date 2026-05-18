# Stay.hr

Multi-tenant SaaS platform (Django + DRF + Celery) behind Traefik and Cloudflare.

## Prerequisites

- Docker and the external `proxy` network: `docker network create proxy` (if missing)
- Shared PostGIS on the `postgis` Docker network (`/opt/stacks/data`)
- Traefik with `certificatesresolvers.cloudflare` and `CF_DNS_API_TOKEN` in `/opt/stacks/traefik/.env`

## Quick start

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY, DB_PASSWORD, and other secrets

docker compose build django
docker compose up -d
docker compose exec django python manage.py migrate
```

## Cloudflare DNS (api + admin)

Traefik terminates TLS using DNS-01 (Cloudflare). Public hostnames must exist as **proxied A** records pointing at this server.

```bash
cp scripts/.env.example scripts/.env
# Set TARGET_SERVER_IP to the Hetzner public IP (or rely on stay.hr apex A if present)

./scripts/cloudflare_dns_upsert.sh
```

The script reads `CF_DNS_API_TOKEN` from `/opt/stacks/traefik/.env` and upserts:

- `api.stay.hr` → Django API + `/health/`
- `admin.stay.hr` → Django admin (`/admin/`)

Verify:

```bash
curl -sS https://api.stay.hr/health/
curl -sS -o /dev/null -w '%{http_code}\n' https://admin.stay.hr/admin/login/
```

Admin is reachable over HTTPS behind the Cloudflare proxy (no Zero Trust Access in v1). Consider Cloudflare Access or WAF rate limits on `/admin/login/` later.

## API authentication (later)

```http
Authorization: Bearer stay_pk_live_...
X-Stay-App-Key: stay_pk_live_...
```
