# Prijava overbookinga — 24.–25.7.2026

**Objekt:** Luxury Room Uzorita B&B  
**Booking.com property ID:** 4181954  
**Datum prijave:** 4.6.2026  
**Konfliktna noć:** 24.07.2026 – 25.07.2026

---

## Sažetak

Booking.com je za **istu noć** prodao **R1** i **R3** dvaput, dok je rezervacija **5796838012** (Susanne Mayer) već bila potvrđena za **cijeli objekt** (4 sobe: R1, R2, R3, R6). Kasnije single-room rezervacije **5238895494** (Pierre LE VAILLANT, R1) i **5398124917** (Eduardo de las Heras, R3) ne mogu se fizički ispuniti.

| | Rezervacija A (incumbent) | Rezervacija B (R1 konflikt) | Rezervacija C (R3 konflikt) |
|---|---|---|---|
| **Booking broj** | **5796838012** | **5238895494** | **5398124917** |
| **Gost** | Susanne Mayer | Pierre Yves LE VAILLANT | Eduardo de las Heras |
| **Check-in / Check-out** | 24.07. → 25.07.2026 | 24.07. → 25.07.2026 | 24.07. → 25.07.2026 |
| **Sobe (Booking.com)** | R3, R1, R6, R2 (4 sobe) | R1 | R3 |
| **Gosti** | 8 odr + 1 dijete | 2 odr | 3 odr |
| **Datum rezervacije** | **1.3.2026** | 28.5.2026 | 30.5.2026 |
| **Ukupna cijena** | €440,65 | €76,70 | €102,05 |

---

## Operativno rješenje objekta (stay.hr)

| Rezervacija | Akcija |
|-------------|--------|
| **5796838012** Susanne Mayer | **OSTAJE** — cijeli objekt R1+R2+R3+R6 (incumbent, 1.3.2026) |
| **5238895494** Pierre LE VAILLANT | **OTKAZ** — kasnija rezervacija, nema slobodne sobe |
| **5398124917** Eduardo de las Heras | **OTKAZ** — kasnija rezervacija, nema slobodne sobe |

U stay.hr:
- Susanne #82: 4 sobe, `import_source=booking_pdf`, `booked_at=1.3.2026`
- Pierre #798: `status=canceled` (4.6.2026), `OVERBOOKING:` napomena
- Eduardo #807: `status=canceled` (4.6.2026), `OVERBOOKING:` napomena
- `detect_overbooking --from-date 2026-07-23`: **0 konflikata**

### Poruke gostima (Booking.com)

Tekstovi pripremljeni — **ParkCity samostalna rezervacija + besplatan doručak Uzorita 25.7.**:

| Booking | Datoteka | Jezik |
|---------|----------|-------|
| 5238895494 | [`docs/operations/booking-message-5238895494-pierre-fr.txt`](operations/booking-message-5238895494-pierre-fr.txt) | francuski |
| 5398124917 | [`docs/operations/booking-message-5398124917-eduardo-es.txt`](operations/booking-message-5398124917-eduardo-es.txt) | španjolski |

**Channex API (4.6.2026):** `POST /bookings/{id}/messages` → **403 Forbidden** (`Property has not access`).

**Email guest.booking.com (4.6.2026):** poslano tenant SMTP `room_reservations@uzorita.hr`:
- Pierre → `pvaill.980290@guest.booking.com` (FR tekst)
- Eduardo → `eheras.626816@guest.booking.com` (ES tekst)

---

## Dokazi (PDF)

Prilozi u `.imports/conflicts/2026-07-24/`:

- `5796838012.pdf` — Susanne Mayer (4 sobe)
- `5238895494.pdf` — Pierre LE VAILLANT (R1)
- `5398124917.pdf` — Eduardo de las Heras (R3)
- `5191789502.pdf` — Anne Marie Fabry (R1, 23.–24.7., nije u konfliktu — checkout prije noći 24.–25.)
- `5057367353.pdf` — Antonio De Leonardis (R2, 22.–24.7., nije u konfliktu)

---

## Zahtjev prema Booking.com

Molimo **otkazati bez penala za objekt** (ako extranet otkaz nije već napravljen):

- [ ] Rezervacija **5238895494** (Pierre LE VAILLANT, R1, 24.–25.7.2026)
- [ ] Rezervacija **5398124917** (Eduardo de las Heras, R3, 24.–25.7.2026)

**Razlog:** overbooking greška — objekt je već bio prodan u cijelosti rezervacijom **5796838012** (1.3.2026).

**Channex CRS cancel (4.6.2026):** `PUT /bookings/{id}` → **403 Forbidden** — **Booking CRS app** nije aktivan. stay.hr označen `canceled` lokalno; **B.com extranet otkaz ili support ticket još potreban**.

---

## Channex / kanal

- Susanne (#82) zaštićena PDF lockom (`import_source=booking_pdf`)
- Channex ARI full sync 4.6.2026 (nakon lokalnog otkaza Pierre/Eduardo)
- Nove management naredbe:
  - `send_channex_booking_message --reservation-id ID --message-file PATH`
  - `cancel_channex_booking --reservation-id ID [--mark-local-on-failure]`

---

## Povijest akcija objekta (interno)

| Datum | Akcija |
|-------|--------|
| 4.6.2026 | Identificiran konflikt — 5 PDF-ova u `.imports/conflicts/2026-07-24/` |
| 4.6.2026 | PDF import Susanne 5796838012 → 4 sobe, 8 odraslih, booked_at 1.3.2026 |
| 4.6.2026 | detect_overbooking: 2 konflikta (R1, R3) |
| 4.6.2026 | Incumbent odluka: Pierre #798 i Eduardo #807 — OVERBOOKING napomena, sobe uklonjene |
| 4.6.2026 | Channex ARI full sync (uzorita) |
| 4.6.2026 | Email FR/ES poslan na guest.booking.com (tenant SMTP) |
| 4.6.2026 | Poruke FR/ES pripremljene; Channex send 403 |
| 4.6.2026 | Channex cancel 403 — stay.hr #798/#807 `canceled` lokalno; **B.com extranet otkaz pending** |
| ___.___.2026 | Otkaz 5238895494 i 5398124917 potvrđen na B.com |
