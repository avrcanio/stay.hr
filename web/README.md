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
