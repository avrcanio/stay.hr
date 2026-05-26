# Test suite — stay.hr backend

Zadnji puni run: **2026-05-26** (Docker image `stay-hr-django:latest`, nakon uklanjanja Smoobu integracije).

## Pokretanje

### Puni suite (preporučeno)

```bash
cd /opt/stacks/stay.hr
docker compose build django
docker compose run --rm django python manage.py test \
  apps.api.tests \
  apps.core.tests \
  apps.tenants.tests \
  apps.integrations.tests \
  apps.properties.tests \
  apps.reservations.tests \
  apps.legacy_import.tests \
  -v 2
```

### Default `manage.py test` (djelomično)

```bash
docker compose run --rm django python manage.py test
```

Pronalazi samo **~53 testa** (uglavnom `api`, `core`, `tenants`). Ne uključuje automatski `integrations`, `properties`, `reservations`, `legacy_import` — koristi eksplicitne labele iznad.

### Integracije (Channex)

```bash
docker compose run --rm django python manage.py test apps.integrations.tests -v 2
```

### Channex cert (plan ispravki)

```bash
docker compose run --rm django python manage.py test \
  apps.integrations.tests.test_channex_ari \
  apps.integrations.tests.test_channex_booking_ingest \
  -v 2
```

---

## Zadnji rezultat (2026-05-20)

| Metrika | Vrijednost |
|---------|------------|
| **Ukupno** | 121 test |
| **Prošlo** | **121** |
| **Palo** | 0 |
| **Trajanje** | ~7–8 s |
| **Status** | **OK** |

### Po aplikaciji

| Modul | Prošlo | Napomena |
|-------|--------|----------|
| `apps.api.tests` | 15/15 | reception, rooms, FCM, unit serializers |
| `apps.core.tests` | 7/7 | notifications, firebase |
| `apps.tenants.tests` | 21/21 | admin scope, API apps, token encryption |
| `apps.integrations.tests` | Channex, channel manager, evisitor, webhook |
| `apps.properties.tests` | 19/19 | units, beds, bathrooms, seeds |
| `apps.reservations.tests` | 6/6 | models, statistics, notifications |
| `apps.legacy_import.tests` | 5/5 | validator bez live legacy DB |

---

## Integracije — što je pokriveno

### Channex (cert tenant `demo`)

| Datoteka | Testovi | Svrha |
|----------|---------|--------|
| `test_channex_ari.py` | 8 | full sync restrictions, **delta rate push**, outbox flush |
| `test_channex_booking_ingest.py` | 7 | webhook ingest, ack, idempotency, **revisions feed** |
| `test_channex_webhook.py` | 3 | auth header, payload |
| `test_channex_mapping.py` | 2 | room type mapping |

### Channel manager / Channex ARI

| Datoteka | Svrha |
|----------|--------|
| `test_channel_dispatch.py` | outbound sync, calendar blocks |
| `test_channel_manager_resolver.py` | `none` / `channex` validation |
| `test_channex_ari.py` | full sync, delta rate push, outbox |
| `test_channex_reservation_availability.py` | availability push |

---

## Legacy import testovi

`ValidatorTests` koristi `@override_settings(DATABASES=…)` **bez** `uzorita_legacy`, jer unit testovi provjeravaju logiku kad legacy baza nije dostupna (isti scenarij kao lokalni/CI test bez `UZORITA_DB_*`).

Za validator protiv stvarne Uzorita baze pokreni management command na serveru s postavljenim `UZORITA_DB_NAME`, ne Django unit test.

---

## Preduvjeti

- Docker Compose stack (`postgis` mreža, env iz `.env`)
- Image se gradi iz repoa (kod **nije** bind-mountan u `stay_django` — nakon izmjena uvijek `docker compose build django`)

## Povezana dokumentacija

- Channex cert: [channex-demo-property.md](../integrations/channex-demo-property.md)
- Channel manager: [channel-manager-setup.md](../operations/channel-manager-setup.md)
