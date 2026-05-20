# Ručna mjesečna statistika (multi-tenant)

Omogućuje unos **povijesnih** prihoda, provizija i noćenja po mjesecu kada u bazi nema kompletnih rezervacija (pre-migracija ili ručna evidencija).

## Ponašanje

1. API `GET /api/v1/reception/statistics/monthly/?year=YYYY` zbraja rezervacije tenant-a sa statusom **`checked_in`** ili **`checked_out`** (po datumu **check-in**).
2. Ako postoji zapis **`MonthlyStatisticsOverride`** za `(tenant, godina, mjesec)`, te vrijednosti **potpuno zamjenjuju** zbroj iz rezervacija za taj mjesec (current ili previous godina u YoY usporedbi).

Isto kao Uzorita `MonthlyStatisticsOverride`, ali s **`tenant_id`** — demo i uzorita imaju odvojene override zapise.

## Django admin

**Reservations → Ručna statistika (mjesec)**

| Polje | Opis |
|-------|------|
| tenant | Obavezno (staff vidi samo svoje tenant-e) |
| year, month | npr. 2024, 3 |
| revenue | Ukupni prihod (EUR) |
| commission | Provizija Booking (opcionalno) |
| nights | Broj noćenja |
| currency | Default EUR |
| notes | Napomena (izvor podataka) |

Unique: jedan zapis po **tenant + godina + mjesec**.

## Legacy import (uzorita)

Postojeći overridei iz stare Uzorita baze (`reception_monthlystatisticsoverride`) uvoze se uz ostale legacy podatke:

```bash
docker compose exec django python manage.py migrate_uzorita_legacy
```

Ako tablica ne postoji na legacy DB, import se preskače (upozorenje u summary).

## Migracija

```bash
docker compose exec django python manage.py migrate
```

## Kod

| Što | Putanja |
|-----|---------|
| Model | `backend/apps/reservations/models.py` → `MonthlyStatisticsOverride` |
| Agregacija | `backend/apps/reservations/statistics.py` |
| Admin | `backend/apps/reservations/admin.py` |
| Legacy | `backend/apps/legacy_import/legacy_models.py`, `migrator.py` |

## Primjer

Za **svibanj 2025** na tenantu **uzorita** uneseš revenue `3580.25`, nights `45` — graf za godinu 2026 prikazuje te brojke u `months[4].previous` čak i bez rezervacija iz 2025. u stay bazi.
