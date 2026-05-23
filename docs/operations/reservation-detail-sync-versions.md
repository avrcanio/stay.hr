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

- rebuild-a Django image ako ima novih migracija (ovdje **nema** → obično samo `docker compose restart`)
- pokreće `python manage.py check`

Očekivani kraj: `Done.` bez grešaka.

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

1. Objavi novi Hospira build (`uzorita_flutter`) koji šalje `reservation_id` na sync-versions.
2. Dok Flutter nije ažuriran, app i dalje radi (puni detail GET); nema breaking change na starom API-ju.
3. Ako Flutter stigne **prije** backend deploya: `reservation_detail` polje nedostaje → app tretira kao stale i i dalje radi puni detail fetch (safe fallback).

---

## 6. Rollback

```bash
cd /opt/stacks/stay.hr
git checkout <prethodni-commit>
./scripts/deploy.sh
```

Stari Flutter app nastavlja raditi (bez `reservation_id` parama).

---

## Povezani dokumenti

- [Test suite](../development/test-suite.md)
- [Deploy / domene](domain-setup.md#deploy-s-githuba)
