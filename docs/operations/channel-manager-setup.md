# Channel manager — onboarding po tenantu

Operativni runbook za postavljanje **jednog** outbound connectora po tenantu: `none`, `smoobu` ili `channex`.

**Repo na serveru:** `/opt/stacks/stay.hr`  
**Admin:** https://admin.stay.hr/admin/  
**Recepcija (web):** https://app.stay.hr/

Povezano: [domain-setup.md](domain-setup.md) (domene, deploy), [README — operacije](../../README.md#operations).

---

## Načelo

Svaki tenant ima **točno jedan** `channel_manager` u `TenantReceptionSettings`:

| Mod | Outbound (stay.hr → kanal) | Inbound rezervacije |
|-----|----------------------------|---------------------|
| `none` | — | PDF/XLS import, ručni unos |
| `smoobu` | Smoobu blocks + rates | Periodični Smoobu sync |
| `channex` | Channex ARI (full sync + delta) | Channex webhook |

Referentni tenant-i u produkciji:

| Tenant | `channel_manager` | Namjena |
|--------|-------------------|---------|
| `demo` | `channex` | Channex PMS certifikacija (staging) |
| `uzorita` | `smoobu` | Produkcija — live Booking.com preko Smoobu |
| novi tenant | `none` | Bez connectora dok se ne odluči mod |

UI na recepciji (`app.stay.hr`) prilagođava se preko `feature_flags` iz `GET /api/v1/reception/app-config/`:

| Flag | `none` | `smoobu` | `channex` |
|------|--------|----------|-----------|
| `channel_panel` | ✗ | ✗ | ✓ (Channel stranica) |
| `smoobu_calendar_blocks` | ✗ | ✓ | ✗ |
| `reception_create_reservation` | ✓ | ✗ | ✓ |
| `manual_import` | ✓ | ✓ | ✓ |

Staff mora biti ulogiran na **ispravan tenant** (`TenantMembership`). Korisnik s pristupom više tenantima bira tenant na login ekranu.

---

## Preduvjeti

1. Tenant postoji s property-jima i unit-ima (`code` mora odgovarati mappingu — npr. `R1`, `BCOM-STUDIO`).
2. U `.env` na serveru:
   - `STAY_INTEGRATION_FERNET_KEY` — obavezno za enkriptirane credential-e u bazi
   - Po modu: `CHANNEX_*` ili `SMOOBU_API_KEY` (vidi sekcije ispod)
3. Django deploy aktualan (`./scripts/deploy.sh` nakon pull-a s backend promjenama).
4. Za Channex inbound: webhook URL mora biti dostupan s interneta (`https://api.stay.hr/...`).

---

## Zajednički koraci (svi modovi)

**Tko:** platform superuser (Django admin)

### 1. Tenant

Admin → [Tenants](https://admin.stay.hr/admin/tenants/tenant/) → **Add** (ili odaberi postojeći):

- `name`, `slug`, `status=active`, `timezone`, `default_language`
- Inline **Tenant domains** — vidi [domain-setup.md](domain-setup.md)
- Inline **Reception settings** — `channel_manager` postavlja se u koraku moda (dolje)

CLI (samo demo scaffold):

```bash
cd /opt/stacks/stay.hr
docker compose run --rm django python manage.py seed_demo_tenant
```

### 2. Property + unit-i

Admin → Properties / Units za taj tenant. Svaki unit treba stabilan `code` (npr. `R1`) koji se mapira na Smoobu apartment ID ili Channex room type UUID.

### 3. Staff korisnici

Admin → [Users](https://admin.stay.hr/admin/auth/user/) → **Add user**:

1. Username, lozinka, uključi **Staff status** (ne superuser osim namjerno).
2. U inline **Tenant access** dodaj tenant(e).
3. Korisnik se prijavljuje na https://app.stay.hr/login (ili admin za operativne zapise unutar tenanta).

### 4. Provjera sessiona

1. Login na `app.stay.hr` kao staff.
2. Ako korisnik ima više tenant membership-a, odaberi ispravan tenant.
3. Otvori timeline — rezervacije i property-i moraju pripadati tom tenantu.
4. (Opcionalno) API provjera:

```bash
# Zamijeni <SESSION_COOKIE> nakon browser login-a, ili koristi staff API token ako postoji.
curl -sS -b "sessionid=<SESSION_COOKIE>" \
  "https://api.stay.hr/api/v1/reception/app-config/" | jq '.channel_manager, .feature_flags'
```

---

## Mod A — `none` (Manual)

**Kada:** novi tenant bez channel connectora; ručni/PDF/XLS import.

### Koraci

1. Admin → Tenant → **Reception settings** → `channel_manager` = **Manual** (`none`).
2. Spremi — nije potreban `IntegrationConfig` za outbound.
3. Recepcija: PDF import na timelineu; XLS trenutno samo CLI (`import_booking_xls`).

### Outbound ponašanje

- Nova ručna rezervacija (`import_source=manual`) — **nema** pusha u kanal.
- Otkaz / promjena datuma — lokalno u stay.hr, bez vanjskog synca.

### Checklist

| # | Korak | OK |
|---|--------|-----|
| 1 | `channel_manager=none` spremljen bez validation errora | |
| 2 | Staff login → ispravan tenant | |
| 3 | `feature_flags.reception_create_reservation=true` | |
| 4 | Nova rezervacija kroz **New reservation** radi | |

---

## Mod B — `smoobu`

**Kada:** produkcijski tenant s live Booking.com preko Smoobu (referenca: `uzorita`).

### Koraci

#### 1. Smoobu API ključ

1. Smoobu → Advanced → **API Keys** → rotiraj / kreiraj ključ.
2. Na serveru (ne commitati):

```bash
export SMOOBU_API_KEY='...'
```

#### 2. IntegrationConfig

```bash
cd /opt/stacks/stay.hr
docker compose exec django python manage.py seed_uzorita_smoobu_config \
  --tenant-slug uzorita \
  --property-slug uzorita
```

Command:

- Verificira ključ (`GET /api/me`) osim `--skip-verify`
- Enkriptira `api_key` u `IntegrationConfig` (provider `smoobu`)
- Popunjava `apartments[]` mapu (`unit_code` → `smoobu_apartment_id` + `unit_id`)

Alternativa: Admin → [Integration configs](https://admin.stay.hr/admin/integrations/integrationconfig/) → Add → provider **Smoobu**, unesi credential-e i JSON mapping.

Rotacija ključa (bez mijenjanja mappinga):

```bash
export SMOOBU_API_KEY='...'
docker compose exec django python manage.py rotate_smoobu_api_key --tenant-slug uzorita
```

#### 3. Postavi channel_manager

Admin → Tenant `uzorita` → Reception settings → `channel_manager` = **Smoobu**.

Django validira da postoji **aktivan** Smoobu `IntegrationConfig` prije spremanja.

#### 4. Mapiranje unit-a

Default mapa za Uzoritu definirana je u `apps/integrations/smoobu/mapping.py` (`R1`, `R2`, `R3`, `R6`). Za novi tenant:

1. U Smoobu zapiši apartment ID po sobi.
2. Ažuriraj `apartments` JSON u IntegrationConfig (admin forma ili seed command s prilagođenim mapping modulom).
3. Svaki red mora imati `unit_code`, `smoobu_apartment_id`, i po mogućnosti `unit_id` (stay.hr PK).

Seed ispisuje mapu nakon pokretanja — provjeri da `unit_id` nije `-`.

#### 5. Inbound sync (rezervacije iz Smoobu)

Automatski: Celery task `sync_smoobu_reservations_task`.

Ručno:

```bash
docker compose exec django python manage.py sync_smoobu_reservations --tenant-slug uzorita
```

#### 6. Hospira tablet (opcionalno)

```bash
docker compose exec django python manage.py create_api_app \
  --tenant uzorita --name "Uzorita Hospira"
```

Scopes: `reception:read`, `reception:write`, `public:read` — vidi [domain-setup.md — Hospira](domain-setup.md#f-hospira--sync-versions-za-detail-ekran).

### Outbound ponašanje

- Blokiranje datuma na kalendaru → Smoobu API (`feature_flags.smoobu_calendar_blocks=true`).
- Web booking (pending) → block u Smoobu pri confirm/refuse.
- Ručno kreirana rezervacija na recepciji **ne** šalje outbound (Smoobu mod nema `reception_create_reservation`).

### Checklist

| # | Korak | OK |
|---|--------|-----|
| 1 | `seed_uzorita_smoobu_config` OK, credentials status u adminu | |
| 2 | `channel_manager=smoobu` spremljen | |
| 3 | Apartment mapping: svi aktivni unit-i imaju `unit_id` | |
| 4 | `sync_smoobu_reservations` povlači rezervacije | |
| 5 | Calendar block na `/calendar/rooms` vidljiv i radi | |
| 6 | Staff na ispravnom tenantu | |

---

## Mod C — `channex`

**Kada:** Channex PMS certifikacija (`demo`) ili produkcijski/staging Channex tenant.

### Podmodovi

| Tenant | `use_generated_ari` | Full sync izvor |
|--------|----------------------|-----------------|
| `demo` (cert) | `true` | Generirani ARI (cert test hotel) |
| produkcija | `false` | Inventory iz stay.hr (`UnitAvailabilityDay`, rezervacije, blockovi) |

### Koraci — cert tenant (`demo`)

Jednokratni bundle (property + units + IntegrationConfig + rate planovi):

```bash
cd /opt/stacks/stay.hr
docker compose exec django python manage.py migrate_channex_cert_to_demo
```

Ili korak po korak:

```bash
docker compose exec django python manage.py seed_channex_booking_test_property \
  --tenant-slug demo --deactivate-other-tenants
docker compose exec django python manage.py seed_channex_rate_plans --tenant-slug demo
```

Postavi credential-e iz `.env`:

```env
CHANNEX_API_KEY=...
CHANNEX_PROPERTY_ID=...    # Channex property UUID
CHANNEX_WEBHOOK_SECRET=... # ili generira seed command
```

```bash
docker compose exec django python manage.py sync_channex_credentials --tenant-slug demo
```

Admin → Tenant `demo` → Reception settings → `channel_manager` = **Channex**.

Full sync (cert test 1 — 500 dana):

```bash
docker compose exec django python manage.py channex_ari_full_sync --tenant-slug demo --days 500
```

Ili recepcija → **Channel** → **Full Sync (500 days)**.

### Koraci — produkcijski / staging tenant (npr. `uzorita` s Channexom)

```bash
export CHANNEX_API_KEY='...'
export CHANNEX_PROPERTY_ID='...'   # UUID iz Channex Properties

docker compose exec django python manage.py seed_uzorita_channex_config \
  --tenant-slug uzorita \
  --property-slug uzorita \
  --environment staging    # ili production
```

```bash
docker compose exec django python manage.py seed_channex_rate_plans --tenant-slug uzorita
docker compose exec django python manage.py sync_channex_credentials --tenant-slug uzorita
```

Admin → `channel_manager` = **Channex**.

U IntegrationConfig admin formi:

- `use_generated_ari` = **false** za produkciju
- `sync_property_slug` = slug property-ja čiji se inventory synca
- `room_types` JSON: `unit_code`, `channex_room_type_id`, `channex_title`, `unit_id`

Full sync nakon postavljanja:

```bash
docker compose exec django python manage.py channex_ari_full_sync --tenant-slug <slug> --days 500
```

### Channex webhook (inbound booking)

**URL:**

```text
https://api.stay.hr/api/v1/integrations/channex/webhook/?provider=stay&env=staging
```

(Za production Channex account promijeni `env` u query parametru ako konfiguracija to zahtijeva — default u kodu je `staging`.)

**Channex UI — webhook postavke:**

| Polje | Vrijednost |
|-------|------------|
| Callback URL | URL gore |
| Custom header | `X-Stay-Channex-Webhook: <CHANNEX_WEBHOOK_SECRET>` |
| Query params | `provider=stay`, `env=staging` |

Secret mora odgovarati `webhook_secret` u IntegrationConfig (ili `CHANNEX_WEBHOOK_SECRET` u `.env`).

Health check (401 bez headera je očekivano):

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  "https://api.stay.hr/api/v1/integrations/channex/webhook/?provider=stay&env=staging"
```

Test booking iz Channex cert-a → rezervacija u stay.hr s `import_source=channex` (bez outbound loopa).

### Mapiranje unit-a → room type UUID

1. U Channex kreiraj room type po fizičkoj jedinici (`count=1`).
2. Kopiraj UUID u `room_types` / `booking_test_rooms` JSON.
3. `unit_code` mora odgovarati stay.hr `Unit.code`.
4. Pokreni seed ponovno ili ručno uredi JSON u adminu.

Cert demo sobe definirane su u `apps/integrations/channex/booking_test.py` (`BCOM-STUDIO`, itd.).

### Outbound ponašanje

- Full sync + delta rate/availability — Channel panel na recepciji.
- Nova ručna rezervacija → Channex availability delta (−1 po noći).
- Otkaz / promjena datuma → delta prema novom stanju.
- Inbound Channex booking → **ne** okida outbound (loop prevention).

### Checklist

| # | Korak | OK |
|---|--------|-----|
| 1 | Aktivan Channex `IntegrationConfig`, credentials OK u adminu | |
| 2 | `channel_manager=channex` spremljen | |
| 3 | Room type mapping s `unit_id` za sve sobe | |
| 4 | `seed_channex_rate_plans` pokrenut | |
| 5 | Full sync — `task_ids` u push results / CLI output | |
| 6 | Webhook registriran, secret match | |
| 7 | Test inbound booking vidljiv na timelineu | |
| 8 | Channel panel vidljiv na recepciji | |

---

## Migracija: Smoobu → Channex

**Kada:** tenant prelazi s live Smoobu na Channex (npr. budući Uzorita rollout).

Redoslijed (kritično — izbjegni double outbound):

1. **Pripremi** Channex property, room type UUID-e, API ključ, webhook.
2. **Seed** Channex config + rate planovi (ne mijenjaj još `channel_manager`):

   ```bash
   docker compose exec django python manage.py seed_uzorita_channex_config --tenant-slug <slug>
   docker compose exec django python manage.py seed_channex_rate_plans --tenant-slug <slug>
   docker compose exec django python manage.py sync_channex_credentials --tenant-slug <slug>
   ```

3. **Full sync** u Channex (baseline ARI):

   ```bash
   docker compose exec django python manage.py channex_ari_full_sync --tenant-slug <slug> --days 500
   ```

4. **Webhook** — registriraj i testiraj inbound prije prekida Smoobu synca.
5. **Prebaci** `channel_manager` s `smoobu` na `channex` u adminu.  
   Smoobu outbound prestaje; Channex outbound počinje.
6. **Deaktiviraj** Smoobu `IntegrationConfig` (`is_active=false`) kad ste sigurni.
7. **Isključi** ručne Smoobu sync jobove za taj tenant (Celery beat / operativna navika).
8. **Provjeri** recepciju: Channel panel, nova rezervacija, otkaz, calendar blocks (Channex koristi lokalni block + delta).

Rollback: vrati `channel_manager=smoobu`, reaktiviraj Smoobu config, deaktiviraj Channex — samo ako Smoobu još drži istinito stanje kanala.

---

## Admin reference

| Što | Gdje |
|-----|------|
| `channel_manager` | Admin → Tenants → tenant → **Reception settings** inline |
| Credential-i + mapping | Admin → Integrations → **Integration configs** |
| Rate planovi (Channex) | Admin → Integrations → **Channel rate plans** (seed iz configa) |
| Outbox / failed push | Admin → Integrations → **Channex ARI outbox** |
| Staff pristup tenantu | Admin → Users → **Tenant access** inline |

Validacija: spremanje `channel_manager=smoobu|channex` bez aktivnog odgovarajućeg `IntegrationConfig` vraća grešku na formi.

---

## Management commandi (sažetak)

| Command | Namjena |
|---------|---------|
| `seed_demo_tenant` | Scaffold demo tenant + domain + units |
| `seed_uzorita_smoobu_config` | Smoobu IntegrationConfig + apartment map |
| `rotate_smoobu_api_key` | Rotacija Smoobu ključa |
| `sync_smoobu_reservations` | Ručni inbound pull |
| `seed_channex_booking_test_property` | Cert property + units + Channex config |
| `migrate_channex_cert_to_demo` | Cert bundle na tenant `demo` |
| `seed_uzorita_channex_config` | Channex config (staging room types) |
| `seed_channex_rate_plans` | `ChannelRatePlan` redovi iz configa |
| `sync_channex_credentials` | Merge API key / webhook / property ID iz env |
| `channex_ari_full_sync` | Push 500-day ARI u Channex |
| `channex_ari_flush` | Retry pending outbox (operativno) |

Svi commandi:

```bash
cd /opt/stacks/stay.hr
docker compose exec django python manage.py <command> --help
```

---

## Troubleshooting

| Simptom | Provjeri |
|---------|----------|
| Validation error pri spremanju `channel_manager` | Postoji li aktivan `IntegrationConfig` za taj provider? |
| Recepcija nema Channel panel | `channel_manager` mora biti `channex`; osvježi nakon admin promjene |
| Calendar block nedostaje (Channex tenant) | `smoobu_calendar_blocks` je false za channex — block ide lokalno + delta (vidi operativni plan Faza 7) |
| Full sync bez `task_ids` | `CHANNEX_API_KEY`, `property_id`, network; Django log |
| Webhook 401 | `X-Stay-Channex-Webhook` header, query `provider=stay`, secret match |
| Inbound booking ne stiže | Channex webhook log; `property_id` u payloadu mapira na IntegrationConfig |
| Outbound loop (dupli push) | Rezervacije s `import_source=channex` ne bi trebale okidati outbound |
| Smoobu key rejected | Rotiraj ključ u Smoobu UI, `rotate_smoobu_api_key` |
| Pogrešan tenant u recepciji | `TenantMembership`; logout + login s odabirom tenanta |
| Mapping `unit_id` missing | Unit s tim `code` ne postoji ili nije aktivan prije seeda |

---

## Povezani dokumenti

- [domain-setup.md](domain-setup.md) — domene, deploy, recepcija login
- [README — Django admin](../../README.md#django-admin) — staff vs superuser
- Operativni plan po fazama (full sync, delta, rezervacije) — internal plan `operativne_faze_po_operaciji`
