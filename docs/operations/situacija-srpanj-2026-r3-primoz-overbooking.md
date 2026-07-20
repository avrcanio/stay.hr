# Situacija — overbooking R3, Primož Juhart (20.–21. srpnja 2026.)

**Objekt:** Luxury Room Uzorita B&B (tenant #2, property `uzorita`)  
**Datum dokumenta:** 20. srpnja 2026.  
**Kontakt:** Toni, +385 99 838 8513

---

## Sažetak

Booking.com overbooking na **R3** za noć **20.–21. 7. 2026.** Kasnija rezervacija **6946148952** (Primož Juhart) vs starija **5865972471** (Lada Rakigjija, R2+R3+R6).

| | Primož (AKCIJA) | Lada (OSTAJE) |
|---|---|---|
| Booking | **6946148952** | 5865972471 |
| stay.hr id | **1008** | 159 |
| Check-in/out | 20.–21. 7. 2026. | 20.–21. 7. 2026. |
| Soba B.com / stay.hr | R3 | **R2 + R3 + R6** |
| Iznos stay.hr | €105,84 | — |
| Gosti | 2 odrasla | — |
| Channex | `channex:2041c20c-…` | — |

**Rješenje:** ParkCity Rooms (~50 m) — **već rezervirano od Uzorite**; doručak 21. 7. u restoranu Uzorita; **bez dodatnog troška za gosta**. **NE check-in Uzorita** za #1008.

**Raspored soba (20. 7.):** R3 → Lada (OSTAJE) + Primož (expected, **ne** check-in Uzorita → ParkCity); R2+R6 → Lada.

Detekcija: [faza0-overbooking-audit-2026-07-20.md](faza0-overbooking-audit-2026-07-20.md).

---

## Gost — kontakt (stay.hr)

| Polje | Vrijednost |
|-------|------------|
| Ime | Primož Juhart |
| Država | **SI** (poruka: **SL**) |
| Email | pjuhar.526506@guest.booking.com |
| Tel. | +386 31 309 874 |

---

## Obavijest gostu — status

| Kanal | Status | Napomena |
|-------|--------|----------|
| Channex → Booking.com Messages API | **Poslano** 20. 7. 2026. ~08:28 UTC | `send_channex_booking_message` → `54ca61cd-4a6e-4ec3-8684-2c040e6c8a07` (HTTP 200); tekst: [booking-message-6946148952-primoz-parkcity-sl.txt](booking-message-6946148952-primoz-parkcity-sl.txt) |
| WhatsApp Auto check-in welcome | **Poslano** 20. 7. 2026. ~08:47 UTC | `send_welcome_template_for_reservation(#1008)` → `sent`; wamid `wamid.HBgLMzg2MzEzMDk4NzQVAgARGBI1MTI0MDk3MTYxREY2MzcwRTYA` |
| WhatsApp freeform ParkCity SL | **Nije poslano** | Meta 24h CS window zatvoren (nema inbound). Welcome template **ne** otvara window. Čekati gostov tap Auto check-in → session ACTIVE → onda `send_guest_message` / `GuestMessageChannel.WHATSAPP` istim SL tekstom |
| Email na guest.booking.com | Nije potrebno | Fallback nije korišten (Channex OK) |
| Booking.com extranet → Poruke | Nije potrebno | Fallback nije korišten (Channex OK) |

---

## ParkCity Rooms (alternativa)

| Polje | Vrijednost |
|-------|------------|
| Naziv | ParkCity Rooms |
| Adresa | Bana Josipa Jelačića 62, 22000 Šibenik |
| Tel. | +385 98 932 2440 |
| Booking.com | [parkcity-rooms](https://www.booking.com/hotel/hr/parkcity-rooms.hr.html?checkin=2026-07-20&checkout=2026-07-21) |
| Kapacitet 20.–21. 7. | **Rezervirano od Uzorite** (2 odrasla) |
| Broj potvrde | **Nema** — gost kaže ime **Primož Juhart** + da je **Uzorita napravila rezervaciju** |
| Doručak | **21. 7. 2026.** u Luxury Room Uzorita B&B (2 odrasla, uključeno) |

**Koordinacija:** ParkCity već dogovoren; pri check-inu gost se predstavi imenom i prezimenom te da je rezervaciju uredila Uzorita.

---

## Prijava Booking.com support / disruption (opcionalno)

**Property ID:** 4181954  
**Rezervacija u sporu (kasnija):** 6946148952  
**Referenca (starija):** 5865972471  
**Datum konflikta:** 20.–21. 7. 2026.  
**Soba:** Deluxe Triple Room R3

Nije blokator za večeras — ParkCity rješenje je već dogovoreno.

### Tekst za extranet (Help / Report issue / disruption)

```
Overbooking — same physical room R3 for the same night.

Property: Luxury Room Uzorita B&B (4181954)
Conflict night: 20–21 July 2026

Incumbent (earlier booking): 5865972471 — Lada Rakigjija — R2 + R3 + R6.
Later booking (action required): 6946148952 — Primož Juhart — R3.

We cannot host Mr Juhart in R3 at our property tonight due to the earlier reservation.
We have already arranged alternative accommodation at ParkCity Rooms (neighbour, ~50 m / 1 min walk) plus breakfast at our B&B on 21 July at no extra cost to the guest.

Please assist with relocation / inventory correction for 6946148952 so R3 is not sold twice.

Contact: Toni, +385 99 838 8513, room_reservations@uzorita.hr
```

- [ ] Prijava poslana u Booking.com extranetu (opcionalno)
- [ ] Broj tiketa (upisati): _______________

---

## Poruke gostu (copy-paste)

### SL (primarno — SI)

Kanal: Channex → B.com Messages (ili email / extranet fallback).

```
Spoštovani gospod Juhart,

iskreno se opravičujemo za nevšečnosti. Zaradi tehničnega overbookinga na Booking.com vas nocoj (20.–21. julij 2026) žal ne moremo nastaniti v sobi, ki je bila potrjena v Luxury Room Uzorita B&B (Deluxe Triple Room R3). To ni vaša napaka — isto sobo že zaseda zgodnejša potrjena rezervacija.

Za vas smo že uredili rešitev brez dodatnih stroškov:

• Prenočišče v ParkCity Rooms (približno 50 metrov / 1 minuta hoje od nas)
  Naslov: Bana Josipa Jelačića 62, 22000 Šibenik
  Tel.: +385 98 932 2440
  https://www.booking.com/hotel/hr/parkcity-rooms.hr.html?checkin=2026-07-20&checkout=2026-07-21

  Sobo smo rezervirali mi (2 odrasla). Ob prijavi povejte ime in priimek — Primož Juhart — ter da je rezervacijo naredila Uzorita. Številka potrditve ni potrebna.

• Zajtrk 21. julija v naši restavraciji v Luxury Room Uzorita B&B (vključeno za vas)

Prosimo, odgovorite tukaj s predvidenim časom prihoda, če lahko. Za vprašanja: Toni, +385 99 838 8513.

Lep pozdrav,
Toni
Luxury Room Uzorita B&B
```

---

## stay.hr — nakon slanja / potvrde dolaska

| Akcija | Status (20. 7. 2026.) |
|--------|----------------------|
| Notes **#1008** | OVERBOOKING riješen; ParkCity; Channex msg ~08:28 UTC; WA welcome ~08:47 UTC; freeform ParkCity čeka inbound; **NE check-in Uzorita** |
| Status **#1008** | **`canceled`**; R3 `ReservationUnit` uklonjen; `units_count=0` |
| **#159** | Ostaje **R2+R3+R6** `expected`; notes: R3 konflikt #1008 riješen ParkCity |
| `detect_overbooking --tenant-id 2 --from-date 2026-07-20` | **0** |

---

## Operativni checklist

- [ ] ParkCity: dogovor bez broja potvrde — gost: ime Primož Juhart + „Uzorita rezervirala“ (2 odrasla, 20.–21. 7.)
- [x] Channex poruka poslana (#1008) — `54ca61cd-4a6e-4ec3-8684-2c040e6c8a07` (20. 7. 2026. ~08:28 UTC)
- [x] Ako 403 → email + extranet — **nije primijenjeno** (Channex HTTP 200)
- [x] WhatsApp Auto check-in welcome (#1008) — `sent` ~08:47 UTC
- [ ] WhatsApp freeform ParkCity SL — **blokirano** (24h CS zatvoren); nakon gostovog Auto check-in tapa
- [x] stay.hr: notes + ukloniti R3 / canceled na #1008
- [x] Notes na #159: R3 konflikt #1008 riješen ParkCity
- [x] `detect_overbooking --tenant-id 2 --from-date 2026-07-20` → 0 konflikata
- [ ] Lada (#159): check-in R2+R3+R6 kao planirano; Primož: **ne** check-in Uzorita
- [ ] (Opcionalno) B.com support / disruption ticket za `6946148952` — nije blokator za večeras

---

## Povezani dokumenti

- [faza0-overbooking-audit-2026-07-20.md](faza0-overbooking-audit-2026-07-20.md)
- [situacija-lipanj-2026-r1-helmuth-overbooking.md](situacija-lipanj-2026-r1-helmuth-overbooking.md)
- [multi-room-overbooking-checklist.md](multi-room-overbooking-checklist.md)
- [channex-uzorita-booking-channel.md](../integrations/channex-uzorita-booking-channel.md) — guest messaging API
