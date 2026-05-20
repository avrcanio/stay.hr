# Channex PMS Certification — Google obrazac (stay.hr)

**Obrazac:** [Channex PMS Certification](https://forms.google.com) (Google Forms, ~34 stranice)  
**Okruženje:** Channex **staging** + stay.hr tenant **`demo`** (id=1), property **`channex-demo`**  
**Channex property:** Test Property - Stay.hr  
**Datum prijave:** 2026-05-20 (re-cert nakon ispravki)

---

## Stranica 1 — Kontakt

| Polje | Vrijednost |
|-------|------------|
| E-pošta | `avrcanus@gmail.com` |
| Product name | `stay.hr` |
| Contact Person Name | `Ante Vrcan` |
| Contact Person Email | `avrcan@finestar.hr` |

---

## Stranica 2 — Information about PMS functionality

| Pitanje | Odgovor | Napomena (stay.hr) |
|---------|---------|-------------------|
| Multiple Room Types per Property? | **Yes** | Cert property ima `BCOM-HOLIDAY` + `BCOM-STUDIO` (2 room typea u Channexu) |
| Multiple Rate Plans per Room Type? | **Yes** | Po sobi: `standard` + `non_refundable` (vidi rate plan tablicu dolje) |
| What restrictions is supported? | **Sve označeno** | Availability, Rate, Min Stay Through, Min Stay Arrival, Max Stay, Closed To Arrival, Closed To Departure, Stop Sell — implementirano u ARI push + full sync |
| Credit card details with bookings? | **No** | Booking ingest ne dohvaća/sprema kartice iz Channex revisiona |
| Are you PCI Certified? | **No** | Nismo PCI-certified; ne obrađujemo card data |

### Restrictions (checkbox lista — sve Yes)

- [x] Availability
- [x] Rate
- [x] Min Stay Through
- [x] Min Stay Arrival
- [x] Max Stay
- [x] Closed To Arrival
- [x] Closed To Departure
- [x] Stop Sell

---

## Stranica 3 — Setup Testing Property

Channex u uputama navodi Twin/Double + USD; **stay.hr cert** koristi property **Test Property - Stay.hr** (GBP, Booking hotel `10745030`) sa sobama **Studio** i **Holiday Home**. Ispod su stvarni Channex UUID-i — mapirani na polja forme.

| Polje u formi | stay.hr entitet | UUID (zalijepi) |
|---------------|-----------------|-----------------|
| **Property ID at Channex** * | Test Property - Stay.hr | `e00e6034-c154-4754-b5d9-9fff73ad12f6` |
| **Twin Room ID** * | BCOM-STUDIO (Studio, 2 guests) | `18c437d7-13e3-4dbc-9565-48fad4832bf5` |
| **Twin Room Best Available Rate ID** * | BCOM-STUDIO → `standard` | `aa73125c-b9b6-48a7-862f-da68c6e77999` |
| **Twin Room Bed & Breakfast Rate ID** | BCOM-STUDIO → `non_refundable` | `6734ae1e-70bb-4217-b668-2aa8720bca13` |
| **Double Room ID** | BCOM-HOLIDAY (Holiday Home) | `430b1381-dace-44d6-8d5d-a0a1025819fc` |
| **Double Room Best Available Rate ID** | BCOM-HOLIDAY → `standard` | `81061916-cc0a-4b78-850e-2d6d4be7c551` |
| **Double Room Bed & Breakfast Rate ID** | BCOM-HOLIDAY → `non_refundable` | `69f4bf3b-e23a-409e-be16-50a0f2b17605` |

**Copy-paste (redom kao u formi):**

```
e00e6034-c154-4754-b5d9-9fff73ad12f6
18c437d7-13e3-4dbc-9565-48fad4832bf5
aa73125c-b9b6-48a7-862f-da68c6e77999
6734ae1e-70bb-4217-b668-2aa8720bca13
430b1381-dace-44d6-8d5d-a0a1025819fc
81061916-cc0a-4b78-850e-2d6d4be7c551
69f4bf3b-e23a-409e-be16-50a0f2b17605
```

**Napomena:** Valuta na propertyju je **GBP** (ne USD iz primjera u formi). Rate plan nazivi u Channexu su *Standard rate* / *non-refundable rate*, ne BAR/B&B — ID-evi su ispravni za cert testove na tom propertyju.

Provjera u Channex staging UI: Property → Test Property - Stay.hr → Room Types / Rate Plans.

**API provjera (2026-05-20)** — [`properties`](https://docs.channex.io/api-v.1-documentation/hotels-collection#properties-list), [`room_types?filter[property_id]=…`](https://docs.channex.io/api-v.1-documentation/room-types-collection#room-types-list), [`rate_plans?filter[property_id]=…`](https://docs.channex.io/api-v.1-documentation/rate-plans-collection#rate-plans-list):

| API entitet | Channex title | UUID u formi | OK |
|-------------|---------------|-------------|-----|
| Property | Test Property - Stay.hr (GBP) | `e00e6034-…` | ✓ |
| Room (Twin) | BCOM-STUDIO, 2 adults | `18c437d7-…` | ✓ |
| Room (Double) | BCOM-HOLIDAY, 11 adults | `430b1381-…` | ✓ |
| Rate → Studio | Standard rate | `aa73125c-…` | ✓ |
| Rate → Studio | non-refundable rate | `6734ae1e-…` | ✓ |
| Rate → Holiday | Standard rate | `81061916-…` | ✓ |
| Rate → Holiday | non-refundable rate | `69f4bf3b-…` | ✓ |

---

## Stranica 4 — Certification scenarios (uputa)

Dokumentacija: [PMS Certification Tests](https://docs.channex.io/api-v.1-documentation/pms-certification-tests#execute-test-scenarios)

**U formu upisuj samo `id` iz `data[].id` (task UUID), ne cijeli JSON.**

Primjer odgovora:
```
03854d5e-5234-43e9-b673-803e91bfe640
```

### Je li stay.hr usklađen? (pregled)

| Test | Channex zahtjev | stay.hr | Status |
|------|-----------------|---------|--------|
| **1** Full sync | 2 API poziva, 500 dana, varijabilni podaci | `channex_ari_full_sync` → availability + restrictions batch, sva restriction polja | OK nakon fixa |
| **2** Single rate | Twin/BAR, 22 Nov 2026, 333 | `BCOM-STUDIO` + `standard`, `2026-11-22`, delta samo `rate` | OK |
| **3** Multi rate, 1 call | 3 rate promjene, 1 API | Jedan `PATCH` s 3 `updates[]` → 1 `POST /restrictions` | OK |
| **4** Date ranges | 3 range-a, 1 API | Jedan `PATCH` s 3 stavke | OK |
| **5** Min stay | 3 min stay, 1 API | `min_stay_arrival` u PATCH (ne `min_stay`) | OK — vidi mapiranje |
| **6** Stop sell | 3 stop_sell, 1 API | `stop_sell: true` u PATCH | OK |
| **7** Multi restrictions | CTA, CTD, max_stay, min_stay | `closed_to_arrival`, `closed_to_departure`, `max_stay`, `min_stay_arrival` | OK — `min_stay` → `min_stay_arrival` |
| **8** Half-year | Dec 2026 – May 2027, 1 API | `date_from` / `date_to` + rate + restrictions | OK |
| **9–10** Availability | 1–2 API poziva | `PATCH .../channex/ari/availability/` | OK |
| **11** Booking | webhook → revision GET → ack | Implementirano; ne `GET /bookings` | OK |
| **12** Rate limits | queue/limiter | Outbox + `sleep(0.5)` na flush; **nema** 429 retry | Djelomično — u formi potvrdi plan |
| **13** Delta only | ne timer full sync | Delta na PATCH; full sync samo ručno/command | OK |
| **14** Extra notes | kao stranica 2 | Isto | OK |

### Mapiranje Twin/Double → stay.hr (cert testovi 2–10)

| Channex (forma) | stay.hr |
|-----------------|---------|
| Twin Room | `BCOM-STUDIO` (`unit_code`) |
| Double Room | `BCOM-HOLIDAY` |
| Best Available Rate | `rate_plan_code`: `standard` |
| Bed & Breakfast Rate | `rate_plan_code`: `non_refundable` |

Valuta u primjerima je **USD**; na propertyju je **GBP** — cijene u testovima (333, 241, …) šalji kao broj, valuta je iz propertyja.

### Kako pokrenuti testove (stay.hr put)

Channex traži akciju iz **PMS UI**, ne standalone cert skriptu. Kod nas je kanonski put:

1. **Admin** ili **reception API** (`PATCH` s Bearer tokenom, tenant `demo`)
2. Ili management command za **test 1** full sync (`channex_ari_full_sync`)

To je legitimno ako na live screenshare možeš promijeniti cijenu u stay.hr (admin / API) i pokažeš da odlazi Channex poziv — ne samo ručni curl izoliran od produkta.

**Napomena:** Vizualni kalendar grid (reception UI) još nije obavezan za cert, ali za Stage 4 screenshare pripremi jasan demo put (admin Rate plan day ili API PATCH).

### API za cert (tenant demo)

```
PATCH https://api.stay.hr/api/v1/integrations/channex/ari/rates/
PATCH https://api.stay.hr/api/v1/integrations/channex/ari/availability/
```

Scope: `reception:write`, API application na tenantu **demo**.

---

## Staging identifikatori (kopiraj na relevantne stranice)

| Što | Vrijednost |
|-----|------------|
| Channex Property ID | `e00e6034-c154-4754-b5d9-9fff73ad12f6` |
| Channex Property title | Test Property - Stay.hr |
| Channel ID (Booking.com test) | `8ee9c7aa-6433-4037-924b-4f95598782d5` |
| Booking.com test hotel ID | `10745030` |
| Valuta | GBP |
| stay.hr API base | `https://api.stay.hr/api/v1` |
| Webhook URL | `https://api.stay.hr/api/v1/integrations/channex/webhook/` |
| Channex API base (staging) | `https://staging.channex.io/api/v1` |

### Room types

| stay.hr unit | Channex room type UUID |
|--------------|-------------------------|
| BCOM-HOLIDAY | `430b1381-dace-44d6-8d5d-a0a1025819fc` |
| BCOM-STUDIO | `18c437d7-13e3-4dbc-9565-48fad4832bf5` |

### Rate plans

| Unit | stay.hr code | Channex rate plan UUID | Default |
|------|--------------|------------------------|---------|
| BCOM-STUDIO | `standard` | `aa73125c-b9b6-48a7-862f-da68c6e77999` | 95 GBP |
| BCOM-STUDIO | `non_refundable` | `6734ae1e-70bb-4217-b668-2aa8720bca13` | 79 GBP |
| BCOM-HOLIDAY | `standard` | `81061916-cc0a-4b78-850e-2d6d4be7c551` | 165 GBP |
| BCOM-HOLIDAY | `non_refundable` | `69f4bf3b-e23a-409e-be16-50a0f2b17605` | 135 GBP |

---

## Deklarirana podrška (restrictions / ARI)

Označi / navedi podršku za:

- Availability
- Rate
- Min Stay Through
- Min Stay Arrival
- Max Stay
- Closed To Arrival
- Closed To Departure
- Stop Sell

**Full sync** šalje sva gornja restriction polja u `POST /restrictions` (mjesečni batch-evi, 500 dana).

**Delta push:** u `POST /restrictions` idu **samo** polja iz PMS PATCH zahtjeva (npr. test #2 = samo `rate`).

---

## Cert testovi — odgovori za obrazac

### Test 1 — Full sync (500 days)

**Naredba:**

```bash
docker exec stay_django python manage.py channex_ari_full_sync --tenant-slug demo
```

**Task ID (availability)** — 2026-05-20:

```
473707cd-ac38-4f7c-bb3e-86f1783ea756
```

**Task ID (restrictions)** — 2026-05-20:

```
4da815ac-1f54-4677-9651-8bfafdb852bc
```

---

### Test 2 — Single date rate change (delta)

**PMS API:**

`PATCH https://api.stay.hr/api/v1/integrations/channex/ari/rates/`  
Auth: Bearer (API app, scope `reception:write`, tenant **demo**)

**Body:**

```json
{
  "updates": [
    {
      "unit_code": "BCOM-STUDIO",
      "rate_plan_code": "standard",
      "date": "2026-11-22",
      "rate": "333.00"
    }
  ]
}
```

**Očekivani Channex restrictions payload (samo promjena):**

```json
{
  "date": "2026-11-22",
  "property_id": "e00e6034-c154-4754-b5d9-9fff73ad12f6",
  "rate_plan_id": "aa73125c-b9b6-48a7-862f-da68c6e77999",
  "rate": "333.00"
}
```

**Task ID** — 2026-05-20:

```
df696150-b44c-44ae-9602-56e1d5dade8b
```

---

### Test 3 — Multiple rates, one API call

Jedan `PATCH` s više stavki u `updates[]` → jedan Channex `POST /restrictions`.

```json
{
  "updates": [
    {"unit_code": "BCOM-STUDIO", "rate_plan_code": "standard", "date": "2026-11-21", "rate": "333.00"},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "standard", "date": "2026-11-25", "rate": "444.00"},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "non_refundable", "date": "2026-11-29", "rate": "456.23"}
  ]
}
```

**Task ID** — 2026-05-20:

```
92db3a77-ee2c-44a6-a09c-bdb33d599481
```

---

### Test 4 — Date range rate change (3 range-a, 1 API)

```json
{
  "updates": [
    {"unit_code": "BCOM-STUDIO", "rate_plan_code": "standard", "date_from": "2026-11-01", "date_to": "2026-11-10", "rate": "241.00"},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "standard", "date_from": "2026-11-10", "date_to": "2026-11-16", "rate": "312.66"},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "non_refundable", "date_from": "2026-11-01", "date_to": "2026-11-20", "rate": "111.00"}
  ]
}
```

**Task ID** — 2026-05-20:

```
d9d1b4c5-5baf-4d95-9e5f-2bbe649235e2
```

---

### Test 5 — Min stay (1 API)

```json
{
  "updates": [
    {"unit_code": "BCOM-STUDIO", "rate_plan_code": "standard", "date": "2026-11-23", "min_stay_arrival": 3},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "standard", "date": "2026-11-25", "min_stay_arrival": 2},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "non_refundable", "date": "2026-11-15", "min_stay_arrival": 5}
  ]
}
```

**Task ID** — 2026-05-20:

```
5506fe45-f57c-44ce-94b5-2c088fe6daf8
```

---

### Test 6 — Stop sell (1 API)

```json
{
  "updates": [
    {"unit_code": "BCOM-STUDIO", "rate_plan_code": "standard", "date": "2026-11-14", "stop_sell": true},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "standard", "date": "2026-11-16", "stop_sell": true},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "non_refundable", "date": "2026-11-20", "stop_sell": true}
  ]
}
```

**Task ID** — 2026-05-20:

```
d9b10072-fa6e-432a-9f64-79d9867aa2f9
```

---

### Test 7 — Multiple restrictions (1 API)

Channex `min_stay` → stay.hr `min_stay_arrival`.

```json
{
  "updates": [
    {"unit_code": "BCOM-STUDIO", "rate_plan_code": "standard", "date_from": "2026-11-01", "date_to": "2026-11-10", "closed_to_arrival": true, "closed_to_departure": false, "max_stay": 4, "min_stay_arrival": 1},
    {"unit_code": "BCOM-STUDIO", "rate_plan_code": "non_refundable", "date_from": "2026-11-12", "date_to": "2026-11-16", "closed_to_arrival": false, "closed_to_departure": true, "min_stay_arrival": 6},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "standard", "date_from": "2026-11-10", "date_to": "2026-11-16", "closed_to_arrival": true, "min_stay_arrival": 2},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "non_refundable", "date_from": "2026-11-01", "date_to": "2026-11-20", "min_stay_arrival": 10}
  ]
}
```

**Task ID** — 2026-05-20:

```
f41c4621-d04b-4368-bfdc-630cc09b3b87
```

---

### Test 8 — Half-year update (1 API)

```json
{
  "updates": [
    {"unit_code": "BCOM-STUDIO", "rate_plan_code": "standard", "date_from": "2026-12-01", "date_to": "2027-05-01", "rate": "432.00", "closed_to_arrival": false, "closed_to_departure": false, "min_stay_arrival": 2},
    {"unit_code": "BCOM-HOLIDAY", "rate_plan_code": "standard", "date_from": "2026-12-01", "date_to": "2027-05-01", "rate": "342.00", "min_stay_arrival": 3}
  ]
}
```

**Task ID** — 2026-05-20:

```
2f0abb88-784f-41b5-9008-a0ae1cc35c06
```

---

### Test 9 — Single date availability (1 API)

`PATCH .../channex/ari/availability/`

```json
{
  "updates": [
    {"unit_code": "BCOM-STUDIO", "date": "2026-11-21", "availability": 7},
    {"unit_code": "BCOM-HOLIDAY", "date": "2026-11-25", "availability": 0}
  ]
}
```

**Task ID** — 2026-05-20:

```
998c2790-11cd-4abd-872f-b21185daf807
```

---

### Test 10 — Multiple date availability (1 API)

```json
{
  "updates": [
    {"unit_code": "BCOM-STUDIO", "date_from": "2026-11-10", "date_to": "2026-11-16", "availability": 3},
    {"unit_code": "BCOM-HOLIDAY", "date_from": "2026-11-17", "date_to": "2026-11-24", "availability": 4}
  ]
}
```

**Task ID** — 2026-05-20:

```
17f454ae-efdc-4a19-8631-9b9a8b4c03da
```

---

### Test 11 — Booking receiving

**Flow (ne koristiti `GET /bookings` ni list `GET /booking_revisions`):**

1. Channex šalje webhook na `https://api.stay.hr/api/v1/integrations/channex/webhook/`
2. stay.hr: `GET /booking_revisions/{revision_id}`
3. Upsert rezervacije na property `channex-demo`
4. stay.hr: `POST /booking_revisions/{revision_id}/ack`

**Webhook (Channex UI):**

| Field | Value |
|-------|--------|
| Property | Test Property - Stay.hr |
| Trigger | Booking |
| Callback | `https://api.stay.hr/api/v1/integrations/channex/webhook/` |
| Request params | `provider=stay`, `env=staging` |
| Header | `X-Stay-Channex-Webhook: <secret>` |

**Fallback (opcionalno u formi):**

```bash
docker exec stay_django python manage.py channex_booking_revisions_feed --tenant-slug demo
```

**Revision ID / booking ID** — 2026-05-20 (Booking CRS `POST /bookings`, webhook ingest + ack):

```
Revision ID: e3de14f2-45c6-45b0-a583-031f34f40a62
Booking ID:  6ec97804-b823-4def-b74d-a4493958713e
```

stay.hr rezervacija: `CERT-STAY-2026-05-20`, property `channex-demo`, check-in 2026-06-10 / check-out 2026-06-14.

---

## Webhook konfiguracija (referenca)

```json
{
  "provider": "stay",
  "env": "staging"
}
```

Header: `X-Stay-Channex-Webhook` = vrijednost iz `.env` (`CHANNEX_WEBHOOK_SECRET`).

---

## Brzi pregled task ID-ova (Google forma, str. 4+)

| Test | Task / ID |
|------|-----------|
| 1 availability | `473707cd-ac38-4f7c-bb3e-86f1783ea756` |
| 1 restrictions | `4da815ac-1f54-4677-9651-8bfafdb852bc` |
| 2 | `df696150-b44c-44ae-9602-56e1d5dade8b` |
| 3 | `92db3a77-ee2c-44a6-a09c-bdb33d599481` |
| 4 | `d9d1b4c5-5baf-4d95-9e5f-2bbe649235e2` |
| 5 | `5506fe45-f57c-44ce-94b5-2c088fe6daf8` |
| 6 | `d9b10072-fa6e-432a-9f64-79d9867aa2f9` |
| 7 | `f41c4621-d04b-4368-bfdc-630cc09b3b87` |
| 8 | `2f0abb88-784f-41b5-9008-a0ae1cc35c06` |
| 9 | `998c2790-11cd-4abd-872f-b21185daf807` |
| 10 | `17f454ae-efdc-4a19-8631-9b9a8b4c03da` |
| 11 revision | `e3de14f2-45c6-45b0-a583-031f34f40a62` |
| 11 booking | `6ec97804-b823-4def-b74d-a4493958713e` |

---

## Prije službe forme — checklist

- [x] Deploy novog koda na `api.stay.hr` (`docker compose build django && up -d`) — 2026-05-20
- [x] `channex_ari_full_sync --tenant-slug demo` → task ID-ovi gore
- [x] Testovi 2–10 PATCH (`reception:write`, tenant demo)
- [x] Test 11 — booking CRS + webhook ingest + ack
- [ ] Screenshot rezervacije u adminu (forma test 11)
- [ ] Email Channex supportu (engleski nacrt u chatu / mail)

---

## Povezano

- [channex-demo-property.md](./channex-demo-property.md) — tehnička setup dokumentacija
- [test-suite.md](../development/test-suite.md) — automatski testovi (121/121 OK)
