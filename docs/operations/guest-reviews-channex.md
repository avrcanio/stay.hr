# Guest reviews (Channex) — operations

Runbook for OTA guest reviews ingested via Channex (Booking.com, Airbnb, Expedia).

## Prerequisites

Same as guest messaging:

1. **Messaging & Reviews** app enabled on the Channex property ([Channex Apps](https://app.channex.io/applications)).
2. stay.hr **Channex IntegrationConfig** with valid `property_id` and API key.
3. Tenant `channel_manager = channex`.

## Channex webhook

On the existing stay.hr webhook, add events (with **`send_data=true`**):

| Event | Purpose |
|-------|---------|
| `review` | New review received |
| `updated_review` | Review updated (e.g. guest text arrives later) |

Keep existing `booking*` and `message` events.

Webhook URL:

```text
https://api.stay.hr/api/v1/integrations/channex/webhook/?provider=stay&env=production
```

## Backend storage

- Model: **Integrations → Channex reviews** (`ChannexReview`)
- Inbound via webhook; optional backfill:

```bash
docker compose exec django python manage.py sync_channex_reviews --tenant-slug=uzorita
```

## Reception API

| Method | Path |
|--------|------|
| GET | `/api/v1/reception/reviews/` — property inbox (`?unreplied=1`, `?ota=BookingCom`, `?sync=auto\|1\|0`, `?lang=hr`, `?translate=1`) |
| GET | `/api/v1/reception/reviews/{id}/` — same `lang` / `translate` query params |
| POST | `/api/v1/reception/reviews/{id}/reply/` — body `{"reply": "..."}` |
| POST | `/api/v1/reception/reviews/{id}/compose-reply/` — body `{"hint": "...", "language": "..."}` (optional) → `{body_text, language, llm_used}` |
| POST | `/api/v1/reception/reviews/{id}/guest-review/` — Airbnb rate guest |
| GET | `/api/v1/reception/reservations/{id}/reviews/` — `lang` / `translate` supported |

Review text fields in list/detail responses:

- `content` — OTA original
- `content_localized` — text in requested `lang` (cached in `ChannexReview.content_translations`)
- `content_is_translated` — whether localized text differs from original
- `translation_available` — OpenAI translate configured

## UI

| Surface | Location |
|---------|----------|
| Web recepcija | Nav **Recenzije** → `/reviews` (read-only inbox); reply on `/reservations/[id]/reviews/[reviewId]` |
| Hospira tablet | Tab **Recenzije** (read-only); reply on reservation → review detail |

## Push notifications

Event type: `guest.review.received` (FCM data + notification).  
Tablet: Postavke → obavijest **Recenzija gosta**.  
Tap (background) ili foreground SnackBar **Otvori** (s `review_id` u payloadu) → `/reservations/{id}/reviews/{reviewId}`; inače inbox `/reviews`.

## Manual test checklist

| # | Scenario | PASS |
|---|----------|------|
| 1 | Webhook `review` → row in admin + push on tablet | |
| 2 | Webhook `updated_review` with `content` → row updated | |
| 3 | GET property inbox — filter unreplied | |
| 4 | GET reviews on Channex reservation | |
| 5 | POST reply → visible in Channex UI | |
| 6 | Airbnb POST guest-review (hidden review) | |
| 7 | Expired `expired_at` → API rejects reply | |
| 8 | Web + Flutter show same data | |
| 9 | Push tap → review detail (or inbox fallback) | |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 403 from Channex API | Enable **Messaging & Reviews** app on property |
| Reviews not in webhook | Add `review` / `updated_review` events on webhook |
| No reservation link | Booking not yet in stay.hr; review stays in property inbox |
| Airbnb reply disabled | Hidden review — submit **guest-review** first |
| Reply shown as dict string in app | Run `sync_channex_reviews --tenant-slug=…` (includes reply repair) |

## Deploy

```bash
docker compose exec django python manage.py migrate
docker compose build django && docker compose up -d django celery-worker
```
