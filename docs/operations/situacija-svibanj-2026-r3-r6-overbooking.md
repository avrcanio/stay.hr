# Situacija — overbooking R3/R6 (22.–25. svibnja 2026.)

**Objekt:** Luxury Room Uzorita B&B (tenant #2, property `uzorita`)  
**Datum dokumenta:** 23. svibnja 2026.  
**Kontakt:** Toni (manager), tel. +385 99 838 8513

---

## Sažetak

U kratkom razdoblju **22.–25. 5. 2026.** dogodilo se više preklapanja na **R3** i **R6** zbog:

1. XLS importa koji je generički `Deluxe King Room` mapirao na **R1** (povijesno — većinom riješeno).
2. Stvarnog preklapanja **Sauvagere (2 sobe)** vs **Hoferica** i **Vlemminx** na **R3**.
3. Otkazanog Smoobu blocka na **R6** (API greška) → prodaja **Mihaljević** na R6 → operativni kaos.
4. Nemogućnosti premještanja Booking.com rezervacije između apartmana putem Smoobu API-ja.

---

## Ključne rezervacije

| Booking | Gost | Datumi | Booking.com soba | stay.hr (operativno) | Smoobu ID | Status |
|---------|------|--------|------------------|----------------------|-----------|--------|
| **6541736653** | Etienne Sauvagere | 21.–24.5. | R2 + R3 | R2 + R3 | — | OSTAJE |
| **5213202593** | Eva Hoferica | 22.–23.5. | R3 (i R1 u Smoobu) | R3 / issue | 139911907 (R3), 139910937 (R1) | **checked_in** — eksterni apartman |
| **5272845192** | Benny Vlemminx | 23.–25.5. | Deluxe Triple **R3** | **R6** (interno) | **139911912** (R3) | expected |
| **6250886338** | Kristina Mihaljević | 23.–24.5. | Deluxe Double **R6** | R6 | **140594307** (R6) | **canceled** — PDF lock (23.5.) |

PDF-ovi: `.imports/5272845192.pdf`, `.imports/6250886338.pdf`, `.imports/6541736653.pdf`

---

## Kronologija (23. 5. 2026.)

| Vrijeme (okvirno) | Događaj |
|-------------------|---------|
| **07:12** | Ručno blokiran **R6** 23.–25.5. (Smoobu block **140587217**) — namjena: Vlemminx |
| **07:17** | **Greška (agent):** API `unblock_apartment_dates` otkazao block **140587217**; kreiran duplikat Website **140587672** |
| **07:18+** | Vlemminx interno na R6 u stay.hr; Smoobu Booking i dalje na **R3** |
| **10:40** | Nova rezervacija **6250886338** Mihaljević na **R6** (Booking.com) — R6 bio otvoren nakon otkazanog blocka |
| Kasnije | Duplikat **140587672** otkazan u Smoobu |
| Operativa | Mihaljević → dogovor **ParkCity Rooms** (susjed); gost odbio alternativu |
| Komunikacija | Booking.com disruption forma (relocate); poruke gostici na HR |
| **ParkCity** | Rezervacija kod susjeda dogovorena, zatim **otkazana** — gostici obavijest |

---

## Detalji po rezervaciji

### 5213202593 — Eva Hoferica (ISSUE)

| Polje | Vrijednost |
|-------|------------|
| Check-in/out | 22.–23.5.2026 |
| Problem | Preklapanje **R3** s Sauvagere (6541736653) |
| Operativa | Gost **nije** u R3 — smješten u **eksterni apartman** (iznajmljen) |
| stay.hr | `checked_in`, napomena ISSUE; **ne checkout** dok se ne riješi dokumentacija |
| Smoobu | Dva unosa: R1 + R3 za isti booking |

**Akcija:** Ostaviti kao otvoreni issue u sustavu; trošak eksternog smještaja za internu evidenciju.

---

### 5272845192 — Benny Vlemminx

| Polje | Vrijednost |
|-------|------------|
| Check-in/out | 23.–25.5.2026 (2 noći) |
| Booking.com | Deluxe Triple Room (**R3**) — PDF potvrđuje |
| Cijena / provizija | €160.20 / €30.92 |
| Email | bvlemm.423495@guest.booking.com |
| stay.hr (cilj) | **R6** — `Uzorita R6`, napomena: *Interno preseljen s R3 na R6* |
| Smoobu | **139911912** na **Uzorita R3** — **ne dirati** bez eksplicitne potvrde |

**Napomena:** Smoobu sync može vratiti sobu na R3 u bazi. Mitigacija: `xls_imported_at` bump nakon ručnog upserta.

**Parking:** Gost traži besplatan parking po dostupnosti (PDF).

---

### 6250886338 — Kristina Mihaljević

| Polje | Vrijednost |
|-------|------------|
| Check-in/out | 23.–24.5.2026 (1 noć) |
| Booking.com | Deluxe Double Room (**R6**) — PDF |
| Cijena / provizija | €88.11 / €17.01 |
| Država | BA |
| Email | kmihal.952458@guest.booking.com |
| Tel. | +387 177726 |
| Smoobu | **140594307** na R6 |
| stay.hr status | **canceled** (`booking_pdf`, `cancelled_by_guest`, PDF lock 23.5.2026) |

#### Komunikacija s gostom

1. **Prva poruka (EN):** overbooking → alternativa ParkCity Rooms + doručak kod nas.
2. **Odgovor gosta:** alternativa **ne odgovara**.
3. **Druga poruka (HR):** nemamo kapacitet; molimo otkaz putem Booking.com + kontakt podrške.
4. **Treća poruka (HR):** soba u **ParkCity Rooms** je **otkazana**; i dalje ne možemo ugostiti; otkaz 6250886338 putem Booking.com.

#### Alternativni smještaj (ParkCity Rooms)

| Polje | Vrijednost |
|-------|------------|
| Naziv | ParkCity Rooms |
| Adresa | Bana Josipa Jelačića 62, 22000 Šibenik |
| Tel. | +385 98 932 2440 |
| Booking.com | [parkcity-rooms](https://www.booking.com/hotel/hr/parkcity-rooms.hr.html) |
| Status | Rezervacija kod susjeda **dogovorena**, zatim **otkazana** |

#### stay.hr napomena (u bazi)

```
Alternativni smještaj: ParkCity Rooms — otkazano.
Gost odbio alternativu; otkaz putem Booking.com.
PDF: .imports/6250886338.pdf
```

Rezervacija u stay.hr: **canceled**, PDF lock (`import_source=booking_pdf`), €88.11 / provizija €17.01.

---

### 6541736653 — Etienne Sauvagere (OSTAJE)

| Polje | Vrijednost |
|-------|------------|
| Check-in/out | 21.–24.5.2026 |
| Sobe | **R2** (Deluxe King) + **R3** (Deluxe Triple) — PDF |
| Iznosi po sobi | €165.90 + €186.90 = €352.80 |
| Email (treba ažurirati) | esauva.758524@guest.booking.com (PDF) |

Drži **R3** do 24.5. — legitimno preklapanje s Vlemminx (Booking R3) 23.–24.5.

---

## Overbooking u stay.hr (stanje nakon ažuriranja)

| Soba | Overlap | OSTAJE | AKCIJA / issue |
|------|---------|--------|----------------|
| **R3** | 22.–23.5. | 6541736653 Sauvagere | 5213202593 Hoferica (eksterni apartman) |
| **R3** | 23.–24.5. | 6541736653 Sauvagere | 5272845192 Vlemminx (Booking R3, interno R6) |
| **R6** | 23.–24.5. | 5272845192 Vlemminx (interno R6) | 6250886338 Mihaljević **canceled** |

Naredba:

```bash
docker compose exec django python manage.py detect_overbooking --tenant-id 2 --from-date 2026-05-22
```

---

## Smoobu — što NE raditi bez potvrde

- **Ne** zvati `unblock_apartment_dates` na aktivnim blockovima.
- **Ne** kreirati duplikat rezervacije (Website channel) za Booking.com goste.
- **Ne** DELETE/otkazivati Booking.com rezervacije bez operativne potrebe.
- **PUT** rezervacije **ne mijenja** `apartmentId` — premještaj samo u Smoobu UI.

### Smoobu ID-evi (referenca)

| ID | Opis | Status |
|----|------|--------|
| 140587217 | Block R6 23.–25.5. (Vlemminx) | **cancellation** (otkazan greškom) |
| 140587672 | Duplikat Website R6 | **cancellation** |
| 139911912 | Vlemminx Booking.com **R3** | aktivna |
| 140594307 | Mihaljević Booking.com **R6** | **cancellation** |
| 139911907 / 139910937 | Hoferica R3 / R1 | aktivna |

---

## Operativne akcije (checklist)

- [x] **Mihaljević:** stay.hr ažuriran (PDF otkaz, `canceled`, PDF lock 23.5.)
- [ ] **Mihaljević:** podrška Booking.com za refund (ako treba)
- [ ] **ParkCity:** potvrditi da je njihova rezervacija otkazana
- [ ] **Vlemminx:** check-in u **R6** (interno); Smoobu UI po potrebi; R3 osloboditi za Sauvagere 23.–24.
- [ ] **Hoferica:** issue dokumentiran; eksterni apartman
- [ ] **R6 block:** po potrebi ponovno blokirati **24.–25.5.** (23.–24. zauzeto Vlemminx; Mihaljević otkazan)
- [ ] **Sauvagere:** ažurirati email/proviziju iz PDF-a ako treba

---

## Uzrok prodaje Mihaljević na R6

1. Block **140587217** kreiran u **07:12** za Vlemminxa.
2. Block **otkazan u 07:17** (agent API — `unblock_apartment_dates`).
3. R6 **otvoren** na Booking.com kanalu.
4. Rezervacija **6250886338** u **10:40** — legitimna Booking.com prodaja.

**5272845192 nikad nije bila na R6 u Smoobu** — samo block je trebao zatvoriti kalendar; rezervacija je ostala na R3.

---

## Povezani dokumenti

- [booking-com-konflikt-dvostruka-rezervacija.md](../booking-com-konflikt-dvostruka-rezervacija.md) — Djouali / Wiśniewski R1 (srpanj 2026.)
- [booking-xls-import.md](../development/booking-xls-import.md) — mapiranje soba iz XLS
- PDF importi: `.imports/5272845192.pdf`, `.imports/6250886338.pdf`, `.imports/6541736653.pdf`

---

## Poruke gostici (Mihaljević) — arhiva

### Otkaz ParkCity (HR, kratko)

Poštovana gospođo Mihaljević,

alternativni smještaj u **ParkCity Rooms** za 23.–24. svibnja **otkazan** je i više nije dostupan. I dalje Vas ne možemo ugostiti u Luxury Room Uzorita B&B.

Molimo da otkažete rezervaciju **6250886338** putem Booking.com i kontaktirate njihovu podršku.

Srdačan pozdrav,  
Toni, Luxury Room Uzorita B&B, +385 99 838 8513
