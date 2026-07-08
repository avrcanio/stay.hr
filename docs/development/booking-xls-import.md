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
- Ako **već ima** barem jednog gosta na rezervaciji, a ime iz XLS-a ne odgovara nikome — **ne dodaje** novog imenovanog gosta (izbjegava duplikate tipa „Andre“ / „André“).
- Ako rezervacija **nema** goste, kreira gosta iz XLS-a.
- Nakon sync-a imenovanih gostiju: ako je `adults_count` veći od broja postojećih gostiju, dodaju se placeholderi **`Novi gost`** (samo nedostajući odrasli slotovi; djeca se ne dodaju automatski).

**Sobe / jedinice**

- Pri `--fill-empty` na postojećoj rezervaciji sobe se **syncaju samo ako** XLS ima **više** soba nego `ReservationUnit` u stay.hr (npr. B.com R1+R2, PMS samo R2). PDF-lock rezervacije se ne diraju.
- Kad se sobe dopune, automatski se queue-a Channex ARI push (sprječava channel overbooking).

**Nova rezervacija**

- Puna kreacija: rezervacija, gosti (imenovani + placeholderi prema `adults_count`), sobe, iznosi — kao i prije.

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

## PDF lock (najjači izvor)

Ručni uvoz iz Booking.com **PDF potvrde** označava rezervaciju poljem `pdf_imported_at` i `import_source=booking_pdf`. Takva rezervacija je **zaključana** protiv automatskih kanala.

| Izvor | Ponašanje |
|--------|-----------|
| Smoobu sync (normalan update) | Preskoči (`pdf_locked`) |
| Smoobu sync (cancellation) | Samo `status=canceled` + `canceled_at` + Smoobu metadata |
| XLS `--allow-update` / `--fill-empty` | Preskoči (`pdf_locked`) |
| Ručni PDF upsert | `upsert_reservation_from_xls_row(..., existing_mode='overwrite', authoritative_pdf=True)` |

Prioritet izvora:

```text
PDF (booking_pdf) > XLS (booking_xls) > Smoobu (smoobu)
```

Za PDF re-import iz shella:

```python
upsert_reservation_from_xls_row(
    tenant=tenant,
    property=prop,
    row=row,
    existing_mode="overwrite",
    authoritative_pdf=True,
)
```

Modifikacija na Booking.com (bez otkaza) zahtijeva novi ručni PDF upsert.

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
| Reconcile domain | `backend/apps/reservations/reports/booking_reconcile*.py` |
| Reception API | `backend/apps/api/reception_booking_reconcile_views.py` |

Povezano: [id-document-import.md](./id-document-import.md) (gosti, dokumenti, eVisitor).

---

## Reconcile UI (upload → diff → apply)

Ručni CLI (`import_booking_xls`, `--fill-empty`) i dalje vrijedi za batch poslove. Za operativni rad s exportom po periodu koristite **Reconcile UI** — isti parser i ista `upsert` pravila (`pdf_locked`, `stale_xls`, zaštita statusa).

