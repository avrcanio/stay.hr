# Deploy: sync-versions za ReservationDetail (Hospira)

Operativne upute za backend promjenu koja dodaje **per-rezervacija hash** u `GET /api/v1/reception/sync-versions/` (query param `reservation_id`). Flutter detail ekran koristi to pri resume-u umjesto uvijek punog `GET /reservations/{id}/`.

**Repo na serveru:** `/opt/stacks/stay.hr`  
**Redoslijed:** **backend prvo** → zatim novi Hospira build (`uzorita_flutter`).

---

## Što se mijenja

| Stavka | Potrebno ručno? |
|--------|-----------------|
| Nova Django migracija | **Ne** |
| Novi env varijable | **Ne** (postojeći `DJANGO_SECRET_KEY` u `.env` ostaje kao i prije) |
| Cloudflare / Traefik / DNS | **Ne** |
| Admin konfiguracija | **Ne** |
| Celery / Redis | **Ne** |
| Deploy koda na server | **Da** — `git pull` + `./scripts/deploy.sh` |

API ostaje **backward compatible**: pozivi bez `reservation_id` vraćaju isti JSON kao prije (bez polja `reservation_detail`).

---

## 1. Deploy na produkciji (Hetzner)

SSH na server:

```bash
cd /opt/stacks/stay.hr
git pull
./scripts/deploy.sh
```

`deploy.sh`:

- **rebuild-a Django image** ako su se promijenile migracije **ili backend Python kod** (`backend/**/*.py`, `requirements.txt`, `Dockerfile`) od zadnjeg builda
- inače samo `docker compose restart`
- pokreće `python manage.py check`

**Važno:** samo `docker compose restart` **ne** deploya code-only promjene — kod je u Docker imageu (`COPY backend/` u Dockerfile). Za ovu promjenu (nema migracija) `deploy.sh` mora pokazati `Rebuild required (backend source changed since last image build)`.

Očekivani kraj: `Done.` bez grešaka.

**Ručni fallback** ako rebuild nije pokrenut:

```bash
docker compose build django celery-worker celery-beat
docker compose up -d
docker compose exec -T django python manage.py check
```

**Brza potvrda u containeru** (nakon deploya):

```bash
docker compose exec -T django python manage.py shell -c \
  "import inspect; from apps.reservations.sync_versions import build_sync_versions_payload; \
   print('reservation_id' in inspect.signature(build_sync_versions_payload).parameters)"
```

Očekivano: `True`.

---

## 2. Provjera API-ja nakon deploya

Zamijeni `<TOKEN>` device tokenom recepcije (npr. Hospira tablet — isti kao u appu).

### 2a. Sync-versions bez reservation_id (postojeće ponašanje)

```bash
curl -sS -H "Authorization: Bearer <TOKEN>" \
  "https://api.stay.hr/api/v1/reception/sync-versions/?year=2026"
```

Očekivano: `200`, JSON s `reservations`, `rooms`, `statistics` — **bez** `reservation_detail`.

### 2b. Sync-versions s reservation_id (novo)

```bash
curl -sS -D - -H "Authorization: Bearer <TOKEN>" \
  "https://api.stay.hr/api/v1/reception/sync-versions/?year=2026&reservation_id=757"
```

Očekivano:

- `HTTP/2 200`
- header `ETag: W/"..."`
- JSON uključuje `"reservation_detail": "<16-znakovni hash>"`
- hash duljine **16** hex znakova (kao `reservations` / `rooms`)

### 2c. 304 Not Modified

```bash
# Prvo uzmi ETag iz 2b, zatim:
curl -sS -D - -H "Authorization: Bearer <TOKEN>" \
  -H 'If-None-Match: W/"<ETAG_IZ_2b>"' \
  "https://api.stay.hr/api/v1/reception/sync-versions/?year=2026&reservation_id=757"
```

Očekivano: `304`, prazan body.

