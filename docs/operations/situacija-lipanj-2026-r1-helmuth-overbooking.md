# Situacija — overbooking R1, Helmuth Pohler (4.–5. lipnja 2026.)

**Objekt:** Luxury Room Uzorita B&B (tenant #2, property `uzorita`)  
**Datum dokumenta:** 4. lipnja 2026.  
**Kontakt:** Toni, +385 99 838 8513

---

## Sažetak

Booking.com overbooking na **R1** za noć **4.–5. 6. 2026.** Kasnija rezervacija **6725524010** (Helmuth Pohler) vs starija **5036489024** (Wolfgang Gross, B.com R1+R2; u stay.hr samo R2 → kalendar R1 bio otvoren).

| | Helmuth (AKCIJA) | Wolfgang (OSTAJE) |
|---|---|---|
| Booking | **6725524010** | 5036489024 |
| stay.hr id | **814** | 106 |
| Check-in/out | 4.–5. 6. 2026. | 4.–5. 6. 2026. |
| Soba B.com | R1 | R1 + R2 |
| Soba stay.hr | R1 | **R1 + R2** (PDF lock, potvrđeno 5. 6. 2026.) |
| Iznos stay.hr | €60,52 | €180,15 |
| `import_source` | `booking_pdf` | `booking_pdf` |
| Rezervirano | 1. 6. 2026. | ožujak / starija |

### PDF import (4. 6. 2026.)

| Datoteka | Rezervacija | Rezultat |
|----------|-------------|----------|
| `.imports/conflicts/5036489024.pdf` | Wolfgang (106) | R1+R2, €180,15, 2 odrasla, `booking_pdf` lock |
| `.imports/conflicts/6725524010.pdf` | Helmuth (814) | R1, €60,52, 2 odrasla; status **expected**; OVERBOOKING napomena |

**Channex:** R1 availability za 4.–5. 6. gurnuta (availability=0 — Wolfgang zauzet).

**Raspored soba (4. 6.):** R1 → Wolfgang + Helmuth (expected, **ne** check-in Uzorita); R2 → Wolfgang; R6 → Florin Stanciu (6925385738).

---

## Gost — kontakt (stay.hr)

| Polje | Vrijednost |
|-------|------------|
| Ime | Helmuth Pohler |
| Država | **AT** (poruka: **DE** + EN) |
| Email | hpohle.408216@guest.booking.com |
| Tel. | +43 664 3379293 |
| Dolazak (notes) | 16:00–17:00 |
| Smart Flex | Da (besplatna otkaz do 2 dana prije) |

---

## Obavijest gostu — status

| Kanal | Status | Napomena |
|-------|--------|----------|
| Channex → Booking.com Messages API | **403 Forbidden** | `Property has not access` — Messaging app na Channex propertyju vjerojatno nije aktiviran |
| Email na guest.booking.com | **Poslano** 4. 6. 2026. ~06:54 | DE + EN, `room_reservations@uzorita.hr` (tenant SMTP) |
| Booking.com extranet → Poruke | **Preporučeno (ručno)** | Copy-paste iz [Poruke](#poruke-gostu-copy-paste) — duplikat ako gost ne odgovori na email |

---

## ParkCity Rooms (alternativa)

| Polje | Vrijednost |
|-------|------------|
| Naziv | ParkCity Rooms |
| Adresa | Bana Josipa Jelačića 62, 22000 Šibenik |
| Tel. | +385 98 932 2440 |
| Booking.com | [parkcity-rooms](https://www.booking.com/hotel/hr/parkcity-rooms.hr.html?checkin=2026-06-04&checkout=2026-06-05) |
| Kapacitet 4.–5. 6. | **Potvrđen** (2 odrasla) |
| Doručak | **5. 6. 2026., 08:00** u Luxury Room Uzorita B&B (2 odrasla, potvrđeno gostom WhatsApp) |

**Koordinacija:** Nazvati ParkCity prije nego gost potvrdi; predati ime **Helmuth Pohler**, 2 odrasla, 1 noć, plaćanje prema dogovoru s Uzoritom.

---

## Prijava Booking.com support / disruption

**Property ID:** 4181954  
**Rezervacija u sporu (kasnija):** 6725524010  
**Referenca (starija):** 5036489024  
**Datum konflikta:** 4.–5. 6. 2026.  
**Soba:** Deluxe King Room R1

### Tekst za extranet (Help / Report issue / disruption)

```
Overbooking — same physical room R1 for the same night.

Property: Luxury Room Uzorita B&B (4181954)
Conflict night: 4–5 June 2026

Incumbent (earlier booking): 5036489024 — Wolfgang Gross — booked March 2025 on Booking.com for R1 + R2.
Later booking (action required): 6725524010 — Helmuth Pohler — booked 1 June 2026 for R1.

We cannot host Mr Pohler in R1 at our property tonight due to the earlier reservation.
We offered alternative accommodation at ParkCity Rooms (neighbour, 2 min walk) plus breakfast at our B&B on 5 June at no extra cost to the guest.

Please assist with relocation or penalty-free cancellation for 6725524010 and correct inventory so R1 is not sold twice.

Contact: Toni, +385 99 838 8513, room_reservations@uzorita.hr
```

- [ ] Prijava poslana u Booking.com extranetu
- [ ] Broj tiketa (upisati): _______________

---

## Poruke gostu (copy-paste)

### DE (primarno — AT)

```
Sehr geehrter Herr Pohler,

wir entschuldigen uns aufrichtig: Aufgrund eines technischen Overbookings auf Booking.com können wir Sie heute Nacht (4.–5. Juni 2026) nicht in der ursprünglich bestätigten Zimmerkategorie (Deluxe King Room R1) in Luxury Room Uzorita B&B unterbringen.

Die Ursache liegt nicht bei Ihnen — eine frühere bestätigte Reservierung belegt dasselbe Zimmer.

Wir bieten Ihnen folgende Lösung für dieselbe Nacht an:

• Unterkunft bei ParkCity Rooms (Nachbarhaus, ca. 2 Min. zu Fuß)
  Adresse: Bana Josipa Jelačića 62, 22000 Šibenik
  Tel.: +385 98 932 2440
  Booking.com: https://www.booking.com/hotel/hr/parkcity-rooms.hr.html?checkin=2026-06-04&checkout=2026-06-05

• Frühstück am 5. Juni bei Luxury Room Uzorita B&B (für Sie inklusive)

Wir unterstützen die Buchung bei ParkCity ohne Mehrkosten gegenüber Ihrer ursprünglichen Reservierung und haben das Overbooking Booking.com gemeldet (Reservierung 6725524010).

Bitte antworten Sie uns so bald wie möglich, damit wir den Check-in für heute Abend koordinieren können. Falls die Alternative nicht passt, unterstützen wir Sie bei einer stornofreien Lösung über Booking.com.

Mit freundlichen Grüßen
Toni
Luxury Room Uzorita B&B
+385 99 838 8513
```

### EN

```
Dear Mr Pohler,

We sincerely apologise — due to a technical overbooking on Booking.com, we are unable to host you tonight (4–5 June 2026) in the room originally confirmed at Luxury Room Uzorita B&B (Deluxe King Room R1).

This is not your fault. An earlier confirmed reservation holds the same room for these dates.

We can offer you a comparable solution for the same night:

• Accommodation at ParkCity Rooms (our neighbour, 2 min walk)
  Address: Bana Josipa Jelačića 62, 22000 Šibenik
  Phone: +385 98 932 2440
  Booking.com: https://www.booking.com/hotel/hr/parkcity-rooms.hr.html?checkin=2026-06-04&checkout=2026-06-05

• Breakfast at Luxury Room Uzorita B&B on 5 June (included for you as our guest)

We will assist with arranging the stay at ParkCity at no extra cost to you compared to your original booking, and we are also reporting the overbooking to Booking.com support (reservation 6725524010).

Please reply here as soon as possible so we can confirm check-in details for this evening. If this alternative does not work for you, we will help you cancel without penalty through Booking.com.

Kind regards,
Toni
Luxury Room Uzorita B&B
+385 99 838 8513
```

---

## Grane — čeka se odgovor gosta

| Odgovor | Akcija |
|--------|--------|
| **Prihvaća ParkCity** | Check-in ParkCity; doručak 5. 6. Uzorita; follow-up s vremenom doručka; napomena u stay.hr „smješten ParkCity“ |
| **Odbija** | EN/DE: otkaz 6725524010 putem Booking.com + podrška; stay.hr `canceled` nakon potvrde |
| **Bez odgovora do 16:00** | Poziv +43 664 3379293; ponovljena poruka extranet |

### Follow-up — prihvaćeno ParkCity (DE)

```
Vielen Dank, Herr Pohler. Ihr Check-in heute Abend: ParkCity Rooms, Bana Josipa Jelačića 62, Šibenik (Tel. +385 98 932 2440). Frühstück am 5. Juni bei uns — bitte teilen Sie uns Ihre gewünschte Uhrzeit mit. Toni, +385 99 838 8513
```

### Follow-up — doručak 08:00 potvrđen (DE)

Gost (WhatsApp): *Hallo, Frühstück bitte um 08:00 Uhr. Lg*

```
Perfekt, Herr Pohler — Frühstück am 5. Juni um 08:00 Uhr bei uns (Luxury Room Uzorita B&B). Wir freuen uns auf Sie. Bei Fragen: Toni, +385 99 838 8513
```

### Follow-up — odbijeno / otkaz (DE)

```
Schade, dass die Alternative nicht passt. Bitte stornieren Sie Reservierung 6725524010 über Booking.com; unsere Support-Meldung hilft bei erlassener Stornogebühr. Bei Fragen: +385 99 838 8513. Toni
```

---

## Operativni checklist

- [x] Podaci gosta provjereni (814 / 6725524010)
- [x] Email gostu (DE+EN) poslan na hpohle.408216@guest.booking.com (tenant SMTP)
- [ ] Poruka na Booking.com extranet Messages (opcionalno — Channex API 403)
- [ ] Booking.com support / disruption prijavljeno (copy-paste: [booking-com-report-6725524010-overbooking.txt](booking-com-report-6725524010-overbooking.txt) — **5. 6. 2026. tekst provjeren, čeka ručni submit u extranetu**)
- [x] Napomena OVERBOOKING u stay.hr (814)
- [ ] ParkCity: telefonski dogovor check-in
- [ ] Wolfgang: check-in R1+R2 (stay.hr usklađen s PDF-om); Helmuth: **ne** check-in Uzorita
- [x] PDF import: `5036489024.pdf`, `6725524010.pdf` (4. 6. 2026.)
- [x] Channex R1 availability push (4.–5. 6.)
- [x] Odgovor gosta dokumentiran (ParkCity prihvaćeno; doručak **08:00** 5. 6.)

---

## Povezani dokumenti

- [situacija-svibanj-2026-r3-r6-overbooking.md](situacija-svibanj-2026-r3-r6-overbooking.md)
- [booking-com-konflikt-dvostruka-rezervacija.md](../booking-com-konflikt-dvostruka-rezervacija.md)
- [channex-uzorita-booking-channel.md](../integrations/channex-uzorita-booking-channel.md) — guest messaging 403 → aktivirati Messaging app