| Sučelje | URL / put |
|---------|-----------|
| **Reception** | [`/reports/booking-reconcile`](https://app.stay.hr/reports/booking-reconcile) — API: `POST /api/v1/reception/reports/booking-reconcile/compare/` (multipart `.xls`), `POST .../apply/` (JSON snapshot + odabrani redovi) |
| **Django admin** | `/admin/reservations/reservation/booking-reconcile/` — gumb „Usporedi Booking export” na changelistu rezervacija (tenant staff vidi samo svoj tenant) |

**Tok:** upload Booking `.xls` → usporedba s bazom po Booking broju → pregled diffa (provizija, iznos, datumi, status informativno) → odabir ispravaka → **Primijeni odabrano (dopuni prazno)** (zadano) ili **Prepiši** (s potvrdom). Nedostajuće rezervacije (`missing_in_stay`) mogu se uvesti cijelim redom.

**Domain (frozen contract):** `backend/apps/reservations/reports/booking_reconcile_types.py` — `BookingReconcileResult`. Compare/apply: `booking_reconcile.py`, `booking_reconcile_apply.py`. Snapshot u Django cacheu (1 h, ključ `booking_reconcile:v1:{uuid}`).

**Testovi:** `test_booking_reconcile_types.py`, `test_booking_reconcile.py`, `test_booking_reconcile_apply.py`, `test_reception_booking_reconcile.py`.

### Production readiness (v1)

| Tema | Ponašanje |
|------|-----------|
| **Snapshot** | `meta`: `tenant_id`, `property_id`, `content_sha256`, `created_at`, `row_count`, TTL 1 h. Apply odbija snapshot drugog tenanta/objekta (`snapshot_scope_mismatch`). |
| **Atomicnost** | Cijeli apply u `transaction.atomic()`. Očekivani skipovi (pdf_locked, nothing_to_apply, …) ne prekidaju batch. Neočekivana iznimka → rollback cijelog apply poziva. |
| **Concurrency** | `select_for_update()` na rezervaciji pri apply-u. Dupli fill_empty na popunjenom polju → `nothing_to_apply` (idempotentno). v2: `reservation_fingerprints` u snapshotu → apply odbija s `reservation_changed_since_compare` ako se rezervacija promijenila od compare-a. |
| **Re-compare (v2 P1)** | Admin gumb „Ponovno usporedi (iz snapshota)” i Reception `POST .../recompare/` — `recompare_from_snapshot()` bez ponovnog uploada. |
| **Audit** | `logger.info` po redu + sažetak (`applied_by`, snapshot_id, booking_code, reservation_id, mode, fields, reason). Reception: `api_app:…`; admin: `admin:username`. |
| **Decimal diff** | Usporedba nakon `quantize(0.01)` — `100` i `100.00` nisu razlika. |
| **Datumi** | Compare koristi samo `date` (check_in/check_out); nema datetime usporedbe u v1 diff poljima. |
| **Veličina snapshota** | Log upozorenje ako `row_count ≥ 3000`. Upload limit 5 MB (API). |
| **API** | Serializer je additive-only; novi JSON ključevi ne lome postojeće klijente. |

**Ručna regresija (pre mergea)** — obavezno na stvarnom Booking `.xls` (npr. Uzorita lipanj 2026). Admin: `/admin/reservations/reservation/booking-reconcile/`.

#### A. Compare (prvi upload)

1. Objekt + period (check-out 2026-06-01 … 2026-06-30) + upload `.xls` → **Usporedi**.
2. Sažetak: brojevi `matched`, `missing_in_stay`, `parse_errors` imaju smisla.
3. **Invariant (bez period filtera):** `matched + missing_in_stay + parse_errors ≈ broj redova u XLS-u`.
4. **S period filterom:**
   - `missing_in_booking` = samo Stay rezervacije u periodu (checked_out / no_show, imaju Booking broj).
   - Rezervacije **izvan** perioda ne smiju se pojaviti kao Stay-only.
5. Log: `event=booking_reconcile.compare` + `tenant_id`, `property_id`, `snapshot_id`, brojači.

#### B. fill_empty

1. Označi red s diffom na proviziji (bez `pdf_locked`).
2. **Dopuni prazno** → **Primijeni odabrano**.
3. Ponovni compare istim `.xls`:
   - diff na tom redu **nestao**
   - `matched` isti
   - `fixable_rows` **manji**
   - ako je provizija bio jedini financijski diff: Booking i Stay total provizije/iznosa **usklađeni** u summaryju.

#### C. overwrite

1. Red s diffom na amount → **Prepiši** + **Potvrdi prepisivanje** → Apply.
2. Ponovni compare: amount diff gone; summary totals usklađeni.

#### D. pdf_locked

1. Red s `(blok: pdf_locked)` → Apply.
2. Rezultat: `preskočeno (pdf_locked)`; polje u bazi **nepromijenjeno**.

#### E. Snapshot istekao

1. Compare → zabilježi da apply forma radi.
2. Obriši snapshot iz cachea ili pričekaj TTL (1 h).
3. Apply → `snapshot_not_found`; **nema** djelomične primjene.

   ```bash
   docker compose exec django python manage.py shell -c \
     "from django.core.cache import cache; cache.delete('booking_reconcile:v1:SNAPSHOT-UUID')"
   ```

#### F. Permissions (tenant staff)

1. Staff vidi samo propertyje svog tenanta.
2. Cross-tenant apply s tuđim snapshotom → `snapshot_scope_mismatch` (API/admin).

#### G. Logovi (jedan uspješan apply)

Svaki red mora imati `event=booking_reconcile.apply` i: `applied_by`, `tenant_id`, `property_id`, `booking_code`, `reservation_id`, `mode`, `snapshot_id`, `applied`/`reason`. Na kraju: `event=booking_reconcile.apply_complete`.

---

### Regresija Uzorita — lipanj 2026 (2026-07-08)

**Referentni export**

| Polje | Vrijednost |
|-------|------------|
| Naziv | `Check-out 2026-06-01 to 2026-06-30.xls` |
| Put na serveru | `/opt/stacks/stay.hr/.imports/Check-out 2026-06-01 to 2026-06-30.xls` |
| SHA-256 | `72b972838b35e36111b9e14ac4ea4b159e0e93d0adc7bf30cce54fc2a88af0c2` |
| Veličina | 42 496 bajtova |
| Datum testa | 2026-07-08 (Uzorita, tenant 2, property `uzorita`) |
| Parametri | os check-out, period 2026-06-01 … 2026-06-30 |

**Sažetak compare (A)**

| Metrika | Vrijednost |
|---------|------------|
| `total_rows` / XLS redovi u periodu | 68 |
| `matched` | 68 |
| `missing_in_stay` | 0 |
| `missing_in_booking` | 0 |
| `parse_errors` | 0 |
| Invariant `matched + missing_in_stay + parse_errors` | 68 ✓ |
| `rows_with_differences` | 17 |
| `fixable_rows` | 16 |

**Ishodi scenarija A–G**

| Scenarij | Ishod | Napomena |
|----------|-------|----------|
| **A — Compare** | ✓ PASS | Log `event=booking_reconcile.compare`; brojevi gore |
| **B — fill_empty** | ⊘ SKIP (dokumentirano) | Svi non-`pdf_locked` provizijski diffovi imaju već popunjenu `commission_amount` u stay.hr → `nothing_to_apply`. Jedini prazni `commission_amount` u exportu na `pdf_locked` redovima (npr. `6725524010`). Idempotentnost potvrđena na `6116305147`. |
| **C — overwrite** | ✓ PASS | `6116305147` commission overwrite 18.93 → 17.66; diff nestao; vrijednost vraćena nakon testa |
| **D — pdf_locked** | ✓ PASS | `6725524010` → `reason=pdf_locked`, podaci nepromijenjeni |
| **E — Snapshot** | ✓ PASS | `cache.delete('booking_reconcile:v1:…')` → apply `snapshot_not_found`, bez djelomične primjene |
| **F — Permissions** | ✓ PASS | `validate_snapshot_scope` → `snapshot_scope_mismatch` za tuđi tenant |
| **G — Audit** | ✓ PASS | `event=booking_reconcile.apply` + `apply_complete` s `applied_by`, poljima i razlozima |

**Merge kriterij:** A, C, D, E, F, G prošli; B dokumentiran skip (nema izvršivog fill_empty reda bez `pdf_locked` u ovom exportu).