### 2d. Nepostojeća rezervacija

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer <TOKEN>" \
  "https://api.stay.hr/api/v1/reception/sync-versions/?year=2026&reservation_id=999999999"
```

Očekivano: `404`.

### 2e. Promjena hash-a

Promijeni status rezervacije #757 (Hospira ili admin), pa ponovi **2b**. `reservation_detail` i `ETag` moraju se promijeniti.

---

## 3. Test suite (opcionalno, na serveru)

```bash
cd /opt/stacks/stay.hr
docker compose build django
docker compose run --rm django python manage.py test \
  apps.reservations.tests.test_sync_versions \
  apps.api.tests.test_reception_api.ReceptionAPITests.test_sync_versions \
  apps.api.tests.test_reception_api.ReceptionAPITests.test_sync_versions_with_reservation_id \
  apps.api.tests.test_reception_api.ReceptionAPITests.test_sync_versions_reservation_id_not_found \
  -v 2
```

---

## 4. Lokalno (Windows / dev) — samo ako testiraš prije pusha

`manage.py` defaultno učitava `config.settings.production` i traži **`DJANGO_SECRET_KEY`** u okruženju.

Za lokalne unit testove koristi test settings (dummy ključ već u njima):

```powershell
cd stay.hr\backend
$env:DJANGO_SETTINGS_MODULE = "config.settings.test"
python manage.py test apps.reservations.tests.test_sync_versions -v 2
```

Na produkcijskom serveru **`DJANGO_SECRET_KEY` već mora biti** u `/opt/stacks/stay.hr/.env` — to nije nova varijabla za ovu promjenu; Django je koristi za session/CSRF/potpise (vidi Django docs).

---

## 5. Nakon backend deploya — Flutter

**Repo:** [github.com/avrcanio/uzorita_flutter](https://github.com/avrcanio/uzorita_flutter) (`hr.finestar.hospira`)

1. Pull/commit s promjenom: `syncVersions(reservationId: …)` + `refreshIfStaleOnResume()` na detail ekranu.
2. Build i distribucija na tablet (Play Store / sideload / MDM).
3. Dok Flutter nije ažuriran, app i dalje radi (puni detail GET); nema breaking change na starom API-ju.
4. Ako Flutter stigne **prije** backend deploya: `reservation_detail` polje nedostaje → app tretira kao stale i i dalje radi puni detail fetch (safe fallback).

### Flutter build (lokalno, Windows/macOS s Flutter SDK)

```bash
cd uzorita_flutter
flutter pub get
flutter test test/features/reception/reception_sync_cache_test.dart
flutter build apk --release
# APK: build/app/outputs/flutter-apk/app-release.apk
```

---

## 6. Rollback

```bash
cd /opt/stacks/stay.hr
git checkout <prethodni-commit>
./scripts/deploy.sh
```

Stari Flutter app nastavlja raditi (bez `reservation_id` parama).

---

## Checklist — deploy gotov

| # | Korak | OK |
|---|--------|-----|
| 1 | `deploy.sh` detektira backend source promjene | |
| 2 | `git pull` + `./scripts/deploy.sh` → `Done.`, `manage.py check` OK | |
| 3 | Container: `reservation_id` u `build_sync_versions_payload` → `True` | |
| 4 | curl **2a** — bez `reservation_detail` | |
| 5 | curl **2b** — `reservation_detail` (16 hex) + `ETag` | |
| 6 | curl **2c** — `304 Not Modified` | |
| 7 | curl **2d** — `404` za nepostojeći ID | |
| 8 | curl **2e** — hash se mijenja nakon promjene rezervacije | |
| 9 | (opcionalno) unit testovi iz §3 prolaze | |
| 10 | Hospira Flutter build objavljen na tablet | |

---

## Povezani dokumenti

- [Test suite](../development/test-suite.md)
- [Deploy / domene](domain-setup.md#deploy-s-githuba)
