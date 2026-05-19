# Stay.hr

Multi-tenant SaaS platform for accommodation providers (Django + DRF + Celery), behind Traefik and Cloudflare.

Uzorita (`/opt/stacks/uzorita`) is a separate system; no migration is included in this project.

## Prerequisites

- Docker and external networks: `proxy`, `postgis`, `hetzner_net` (if missing: `docker network create proxy`, etc.)
- Shared PostGIS on the `postgis` network (`/opt/stacks/data`) **or** adjust `DB_HOST` in `.env`
- Shared Redis on `hetzner_net` (`/opt/stacks/redis`, container `infra-redis`, **DB 2** for Stay)
- Traefik with `certificatesresolvers.cloudflare` and `CF_DNS_API_TOKEN` in `/opt/stacks/traefik/.env`

## Quick start

```bash
cd /opt/stacks/stay.hr
cp .env.example .env
# Set DJANGO_SECRET_KEY, DB_PASSWORD, and other secrets

docker compose build
docker compose up -d
docker compose run --rm django python manage.py migrate
docker compose run --rm django python manage.py createsuperuser
```

## Migrations

```bash
docker compose run --rm django python manage.py makemigrations
docker compose run --rm django python manage.py migrate
docker compose run --rm django python manage.py check
```

## Demo tenant and Flutter API token

```bash
docker compose run --rm django python manage.py seed_demo_tenant
docker compose run --rm django python manage.py create_api_app --tenant demo --name "Demo Flutter"
```

The `create_api_app` command prints the raw token **once**. It is stored in the database only as a SHA-256 hash.

Default scopes for the demo command: `public:read`, `reservations:create` (no admin scopes).

## API authentication

Send the app key using either header:

```http
Authorization: Bearer stay_pk_live_...
```

```http
X-Stay-App-Key: stay_pk_live_...
```

Example:

```bash
TOKEN="stay_pk_live_..."  # from create_api_app output

curl -sS -H "Authorization: Bearer $TOKEN" https://api.stay.hr/api/v1/app/config | jq .
curl -sS -H "Authorization: Bearer $TOKEN" "https://api.stay.hr/api/v1/public/properties"
curl -sS -H "Authorization: Bearer $TOKEN" "https://api.stay.hr/api/v1/public/units?property=demo"
curl -sS -H "Authorization: Bearer $TOKEN" "https://api.stay.hr/api/v1/public/availability?from=2026-06-01&to=2026-06-15&property=demo"
```

Create a reservation (requires `reservations:create` scope):

```bash
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "property_slug": "demo",
    "check_in": "2026-07-01",
    "check_out": "2026-07-05",
    "booker_name": "Ana Anić",
    "booker_email": "ana@example.com",
    "guests": [{"first_name": "Ana", "last_name": "Anić"}]
  }' \
  https://api.stay.hr/api/v1/public/reservations
```

## API endpoints (v1)

| Method | Path | Scope |
|--------|------|-------|
| GET | `/health/` | none |
| GET | `/api/v1/app/config` | `public:read` |
| GET | `/api/v1/public/properties` | `public:read` |
| GET | `/api/v1/public/units` | `public:read` |
| GET | `/api/v1/public/availability?from=&to=&property=` | `public:read` |
| POST | `/api/v1/public/reservations` | `reservations:create` |

Tenant context is resolved from the API token (primary) or from the `Host` header via `TenantDomain` (for future `*.stay.hr` subdomains).

## Django admin

- https://admin.stay.hr/admin/

### Platform superuser vs tenant staff

| Role | Access |
|------|--------|
| **Superuser** | All tenants, users, domains, platform settings |
| **Staff + tenant membership** | Only data for assigned tenant(s): properties, reservations, integrations, API applications |

Staff users **do not** see the Tenants or Users modules. API login (device bearer tokens) and admin login are separate channels.

### Adding a tenant staff user (superuser only)

1. **Users** → **Add user** — set username, password, enable **Staff status** (not superuser unless intended).
2. In **Tenant access** inline, add one or more tenants.
3. The user signs in at `admin.stay.hr` and sees only those tenants’ records (multiple tenants appear in one changelist with a **tenant** column/filter).

### Day-to-day operations

- Create tenants, domains, properties, units, reservations (superuser for tenants/domains; staff within their tenants for the rest).
- **API applications:** device tokens are stored **encrypted** (`token_encrypted`, Fernet via `STAY_INTEGRATION_FERNET_KEY`). On the change form, **Device token** shows the full bearer for copy into Hospira. Legacy rows without ciphertext: use admin action **Regenerate API token** (invalidates the old bearer).
- When adding an **API application**, the raw token is also shown once in a warning message

## Cloudflare DNS (api + admin)

```bash
cp scripts/.env.example scripts/.env
./scripts/cloudflare_dns_upsert.sh
```

Upserts proxied A records for `api.stay.hr` and `admin.stay.hr` pointing at this server.

Verify:

```bash
curl -sS https://api.stay.hr/health/
curl -sS -o /dev/null -w '%{http_code}\n' https://admin.stay.hr/admin/login/
```

## Traefik / tenant subdomains (later)

Wildcard `*.stay.hr` router labels are commented in `docker-compose.yml`. Enable when Cloudflare DNS wildcard and tenant domains are ready.

## Security notes

- API authentication uses SHA-256 **hash** lookup (`public_key_hash`); requests do not decrypt `token_encrypted`
- Recoverable copies for admin are **Fernet-encrypted** in the database (`STAY_INTEGRATION_FERNET_KEY` required in production)
- Regenerating a token in admin invalidates the previous bearer immediately
- Revoke access with `is_active=False` on the API application
- Flutter/mobile tokens must not include `admin:read` or `admin:write`

## Shared infra layout

Stay.hr does **not** run its own Postgres or Redis containers. It attaches to the shared Hetzner stack:

| Component | Path / container | Network | Stay usage |
|-----------|------------------|---------|------------|
| PostGIS | `/opt/stacks/data` → `postgis` | `postgis` | DB `stay_platform_db`, user `stay` |
| Redis | `/opt/stacks/redis` → `infra-redis` | `hetzner_net` | Redis logical DB **2** (broker + results) |
| Traefik | `/opt/stacks/traefik` | `proxy` | TLS for `api.stay.hr`, `admin.stay.hr` |
| Document media | `/opt/stacks/stay.hr/data/media` | bind mount | Reception face/ID photos (`MEDIA_ROOT`) |

Create the database once on shared PostGIS (as superuser):

```sql
CREATE USER stay WITH PASSWORD 'your-password';
CREATE DATABASE stay_platform_db OWNER stay;
GRANT ALL PRIVILEGES ON DATABASE stay_platform_db TO stay;
```

Match `DB_PASSWORD` in `.env`. Celery beat runs an hourly `apps.core.tasks.ping` task to verify the worker pipeline.

## Stack layout

| Service | Role |
|---------|------|
| `django` | Gunicorn, API + admin, Traefik labels; `./data/media` → `/app/backend/media` |
| `celery-worker` | Background tasks; same media volume as django |
| `celery-beat` | Scheduled tasks |
| `infra-redis` (`hetzner_net`, DB 2) | Celery broker and result backend |
| PostGIS (`postgis` network) | Database `stay_platform_db` |
