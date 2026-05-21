# Booking.com XLS import

Uvoz rezervacija iz Booking.com exporta (Excel 97–2003, `.xls`) u stay.hr. Svaki red = jedna rezervacija; ključ je **broj rezervacije Booking** (`external_id` / `booking_code`).

**Media / datoteke:** export može biti bilo gdje na disku (npr. `Rezervacija`, `Reservation 2026-05-20 to 2026-05-21.xls`). U repou se XLS exporti obično **ne commitaju**.

---

## Brzi start

```bash
# Pregled bez pisanja u bazu
/opt/stacks/stay.hr/scripts/import_booking_xls.sh --dry-run "/path/to/export.xls"

# Samo nove rezervacije (zadano)
/opt/stacks/stay.hr/scripts/import_booking_xls.sh \
  --tenant-id 2 --property-slug uzorita \
  "/opt/stacks/stay.hr/Rezervacija"

# Postojeće: dopuni samo prazna polja (preporučeno za ponovni import)
/opt/stacks/stay.hr/scripts/import_booking_xls.sh --fill-empty \
  --tenant-id 2 --property-slug uzorita \
  "/opt/stacks/stay.hr/Rezervacija"
```

Ručno (Docker):

```bash
docker compose run --rm -v /opt/stacks/stay.hr:/host/stay:ro django \
  python manage.py import_booking_xls \
  "/host/stay/Rezervacija" \
  --tenant-id 2 --property-slug uzorita --fill-empty
```

---

## Tri načina rada s postojećim rezervacijama

| Način | Zastavica | Ponašanje |
|--------|-----------|-----------|
| **Preskoči** | *(zadano)* | Ako rezervacija već postoji (`external_id` ili `booking_code`), red se **ne dira**. Uvozi se samo novi Booking broj. |
| **Dopuni prazno** | `--fill-empty` | Postojeća rezervacija se **ne prepisuje**. Popunjavaju se samo polja koja su trenutno prazna na rezervaciji i na gostu. |
| **Prepiši** | `--allow-update` | Cijela rezervacija i gosti se ažuriraju iz XLS-a (oprezno: može promijeniti status, bookera, dodati goste). |

**Ne miješaj** `--fill-empty` i `--allow-update` u istom pozivu.

### Što `--fill-empty` radi u praksi

**Rezervacija**

- Traži postojeći zapis po `external_id`, pa po `booking_code`.
- Za svako polje iz XLS-a: upis **samo ako** je u bazi prazno (`null`, `""`, prazan string).
- **Ne mijenja** `status` ako je gost već `checked_in` ili `checked_out`.
- Ako `external_id` nedostaje, postavlja ga iz Booking broja.

**Gost**

- Traži gosta po imenu/prezimenu (parsirano iz XLS-a).
- Ako postoji: dopunjava samo prazna polja (npr. `email`, `nationality`).
- Ako **već ima** barem jednog gosta na rezervaciji, a ime iz XLS-a ne odgovara nikome — **ne dodaje** novog gosta (izbjegava duplikate tipa „Andre“ / „André“).
- Ako rezervacija **nema** goste, kreira gosta iz XLS-a.

**Sobe / jedinice**

- Pri `--fill-empty` na postojećoj rezervaciji **ne** radi se ponovni sync soba iz XLS-a (postojeći raspored ostaje).

**Nova rezervacija**

- Puna kreacija: rezervacija, gosti, sobe, iznosi — kao i prije.

---

## Filtriranje po datumu

Ako ime datoteke sadrži raspon, npr. `Reservation 2026-05-20 to 2026-05-21.xls`, uvoz se automatski ograniči na check-in u tom rasponu.

Ručno:

```bash
--check-in-from 2026-05-20 --check-in-to 2026-05-21
```

Datoteka bez datuma u imenu (npr. `Rezervacija`) → uvozi **sve** redove iz lista.

---

## Mapiranje polja (XLS → stay.hr)

| XLS (HR/EN) | Polje |
|-------------|--------|
| Broj rezervacije / Book number | `external_id`, `booking_code` |
| Nositelj rezervacije / Booked by | `booker_name`, primarni gost |
| Ime(na) gosta | dodatni gosti |
| Prijava / Check-in | `check_in` |
| Odjava / Check-out | `check_out` |
| Vrsta jedinice / Unit type | `room_name` → `ReservationUnit` |
| Cijena / Price | `amount`, `currency` |
| Booker country, telefon, adresa, napomene, provizija, … | odgovarajuća polja |

`import_source` = `booking_xls`, `source` = `Booking.com`.

Booking status `cancelled` → `status=canceled`; inače `expected`.

---

## Push notifikacije

Samo **novo kreirane** rezervacije (`created`) pokreću Celery task `notify_new_reservation` (FCM po tenantu). Preskočene ili `--fill-empty` merge **ne** šalju push.

---

## Izlaz naredbe

```
Import done: created=1 merged=2 skipped=0 updated=0 errors=0 total=3
```

| Stat | Značenje |
|------|----------|
| `created` | Nova rezervacija |
| `merged` | Postojeća, dopunjena prazna polja (`--fill-empty`) |
| `skipped` | Postojeća, nije dirnuta (zadano) |
| `updated` | Prepisana (`--allow-update`) |
| `errors` | Red nije uvezen (vidi stderr) |

---

## Zahtjevi

- Datoteka mora biti **stari Excel `.xls`** (OLE), ne `.xlsx`.
- Tenant i property moraju postojati (`--tenant-id`, `--property-slug`).
- Sobe se mapiraju preko `unit_mapping` / naziva iz kolone „Vrsta jedinice“.

---

## Kod

| Komponenta | Put |
|------------|-----|
| Parser + logika | `backend/apps/reservations/booking_xls_import.py` |
| Management command | `backend/apps/reservations/management/commands/import_booking_xls.py` |
| Skripta | `scripts/import_booking_xls.sh` |
| Testovi | `backend/apps/reservations/tests/test_booking_xls_import.py` |

Povezano: [id-document-import.md](./id-document-import.md) (gosti, dokumenti, eVisitor).
