# Guest messages — tri kanala (Mail, Channex, WhatsApp)

Operativni runbook za slanje i primanje poruka gostima iz stay.hr recepcije (web + Flutter).

---

## Kanali

| Kanal | Outbound | Inbound u stay.hr | Rezervacije |
|-------|----------|-------------------|-------------|
| **Mail** | Tenant SMTP (`room_reservations@uzorita.hr`) | Ne | Sve s emailom |
| **Channex** | Channex Messages API → B.com Poruke | Da (webhook `message`) | `import_source=channex` |
| **WhatsApp** | Handoff (`wa.me`) | Da (WhatsApp webhook) | S telefonom |

**Vlastita booking platforma** (stay.hr web booking, `source=api`): nema guest app — koristi **Mail** (+ WhatsApp). Inbound odgovori gosta na mail **ne ulaze** u chat timeline.

**B.com PDF import** (`import_source=booking_pdf`): Mail na `@guest.booking.com` + WhatsApp; Channex API **nije** dostupan (nema Channex linka).

---

## Channex setup (jednokratno)

1. Channex UI → Property → Apps → **Messages & Reviews** — instalirano
2. Webhook (isti URL kao bookingi):
   ```text
   https://api.stay.hr/api/v1/integrations/channex/webhook/?provider=stay&env=staging
   ```
   Header: `X-Stay-Channex-Webhook: <secret iz IntegrationConfig>`
3. Dodati event **`message`** s **`send_data=true`**

---

## API (recepcija)

| Metoda | Ruta |
|--------|------|
| GET | `/api/v1/reception/reservations/{id}/messages/` — unified chat timeline |
| POST | `/api/v1/reception/reservations/{id}/messages/compose/` |
| POST | `/api/v1/reception/reservations/{id}/messages/send/` — body: `{ draft_id, channel, body_text }` |
| GET | `/api/v1/reception/reservations/{id}/channex-messages/` — samo Channex (legacy/sync) |

`channel` u send: `email` | `booking` | `whatsapp`

---

## Reception web

Detalj rezervacije → sekcija **Poruke gostu** ([`GuestMessagesPanel.tsx`](../../web/reception/app/_components/GuestMessagesPanel.tsx)):

- Chat timeline
- Generiraj (check-in / odgovor / prilagođeno)
- Odabir kanala: Channex / Mail / WhatsApp (samo dostupni)

---

## CLI

```bash
# Pošalji poruku preko Channexa
docker compose exec django python manage.py send_channex_booking_message \
  --reservation-id 798 \
  --message-file docs/operations/booking-message-5238895494-pierre-fr.txt \
  --tenant-slug uzorita

# Povuci postojeće poruke iz Channexa (backfill)
docker compose exec django python manage.py sync_channex_booking_messages \
  --tenant-slug uzorita

# Jedna rezervacija
docker compose exec django python manage.py sync_channex_booking_messages \
  --tenant-slug uzorita --reservation-id 798
```

---

## Provjera

| Test | Očekivano |
|------|-----------|
| Gost piše na B.com | Inbound u admin → Channex messages; vidljivo u web/Flutter timeline |
| Send `booking` | Poruka u B.com extranet Poruke |
| Send `email` | Mail na gostovu adresu; Sent u webmail |
| Send `whatsapp` | Otvara WhatsApp s predloženim tekstom |
| Vlastita platforma compose | `booking.available=false`, `email.available=true` |

---

## Troubleshooting

| Simptom | Rješenje |
|---------|----------|
| Send booking → 403 | Messages & Reviews app nije aktivan na Channex propertyju |
| Inbound ne stiže | Webhook nema `message` event; provjeri Django log |
| `booking.available=false` | Rezervacija nije `import_source=channex` ili nema Channex external_id |
| Mail ne odlazi | Tenant SMTP u Reception settings (`guest_contact_email` + password) |

---

## Povezano

- [guest-messages-flutter.md](../development/guest-messages-flutter.md) — Flutter implementacija
- [channex-uzorita-booking-channel.md](../integrations/channex-uzorita-booking-channel.md)
- [whatsapp-checkin-template.md](./whatsapp-checkin-template.md)
