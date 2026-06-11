# Uzorita — surge cijene 4. kolovoza 2026.

**Objekt:** Luxury Room Uzorita B&B (tenant `uzorita`, property `uzorita`)  
**Datum odluke:** 2026-06-11  
**Tražio:** Ante — namjerno povećanje, **nije bug** niti ručno sniženje od treće strane.

---

## Sažetak (trenutno stanje)

| Datum | Pravilo | R1/R2 baza (1 odr.) | R3/R6 baza (1 odr.) |
|-------|---------|---------------------|---------------------|
| **2026-08-04** | **Sezonska baza × 4** | **452,00 €** (113 × 4) | **588,00 €** (147 × 4) |
| **2026-08-05** | Standardna sezona (isto kao 6. 8.) | **113,00 €** | **147,00 €** |
| **2026-08-06+** | Standardna sezona srpanj–kolovoz | **113,00 €** | **147,00 €** |

Kanali: **Booking.com** (Channex push) + **Direct** (recepcija / booking.uzorita.hr).  
**R4** nije uključen.

---

## Formula

```
aug4_base = season_base × 4
```

| Soba | Sezonska baza (1 odr.) | **4. 8. baza (×4)** |
|------|------------------------|---------------------|
| R1, R2 | 113,00 € | **452,00 €** |
| R3, R6 | 147,00 € | **588,00 €** |

Stay.hr u `RatePlanDay.rate` pohranjuje **bazu za 1 odraslog**. Channex push = OBP **normal** cijena.

---

## Cijene po kanalu

### 4. kolovoza 2026. — Booking.com (OBP)

| Soba | Baza stay.hr (1 odr.) | Channex push (normal) | Booking 1 / 2 / 3 odr. |
|------|----------------------|----------------------|-------------------------|
| R1, R2 | 452,00 € | 457,00 € | 452 / 457 € |
| R3, R6 | 588,00 € | 598,00 € | 588 / 593 / 598 € |

### 5. i 6. kolovoza — sezona (Booking.com OBP)

| Soba | Baza | Channex push | Booking 1 / 2 / 3 odr. |
|------|------|--------------|-------------------------|
| R1, R2 | 113,00 € | 118,00 € | 113 / 118 € |
| R3, R6 | 147,00 € | 157,00 € | 147 / 152 / 157 € |

Direct kanal: isti iznosi baze; bez Channex pusha.

---

## Primijenjeno (audit)

| Stavka | Vrijednost |
|--------|------------|
| **Zadnja ispravka (UTC)** | 2026-06-11 |
| **4. 8.** | R1/R2 **452** (113×4), R3/R6 **588** (147×4) |
| **5. 8.** | R1/R2 **113**, R3/R6 **147** — **isto kao 6. 8.** |
| **Channex flush** | `python manage.py channex_ari_flush --tenant-slug uzorita` |
| **Outbox #269** | `restrictions`, **sent**, 4 values |
| **Channex task** | `d6c4c4e4-3bcd-41c6-9ad6-7129ca92bc17` |

### Naredbe (reprodukcija)

```python
from datetime import date
from decimal import Decimal
from apps.integrations.channex.ari_service import apply_rate_updates, get_active_channex_integration
from apps.integrations.models import SalesChannel

integration = get_active_channex_integration("uzorita")
AUG4 = {"R1": Decimal("452"), "R2": Decimal("452"), "R3": Decimal("588"), "R6": Decimal("588")}

for channel, push in [(SalesChannel.BOOKING_COM, True), (SalesChannel.DIRECT, False)]:
    apply_rate_updates(integration, [
        {"unit_code": u, "rate_plan_code": "standard", "sales_channel": channel,
         "date_from": date(2026, 8, 4), "date_to": date(2026, 8, 4), "rate": r}
        for u, r in AUG4.items()
    ], queue_push=push)
```

```bash
docker compose exec django python manage.py channex_ari_flush --tenant-slug uzorita
```

---

## Provjera u bazi

```sql
SELECT u.code, rpd.date, crp.sales_channel, rpd.rate
FROM integrations_rateplanday rpd
JOIN integrations_channelrateplan crp ON crp.id = rpd.rate_plan_id
JOIN properties_unit u ON u.id = crp.unit_id
JOIN tenants_tenant t ON t.id = rpd.tenant_id
WHERE t.slug = 'uzorita'
  AND rpd.date IN ('2026-08-04', '2026-08-05', '2026-08-06')
  AND u.code IN ('R1', 'R2', 'R3', 'R6')
ORDER BY rpd.date, u.code;
```

**Očekivano:**

| Datum | R1/R2 | R3/R6 |
|-------|-------|-------|
| 2026-08-04 | 452,00 | 588,00 |
| 2026-08-05 | 113,00 | 147,00 |
| 2026-08-06 | 113,00 | 147,00 |

**5. 8. = 6. 8.** (sezona). **4. 8. = sezona × 4.** Razlika 4. vs 5. 8. **namjerna**.

---

## Napomena o ranijim pogreškama (2026-06-11)

| Pokušaj | Greška | Ispravno |
|---------|--------|----------|
| 3× sezona na 4.+5. 8. | 339 / 441 oba dana | — |
| ×4 na **surge** (339×4) | 1356 / 1764 | **×4 na sezonu**: 452 / 588 |

---

## Povezano

- [channex-uzorita-booking-channel.md](../integrations/channex-uzorita-booking-channel.md)
