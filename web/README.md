# Stay.hr web frontends

Next.js apps for public booking and reception (read-only MVP).

| App | Path | Host |
|-----|------|------|
| Booking | `web/booking` | `*.stay.hr`, custom domains |
| Reception | `web/reception` | `app.stay.hr` |

## Local development

```bash
cd web/booking   # or web/reception
npm install
npm run dev
```

Booking needs `STAY_BOOKING_API_TOKEN` and reachable Django API. Reception uses login form (device token → httpOnly cookie).

Production deploy: see [docs/operations/domain-setup.md](../docs/operations/domain-setup.md).

## Docker: development vs production

When [`docker-compose.override.yml`](../docker-compose.override.yml) is present, `web-booking` and `web-reception` run `next dev` with source bind mounts — no image rebuild for UI edits.

**Return to dev mode** (from production):

```bash
cd /opt/stacks/stay.hr
mv docker-compose.override.yml.bak docker-compose.override.yml
docker compose build web-booking web-reception
docker compose up -d web-booking web-reception
```

Full details: [README.md — Frontend: production vs development mode](../README.md#frontend-production-vs-development-mode) and [AGENTS.md](../AGENTS.md).
