# Tenant integration credentiali — platforma vs baza

Operativni plan: **produkcijski connector credentiali po tenantu u bazi** (`IntegrationConfig`), ne u globalnom `.env`. Cert/staging Channex tenant ugašen.

**Repo:** `/opt/stacks/stay.hr`  
**Admin:** https://admin.stay.hr/admin/integrations/integrationconfig/

Povezano: [channel-manager-setup.md](channel-manager-setup.md), [channex-uzorita-booking-channel.md](../integrations/channex-uzorita-booking-channel.md).

---

## Načelo

| Sloj | Gdje | Primjer |
|------|------|---------|
| **Platforma (stay.hr)** | `.env` na serveru | `STAY_INTEGRATION_FERNET_KEY`, Redis, Cloudflare, Meta app-level |
| **Tenant connector** | `IntegrationConfig` u bazi (`config_encrypted`) | Channex `api_key`, `webhook_secret`, `property_id`; WhatsApp `access_token`; eVisitor |
| **Recepcija / SMTP gostima** | `TenantReceptionSettings` u bazi | `guest_contact_email`, SMTP lozinka |

**Ne** držati produkcijske tenant ključeve u `.env` nakon što su u bazi.

---

## Smoobu — uklonjen iz stay.hr

Migracija [`0017_remove_smoobu`](../../backend/apps/integrations/migrations/0017_remove_smoobu.py):

- provider `smoobu` više **nije** u `IntegrationConfig`
- postojeći Smoobu config redovi **obrisani** iz baze
- `uzorita` koristi **`channel_manager=channex`**

`SMOOBU_API_KEY` / `SMOOBU_WEBHOOK_SECRET` u `.env` **nema gdje u aplikaciji** — ukloniti iz aktivnog `.env` (ostaviti samo arhivu lokalno ako treba).

Ako ikad treba Smoobu opet: to je **feature restore**, ne samo spremanje ključa u bazu.

---

## Channex — produkcija (`uzorita`)

| Polje | Izvor istine | Uzorita (produkcija) |
|-------|--------------|----------------------|
| Channex property UUID | `IntegrationConfig` → `property_id` | `bca8473d-7c36-4986-bcdb-b5760b633283` |
| API key | `IntegrationConfig` → `api_key` | Organisation → API Keys (app.channex.io) |
| Webhook secret | `IntegrationConfig` → `webhook_secret` | Header `X-Stay-Channex-Webhook` |
| Room mapping | `IntegrationConfig` → `room_types` / `booking_test_rooms` | R1, R2, R3, R6 |
| `channel_manager` | `TenantReceptionSettings` | `channex` |
| `sync_property_slug` | config | `uzorita` (inventory property) |

### Webhook URL (produkcija)

```text
https://api.stay.hr/api/v1/integrations/channex/webhook/?provider=stay&env=production
```

(Ako Channex UI još koristi `env=staging` u queryju, uskladiti s [`webhook_auth.py`](../../backend/apps/integrations/channex/webhook_auth.py) — trenutno default provjera je `staging`; za produkciju treba proširiti `EXPECTED_ENV` ili registrirati odvojeni query param.)

Header mora odgovarati **`webhook_secret` u bazi** za taj `property_id`, ne globalnom `.env`.

---

## Cert / test — ugašeno

| Stavka | Akcija |
|--------|--------|
| Tenant `channex` + property `channex-demo` | `IntegrationConfig` **is_active=False** |
| `TenantReceptionSettings.channel_manager` za `channex` | `none` |
| Staging ključevi u `.env` | već komentirani (`CHANNEX_STAGING_*`) |
| Seed cert commandi | ostaju u repou za eventualni re-cert, ne pokretati na produkciji |

---

## Migracija (jednokratno)

### 1. Kopiraj credential-e u bazu (uzorita)

Ako su ključevi još samo u `.env`:

```bash
cd /opt/stacks/stay.hr
docker compose exec django python manage.py sync_channex_credentials --tenant-slug uzorita
```

Ili admin → Integrations → Integration configs → uzorita / Channex → Credentials.

Provjera:

