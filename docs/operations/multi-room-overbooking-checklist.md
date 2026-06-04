# Multi-room i overbooking — operativni checklist

**Objekt:** Luxury Room Uzorita B&B (`uzorita`, tenant #2)  
**Kanal:** Channex → Booking.com (property ID `4181954`)

Ovaj runbook sprječava tip overbookinga iz 2026.: PMS ima manje soba nego Booking.com → Channex ne zatvara sve listinge → B.com prodaje istu noć dvaput.

---

## Kad koristiti

- Nova rezervacija s **2+ soba** ili PDF s više `Luxury Room Uzorita - R*`
- Rezervacija „cijeli objekt“ (4 sobe: R1, R2, R3, R6)
- Nakon **PDF importa** koji mijenja dodjelu soba
- Dnevno (automatski): Celery `detect_overbooking` + push ako ima konflikata

---

## Checklist — isti dan kad stigne rezervacija

1. **Booking.com PDF** (extranet → Print confirmation) spremi u `.imports/` ili importaj u Reception / CLI.
2. U stay.hr provjeri:
   - `units_count` = broj soba na PDF-u
   - `ReservationUnit` — svaka soba ima `unit` (R1, R2, R3, R6), ne samo jedna
   - `import_source=booking_pdf` za autoritativne multi-room (Channex ne smije smanjiti broj soba)
3. **Channex inventar** (automatski nakon PDF importa u stay.hr od 6/2026.; ručno ako treba):
   ```bash
   docker compose exec django python manage.py channex_ari_full_sync uzorita
   ```
4. **Detekcija konflikta**:
   ```bash
   docker compose exec django python manage.py detect_overbooking --tenant-id 2 --from-date YYYY-MM-DD
   ```
5. Ako `detect_overbooking` > 0 ili reception push „Overbooking“ — **ne check-in** kasnijeg gosta na zauzetu sobu; otkaz / relocacija prema [booking-com-konflikt](booking-com-konflikt-dvostruka-rezervacija.md) uzorcima.

---

## Reconcile (tjedno ili pri sumnji)

```bash
docker compose exec django python manage.py reconcile_booking_units --tenant-id 2
```

Prikazuje rezervacije gdje `units_count` ili Channex `rooms[]` ne odgovara broju `ReservationUnit` u stay.hr.

---

## Channex — Messaging i Booking CRS (ručno u Channex UI)

Bez ovoga API vraća **403** za poruke i otkaz rezervacije:

| App | Svrha |
|-----|--------|
| **Messaging & Reviews** | `send_channex_booking_message` → B.com Poruke |
| **Booking CRS** | `cancel_channex_booking` → otkaz na kanalu |

Vidi [channex-uzorita-booking-channel.md](../integrations/channex-uzorita-booking-channel.md).

Email na `@guest.booking.com` (tenant SMTP) radi i bez Messaging appa; extranet „Poruke“ može ostati prazan.

---

## Otvoreni B.com otkazi (stanje 4. 6. 2026.)

stay.hr lokalno `canceled` — **extranet/support još potreban** na Booking.com:

| Booking | Gost | Dokument |
|---------|------|----------|
| 5238895494 | Pierre LE VAILLANT | [booking-com-konflikt-2026-07-24-overbooking.md](../booking-com-konflikt-2026-07-24-overbooking.md) |
| 5398124917 | Eduardo de las Heras | isto |
| 5461475045 | Sandy Bowser | [situacija-srpanj-2026-r2-r3-overbooking.md](situacija-srpanj-2026-r2-r3-overbooking.md) |
| 6754897669 | David Martín Céspedes | isto |

---

## Povezani dokumenti

- [situacija-lipanj-2026-r1-helmuth-overbooking.md](situacija-lipanj-2026-r1-helmuth-overbooking.md)
- [situacija-srpanj-2026-r2-r3-overbooking.md](situacija-srpanj-2026-r2-r3-overbooking.md)
- [booking-com-konflikt-2026-07-24-overbooking.md](../booking-com-konflikt-2026-07-24-overbooking.md)
- [situacija-svibanj-2026-r3-r6-overbooking.md](situacija-svibanj-2026-r3-r6-overbooking.md)
