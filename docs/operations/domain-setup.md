# Postavljanje domena (booking + recepcija)

Operativne upute za domene web frontenda Stay.hr platforme.

**Repo na serveru:** `/opt/stacks/stay.hr`  
**Deploy:** `git pull` + `./scripts/deploy.sh` (vidi [Deploy s GitHuba](#deploy-s-githuba))

---

## Tri sloja

| Sloj | Tko konfigurira | Što radi |
|------|-----------------|----------|
| **Cloudflare DNS** | Django backend (admin / management command) | A/CNAME zapisi, proxied → Hetzner IP |
| **Traefik** | `docker-compose.yml` labele (jednokratno + custom hostovi) | TLS (ACME DNS-01) + routing po `Host` |
| **Django `TenantDomain`** | Admin (`admin.stay.hr`) | Koji `Host` = koji tenant + property (booking kontekst) |

Token **`CF_DNS_API_TOKEN`** — isti kao u `/opt/stacks/traefik/.env` (Traefik cert resolver + Django DNS upsert).

---

## Preduvjeti

1. Traefik stack na `/opt/stacks/traefik`, mreža `proxy`
2. U Django `.env` na serveru ( `/opt/stacks/stay.hr/.env` ):

```env
CF_DNS_API_TOKEN=...          # Cloudflare API token (Zone DNS Edit)
STAY_SERVER_IP=...            # Javni IP Hetzner servera (proxied A record)
CLOUDFLARE_ZONE_STAY=stay.hr  # Zona za *.stay.hr subdomene
```

3. Web frontend containeri (`web/reception`, `web/booking`) deployani s Traefik labelama (kad budu u produkciji)

> **Napomena:** Management command `provision_platform_dns` i admin akcija **Provision DNS** planirani su u backendu (faza web frontenda). Dok nisu deployani, za `api.stay.hr` / `admin.stay.hr` koristi postojeću skriptu `./scripts/cloudflare_dns_upsert.sh` (vidi README).

---

## A) Jednokratno — platforma

Prije go-live web frontenda (recepcija + booking subdomene).

### 1. DNS (backend)

```bash
cd /opt/stacks/stay.hr
docker compose run --rm django python manage.py provision_platform_dns
```

Očekivani zapisi u zoni `stay.hr` (proxied A → `STAY_SERVER_IP`):

| Host | Namjena |
|------|---------|
| `app.stay.hr` | Recepcija u browseru |
| `*.stay.hr` | Wildcard — tenant booking subdomene (`uzorita.stay.hr`, …) |

API i admin (`api.stay.hr`, `admin.stay.hr`) već postoje — ne dirati osim provjere.

**Interim (prije `provision_platform_dns`):** ručno u Cloudflare dashboardu ili proširi `STAY_DNS_HOSTS` u `scripts/.env` i pokreni `./scripts/cloudflare_dns_upsert.sh`.

### 2. Traefik (docker-compose)

U `docker-compose.yml` web servisa — jednokratno:

- `Host(\`app.stay.hr\`)` → `stay-web-reception`
- `HostRegexp(\`^[a-z0-9-]+\\.stay\\.hr$\`)` → `stay-web-booking`
- `tls.certresolver=cloudflare` na oba routera

Zatim:

```bash
docker compose up -d
```

### 3. Provjera

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://app.stay.hr/
curl -sS -o /dev/null -w '%{http_code}\n' https://uzorita.stay.hr/
```

Očekivano: `200` ili `307` (redirect), ne `404`/`502`.

---

## B) Nova Stay subdomena (`*.stay.hr`)

Primjer: `demo.stay.hr` za tenant `demo`.

Wildcard DNS i Traefik `HostRegexp` već pokrivaju routing — **nema novih Traefik labela**.

### Koraci

1. **Admin** → [Tenant domains](https://admin.stay.hr/admin/tenants/tenantdomain/) → **Add**:
   - `domain`: `demo.stay.hr`
   - `tenant`: demo
   - `property`: (opcionalno) FK na objekt — ako je postavljen, booking ide direktno na taj objekt
   - `domain_type`: `stay_subdomain`
   - `is_verified`: `False`

2. Odaberi red → admin akcija **Provision DNS** → backend upsert-a A zapis u Cloudflare

3. Provjera:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://demo.stay.hr/
```

4. Postavi `is_verified=True` u adminu

### Slug u URL-u (više objekata po tenantu)

Ako `TenantDomain.property` **nije** postavljen (tenant hub):

- `https://demo.stay.hr/p/<property-slug>/` — booking za taj objekt
- Primjer: `https://uzorita.stay.hr/p/uzorita/`

---

## C) Custom domena (vanjski host)

Primjer: `booking.uzorita.hr` → tenant `uzorita`, property `uzorita`.

Wildcard `*.stay.hr` **ne pokriva** vanjsku domenu — treba i DNS i Traefik `Host()` rule.

### Koraci

1. **Admin** → TenantDomain → **Add**:
   - `domain`: `booking.uzorita.hr`
   - `tenant`: uzorita
   - `property`: Uzorita Luxury Rooms (`slug=uzorita`)
   - `domain_type`: `custom_domain`
   - `is_verified`: `False`

2. Admin akcija **Provision DNS**  
   Backend upsert-a zapis u zoni `uzorita.hr` (mora biti u istom Cloudflare accountu kao token).

3. **Traefik** — dodaj label u `docker-compose.yml` booking servisa:

```yaml
- traefik.http.routers.stay-booking-uzorita.rule=Host(`booking.uzorita.hr`)
- traefik.http.routers.stay-booking-uzorita.entrypoints=websecure
- traefik.http.routers.stay-booking-uzorita.tls=true
- traefik.http.routers.stay-booking-uzorita.tls.certresolver=cloudflare
- traefik.http.routers.stay-booking-uzorita.service=stay-web-booking
```

```bash
cd /opt/stacks/stay.hr
docker compose up -d
```

4. Provjera:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://booking.uzorita.hr/
curl -sS -H "Host: booking.uzorita.hr" https://api.stay.hr/api/v1/public/site-context/
```

5. `is_verified=True` u adminu

---

## D) Recepcija (`app.stay.hr`)

- Fiksna platform domena — **ne ovisi** o property slug-u
- Nema javnog bookiranja; auth = device token (kao Hospira tablet)
- DNS: uključen u `provision_platform_dns`
- Traefik: `Host(\`app.stay.hr\`)` → reception container

---

## Deploy s GitHuba

Na Hetzner serveru (SSH):

```bash
cd /opt/stacks/stay.hr
git pull
./scripts/deploy.sh
```

`deploy.sh` rebuild-a image ako ima novih migracija; inače restart servisa.

**Ova uputa** (`docs/operations/domain-setup.md`) dolazi na server automatski s `git pull` — nema zasebnog koraka.

### Redoslijed pri prvom web go-live

1. `git pull` + `./scripts/deploy.sh` (backend s domain routing + Cloudflare modulom)
2. `provision_platform_dns` (jednokratno)
3. Deploy web frontend servisa (`docker compose up -d`)
4. Admin: TenantDomain zapisi + **Provision DNS** po objektu
5. Traefik `Host()` labele za custom domene izvan `*.stay.hr`
6. Provjera curl + `is_verified=True`

---

## Checklist — Uzorita

| # | Korak | OK |
|---|--------|-----|
| 1 | `provision_platform_dns` (app + wildcard) | |
| 2 | Traefik labele: `app.stay.hr`, `HostRegexp *.stay.hr` | |
| 3 | TenantDomain `uzorita.stay.hr` (tenant hub, property=null) + Provision DNS | |
| 4 | TenantDomain `booking.uzorita.hr` (property=uzorita) + Provision DNS | |
| 5 | Traefik `Host(booking.uzorita.hr)` | |
| 6 | `https://booking.uzorita.hr/` radi | |
| 7 | `https://uzorita.stay.hr/p/uzorita/` radi | |
| 8 | `https://app.stay.hr/` recepcija (kad je deployana) | |

---

## Troubleshooting

| Simptom | Provjeri |
|---------|----------|
| `502 Bad Gateway` | Je li web container up? `docker compose ps` |
| DNS ne resolve | Cloudflare dashboard → DNS zapisi; `Provision DNS` ponovno |
| TLS greška | Traefik log; `CF_DNS_API_TOKEN` u traefik `.env`; DNS mora biti proxied |
| Booking prikazuje krivi objekt | `TenantDomain.property` FK; `site-context` s `Host` headerom |
| `404` na custom domeni | Nedostaje Traefik `Host()` label za tu domenu |
| Admin `is_verified` blokira | U produkciji middleware filtrira neverified domene — postavi verified nakon provjere |

---

## Što backend ne automatizira (MVP)

- **Traefik router labele** — ručno u `docker-compose.yml` (custom domene izvan wildcarda)
- **TLS certifikati** — Traefik ACME automatski nakon DNS-a
- **Cloudflare WAF / Page Rules** — po potrebi u CF dashboardu

---

## Povezani dokumenti

- [README — Cloudflare DNS](../../README.md#cloudflare-dns-api--admin)
- [README — Traefik / tenant subdomains](../../README.md#traefik--tenant-subdomains-later)
- `scripts/cloudflare_dns_upsert.sh` — legacy bootstrap za api/admin hostove