```bash
docker compose exec -T django python manage.py shell -c "
from apps.integrations.config_secrets import credentials_complete
from apps.integrations.models import IntegrationConfig
row = IntegrationConfig.objects.get(tenant__slug='uzorita', provider='channex', is_active=True)
print(credentials_complete('channex', row.get_config_dict()))
"
```

Očekivano: `True`.

### 2. Ukloni tenant Channex varijable iz `.env`

Obriši ili zakomentiraj (ne commitati stvarne vrijednosti):

```env
# CHANNEX_PROPERTY_ID=...   → IntegrationConfig uzorita
# CHANNEX_API_KEY=...       → IntegrationConfig uzorita
# CHANNEX_WEBHOOK_SECRET=... → IntegrationConfig uzorita
```

Restart Django nakon promjene `.env`:

```bash
docker compose restart django celery-worker celery-beat
```

### 3. Ugasi test config

```bash
docker compose exec -T django python manage.py shell -c "
from apps.integrations.models import IntegrationConfig
IntegrationConfig.objects.filter(tenant__slug='channex', provider='channex').update(is_active=False)
"
```

### 4. Channex UI

- Produkcijski property Uzorita: webhook header = secret iz admina (Integration config id za uzorita).
- Staging cert property: webhook može ostati disabled ili uklonjen.

---

## Rotacija ključeva (kad zatreba)

1. Novi ključ u Channex UI / Organisation API Keys.
2. Admin → Integration config (uzorita) → API key / webhook secret → Save.
3. Channex webhook header ažurirati isti dan.
4. **Ne** vraćati ključ u `.env`.

---

## Kod — implementirano (overbooking / tenant routing)

| Promjena | Datoteka |
|----------|----------|
| Ingest property = `sync_property_slug` (uzorita), ne `channex-bcom-test` | [`booking_service.py`](../../backend/apps/integrations/channex/booking_service.py) |
| Mapiranje soba iz `room_types` + `booking_test_rooms` | [`config.py`](../../backend/apps/integrations/channex/config.py) |
| ARI push nakon Channex inbound ingest | [`reservation_availability_service.py`](../../backend/apps/integrations/channex/reservation_availability_service.py) |
| Webhook routing samo po `property_id` (bez fallback na prvi tenant) | [`webhook_service.py`](../../backend/apps/integrations/channex/webhook_service.py) |

### Nakon deploya (operativa)

1. **Full sync** — uskladiti Channex kalendar s trenutnim inventarom:

```bash
docker compose exec django python manage.py channex_ari_full_sync --tenant-slug uzorita --days 500
```

2. Provjera novog inbound bookinga — u stay.hr mora imati `property=uzorita` i mapirane `unit_id` (R1/R2/R3/R6).

---

## Kod — preostali backlog

| # | Promjena | Zašto |
|---|----------|-------|
| 1 | `ChannexRuntimeConfig.from_integration_dict` — bez env fallbacka u produkciji | DB = jedini izvor |
| 2 | `verify_channex_webhook_request` — secret samo iz `IntegrationConfig` po `property_id` | Bez globalnog secret-a |
| 3 | `sync_channex_credentials` — obavezan `--tenant-slug`, bez merge u sve redove | Sprječava miješanje tenant-a |
| 4 | Upozorenje / alert pri ingestu ako unit već zauzet (druga rezervacija) | Rana detekcija overbookinga |

---

## Checklist — produkcija

| # | Korak | OK |
|---|--------|-----|
| 1 | Uzorita `IntegrationConfig` active, credentials complete u adminu | |
| 2 | Ključevi u bazi (ne ovisi o `.env` CHANNEX_*) | |
| 3 | `.env` bez `CHANNEX_PROPERTY_ID` / `API_KEY` / `WEBHOOK_SECRET` | |
| 4 | Cert config `channex/channex-demo` deactivated | |
| 5 | `uzorita` `channel_manager=channex` | |
| 6 | Webhook u Channex UI → secret iz baze | |
| 7 | Test inbound booking na uzorita (jedna noć) | |
| 8 | Full sync / ARI za kolovoz provjeren | |

---

## Povezani dokumenti

- [channel-manager-setup.md](channel-manager-setup.md)
- [domain-setup.md](domain-setup.md)
