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

## Periodic sync

Celery beat runs `sync_channex_reviews_periodic` every **6 hours** for `uzorita` (same tenant as message sync). Manual backfill:

```bash
docker compose exec django python manage.py sync_channex_reviews --tenant-slug=uzorita
```

Opening **Recenzije** with default `sync=auto` re-pulls from Channex when the last sync is older than 6 hours.

Reservation **checked out within the last 7 days**: `GET .../reservations/{id}/reviews/` defaults to `sync=auto` (pull if empty or stale).

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
- `reply_published` — Booking.com (or OTA) confirmed publication (`reply_sent_at` set)
- `reply_pending_moderation` — Booking.com reply submitted but not yet published
- `suggested_reply_language` — detected language for compose (match guest review when possible)
- `can_reply` — `true` while no published reply and deadline not expired (allows resubmit after moderation rejection)

## Booking.com reply moderation

All public replies on Booking.com are **moderated** before they appear on the extranet (up to **72 hours**).

| Signal | Meaning |
|--------|---------|
| Channex `is_replied: true` | stay.hr successfully POSTed a reply to Channex |
| `reply_sent_at` set | Publication confirmed (visible on Booking.com) |
| `reply` text + `reply_sent_at` null | Pending moderation or **rejected** — staff can edit and resend from stay.hr |

**Content guidelines** (reduce rejection risk):

- Reply in the **guest review language** or **English**
- Keep it short (2–4 sentences), professional, thank the guest
- **Do not repeat** explicit negative details from the review (dirty bathroom, insects, noise specifics)
- No contact details, links, or compensation offers

If Booking shows *“Your response was not approved”*, shorten the reply, remove repeated complaints, and resubmit (stay.hr allows resend while `reply_published` is false).

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
| Review on Booking.com but not in stay.hr | Normal delay Booking.com → Channex; `sync=1` only helps after Channex has the row. Periodic sync every 6 h via Celery (`channex-reviews-periodic`). |
| Inbox `sync=auto` missed a new review | Fixed: `sync=auto` now re-pulls if last sync is older than 6 h (not only when inbox is empty) |
| No reservation link | Booking not yet in stay.hr; review stays in property inbox |
| Airbnb reply disabled | Hidden review — submit **guest-review** first |
| Reply shown as dict string in app | Run `sync_channex_reviews --tenant-slug=…` (includes reply repair) |

## Deploy

```bash
docker compose exec django python manage.py migrate
docker compose build django && docker compose up -d django celery-worker
```
