# AGENTS.md — stay.hr

Guidance for AI agents and developers working in this repository.

## Current mode: development

**The project is running in Next.js development mode.** Frontend changes hot-reload without rebuilding Docker images.

### What this means

| Layer | Mode | Hot reload |
|-------|------|------------|
| `web/booking` | `next dev` (Docker) | Yes — edit TSX/CSS, refresh browser |
| `web/reception` | `next dev` (Docker) | Yes |
| `django` / Celery | Production image | No — restart container or `./scripts/deploy.sh` after Python changes |

Dev mode is enabled by [`docker-compose.override.yml`](docker-compose.override.yml), which Docker Compose loads automatically alongside [`docker-compose.yml`](docker-compose.yml).

### Frontend workflow

1. Edit files under `web/booking/` or `web/reception/`
2. Save — Next.js recompiles inside the container
3. Refresh the browser (Traefik URLs unchanged: `booking.uzorita.hr`, `app.stay.hr`, etc.)

**Do not** run `docker compose build web-booking` or `web-reception` for routine UI work.

After changing `package.json` or adding npm dependencies:

```bash
docker compose build web-booking web-reception
docker compose up -d web-booking web-reception
```

### Backend workflow

Python/API changes still require a Django container restart or deploy:

```bash
./scripts/deploy.sh
# or
docker compose restart django
```

### Switch back to production frontends

Remove or rename `docker-compose.override.yml`, then rebuild and start:

```bash
mv docker-compose.override.yml docker-compose.override.yml.bak
docker compose build web-booking web-reception
docker compose up -d web-booking web-reception
```

### Local (non-Docker) frontend dev

```bash
cd web/booking   # or web/reception
npm install
npm run dev
```

Set `STAY_API_INTERNAL_URL` and `STAY_BOOKING_API_TOKEN` in `.env` / shell. See [web/README.md](web/README.md).

### Key paths

- Booking app: `web/booking/`
- Reception app: `web/reception/`
- Django API: `backend/`
- Ops runbook: `docs/operations/domain-setup.md`
