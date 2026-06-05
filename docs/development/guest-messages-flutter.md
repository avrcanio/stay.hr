# Guest messages — Flutter (Hospira) integracija

**Flutter repo:** [github.com/avrcanio/uzorita_flutter](https://github.com/avrcanio/uzorita_flutter) (`hr.finestar.hospira`)

**Backend:** [`backend/apps/api/reception_guest_messages_views.py`](../../backend/apps/api/reception_guest_messages_views.py), [`guest_message_send.py`](../../backend/apps/communications/guest_message_send.py)

**Reception web referenca:** [`web/reception/app/_components/GuestMessagesPanel.tsx`](../../web/reception/app/_components/GuestMessagesPanel.tsx)

---

## Tri kanala slanja

| Kanal | API `channel` | Kada je `available` | Outbound | Inbound u timeline |
|-------|-----------------|---------------------|----------|-------------------|
| **Mail** | `email` | Gost ima email | Tenant SMTP | Ne (nema email ingest) |
| **Channex** | `booking` | `import_source=channex` + Channex booking ID | Channex → B.com Poruke | Da (webhook) |
| **WhatsApp** | `whatsapp` | Gost ima telefon | `wa.me` handoff | Da (webhook) |

### Po tipu rezervacije

| Tip | Channex | Mail | WhatsApp |
|-----|---------|------|----------|
| Channex / B.com (`import_source=channex`) | Da | Da (fallback) | Ako ima tel. |
| Vlastita platforma (`source=api`) | Ne | **Primarni** | Ako ima tel. |
| B.com PDF import (`import_source=booking_pdf`) | Ne | Da (`@guest.booking.com`) | Ako ima tel. |

**Default odabir kanala u UI:**

1. Channex rezervacija → `booking` ako `channels.booking.available`, inače `email`
2. Vlastita platforma → `email`
3. WhatsApp uvijek alternativa kad je `channels.whatsapp.available`

---

## API ugovor

Auth: `Authorization: Bearer <device_token>` sa scope `reception:read` / `reception:write`.

Base: `/api/v1/reception/reservations/{id}/messages/`

### GET — timeline (chat)

```http
GET /api/v1/reception/reservations/798/messages/
```

Response: sortirani niz (asc po `created_at`):

```json
[
  {
    "id": 3000000042,
    "source": "booking",
    "direction": "inbound",
    "channel": "booking",
    "body_text": "Ok merci du mail",
    "created_at": "2026-06-04T15:01:08+00:00",
    "status": null,
    "sent_by_name": null,
    "from_email": null,
    "wa_me_url": null
  },
  {
    "id": 12,
    "source": "outbound",
    "direction": "outbound",
    "channel": "email",
    "body_text": "…",
    "created_at": "2026-06-04T16:00:00+00:00",
    "status": "sent",
    "sent_by_name": "Tablet R1",
    "wa_me_url": null
  }
]
```

| Polje | Značenje |
|-------|----------|
| `direction` | `inbound` (gost) / `outbound` (recepcija) |
| `channel` | `booking` \| `email` \| `whatsapp` |
| `source` | `booking` (Channex), `whatsapp`, `outbound` (email send audit) |
| `id` | Offset za Channex/WhatsApp; raw PK za outbound email |

**UI:** bubble lijevo = inbound, desno = outbound; badge po `channel` (Channex / Mail / WhatsApp).

### POST compose — generiraj tekst

```http
POST /api/v1/reception/reservations/798/messages/compose/
Content-Type: application/json

{"intent": "checkin"}
```

Intents: `checkin` | `reply` | `custom`. Opcionalno: `hint`, `language`.

Response:

```json
{
  "draft_id": 55,
  "body_text": "…",
  "language": "fr",
  "llm_used": false,
  "channels": {
    "email": {"available": true, "to": "pvaill.980290@guest.booking.com"},
    "whatsapp": {"available": false, "phone_raw": "", "phone_wa": "", "wa_me_url": ""},
    "booking": {"available": true}
  }
}
```

Check-in i `reply` + `hint: "checkin ready"` — deterministički template (`llm_used: false`). Vidi [`whatsapp-checkin-template.md`](../operations/whatsapp-checkin-template.md).

### POST send — pošalji

```http
POST /api/v1/reception/reservations/798/messages/send/
Content-Type: application/json

{
  "draft_id": 55,
  "channel": "booking",
  "body_text": "Uredeni tekst poruke."
}
```

`channel`: `email` | `booking` | `whatsapp`

**WhatsApp response** uključuje `wa_me_url` — otvori u browseru / `url_launcher`; recepcija ručno pošalje.

**Channex response** — isti oblik kao timeline item (`source: booking`, `status: sent`).

Nakon slanja: ponovno učitaj GET timeline.

---

## Predložena Flutter implementacija

### 1. Model

```dart
class GuestMessageTimelineItem {
  final int id;
  final String source;
  final String direction; // inbound | outbound
  final String channel; // booking | email | whatsapp
  final String bodyText;
  final DateTime createdAt;
  final String? sentByName;
  final String? waMeUrl;
}

class GuestMessageChannels {
  final bool emailAvailable;
  final String emailTo;
  final bool bookingAvailable;
  final bool whatsappAvailable;
  final String? waMeUrl;
}
```

### 2. Repository

```dart
Future<List<GuestMessageTimelineItem>> fetchTimeline(int reservationId);
Future<ComposeResult> compose(int reservationId, {required String intent, String? hint});
Future<GuestMessageTimelineItem> send(
  int reservationId, {
  required int draftId,
  required String channel,
  required String bodyText,
});
```

### 3. Ekran poruka (chat)

- `ListView` bubblea sortiranih po `createdAt`
- Pull-to-refresh → `fetchTimeline`
- Donji panel: intent gumbi (Check-in / Odgovor / Prilagođeno) → Compose → editable `TextField` → radio kanala (samo `available`) → Send

### 4. Odabir kanala

```dart
String defaultChannel(GuestMessageChannels c, {required bool isChannexReservation}) {
  if (isChannexReservation && c.bookingAvailable) return 'booking';
  if (c.emailAvailable) return 'email';
  if (c.whatsappAvailable) return 'whatsapp';
  return '';
}
```

`isChannexReservation`: `reservation.importSource == 'channex'`.

### 5. WhatsApp handoff

```dart
if (channel == 'whatsapp' && response.waMeUrl != null) {
  await launchUrl(Uri.parse(response.waMeUrl!));
}
```

### 6. Check-in ready hint (post-OCR)

Nakon uspješnog OCR apply postavi lokalni flag; sljedeći Reply → Compose automatski šalje `hint: "checkin ready"`. Vidi [`whatsapp-checkin-template.md`](../operations/whatsapp-checkin-template.md).

---

## Što ne implementirati u fazi 1

- Email inbound (mailbox parse) — nema API-ja
- Channex attachments — `have_attachment` postoji, download nije implementiran
- FCM push za nove Channex poruke — koristi refresh pri otvaranju ekrana

---

## Test plan (Flutter)

1. Channex rezervacija: timeline prikazuje inbound `booking` + outbound
2. Send `booking` → poruka u B.com extranet Poruke
3. Vlastita platforma: samo Mail + WhatsApp u channel pickeru; default Mail
4. WhatsApp send → otvara `wa.me` s tekstom
5. Compose check-in → `llm_used: false`, ispravan jezik

---

## Povezani dokumenti

- [`guest-messages-channels.md`](../operations/guest-messages-channels.md) — operativni runbook (Channex webhook, sync)
- [`whatsapp-checkin-template.md`](../operations/whatsapp-checkin-template.md) — check-in compose flow
- [`channex-uzorita-booking-channel.md`](../integrations/channex-uzorita-booking-channel.md) — Channex messaging setup
