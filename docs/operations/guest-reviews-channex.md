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
| GET | `/api/v1/reception/reviews/` — property inbox (`?unreplied=1`, `?ota=BookingCom`, `?sync=auto\|1\|0`, `?lang=hr`, `?translate=0\|1`) |
| GET | `/api/v1/reception/reviews/{id}/` — detail; `?lang=` + `?translate=1` lokalizira tekst recenzije |
| POST | `/api/v1/reception/reviews/{id}/reply/` — body `{"reply": "..."}` |
| POST | `/api/v1/reception/reviews/{id}/guest-review/` — Airbnb rate guest |
| GET | `/api/v1/reception/reservations/{id}/reviews/` |

## UI

| Surface | Location |
|---------|----------|
| Web recepcija | Nav **Recenzije** → `/reviews`; panel on reservation detail |
| Hospira tablet | **Više → Recenzije gostiju**; summary on reservation detail |

## Translation (OpenAI)

Guest review text can be auto-translated to the reception UI language (web recepcija cookie `stay_locale`, Hospira app locale, or `Accept-Language`).

Query params:

| Param | Values | Default |
|-------|--------|---------|
| `lang` | `hr`, `en`, `de`, `es`, `fr`, `it` | `Accept-Language` → tenant `default_language` |
| `translate` | `0` / `1` | list inbox: `0`; detail + reservation panel: `1` |

Response fields: `content` (original OTA text), `content_localized`, `content_is_translated`, `translation_available`.

Uses the same OpenAI key as guest message compose (`GUEST_COMPOSE_LLM_API_KEY`). Translations are cached in `ChannexReview.content_translations`.

Hospira example:

```http
GET /api/v1/reception/reviews/42/?lang=hr&translate=1
Accept-Language: hr-HR
```

## Push notifications

Event type: `guest.review.received` (FCM data + notification).  
Tablet: Postavke → obavijest **Recenzija gosta**.

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
| 9 | Push tap → reviews inbox | |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 403 from Channex API | Enable **Messaging & Reviews** app on property |
| Reviews not in webhook | Add `review` / `updated_review` events on webhook |
| No reservation link | Booking not yet in stay.hr; review stays in property inbox |
| Airbnb reply disabled | Hidden review — submit **guest-review** first |

## Deploy

```bash
docker compose exec django python manage.py migrate
docker compose build django && docker compose up -d django celery-worker
```
