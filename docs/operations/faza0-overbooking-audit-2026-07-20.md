# Faza 0 audit — overbooking / multi-room (tenant 2 Uzorita)

**Datum:** 2026-07-20  
**Opseg:** read-only detekcija (`detect_overbooking`, `reconcile_booking_units`, `find_all_multi_room_gaps`)  
**Nije urađeno:** ops rješavanje #1008 (cancel / relocacija / check-in block)

```bash
docker compose exec django python manage.py detect_overbooking --tenant-id 2 --from-date 2026-07-20
docker compose exec django python manage.py reconcile_booking_units --tenant-id 2 --only-issues
docker compose exec django python manage.py detect_multi_room_gaps --tenant-id 2 --from-date 2026-07-20
```

---

## 1) Overbooking konflikti (`detect_overbooking`)

**Broj:** 1

| Unit | Overlap | OSTAJE | AKCIJA |
|------|---------|--------|--------|
| **R3** | 2026-07-20 .. 2026-07-21 | **#159** Lada Rakigjija `5865972471` — R2+R3+R6, `expected`, `units_count=3` | **#1008** Primož Juhart `6946148952` — R3, `expected`, `units_count=1` |

Napomena (bez ops): #159 notes još referenciraju stariji R3 konflikt sa Sandy Bowser `5461475045`; trenutni aktivni conflict pair je **#159 vs #1008**.

---

## 2) Multi-room inventory gaps (`units_count` vs mapped `ReservationUnit`)

**Broj:** 0  

Nema rezervacija gdje je `units_count >= 2` a mapped units manje od `units_count` (od 2026-07-20 nadalje).

---

## 3) Multi-room gaps — Channex calendar mismatch (`mapped >= 2`, Channex rooms < mapped)

**Broj:** 15 (svi `channex_rooms=0` u lokalnoj revision; stay.hr mapping kompletan)

| # | Booking | Gost | Noć | units | PDF lock |
|---|---------|------|-----|-------|----------|
| 159 | 5865972471 | Lada Rakigjija | 20.–21.7. | 3 | da |
| 82 | 5796838012 | Susanne mayer | 24.–25.7. | 4 | da |
| 945 | 5980557818 | Jolanta Zvīgzne | 29.–30.7. | 2 | ne |
| 995 | 5729650393 | Olewczyńska Anita | 30.–31.7. | 2 | ne |
| 857 | 5564421243 | Julie Bernard | 31.7.–1.8. | 2 | ne |
| 869 | 6347637695 | Andrzej Brzozowski | 31.7.–1.8. | 2 | ne |
| 708 | 6104960555 | Philippe RULFO | 15.–16.8. | 2 | da |
| 936 | 5954431983 | Dorota Dobrzyń-Matusiak | 16.–17.8. | 2 | ne |
| 969 | 6355795319 | Merowj Taqi | 20.–21.8. | 2 | ne |
| 889 | 5850283384 | Filipe Ribeiro | 29.–30.8. | 2 | ne |
| 154 | 6895655754 | Marcel Droste | 12.–13.9. | 2 | ne |
| 201 | 6689193987 | Ivo Sousa | 12.–13.9. | 2 | ne |
| 1026 | 6401890535 | JOSE MARIA JIMENEZ GONZALEZ | 29.–30.9. | 2 | ne |
| 920 | 5516240346 | Josef Géba | 26.–27.2.2027 | 2 | ne |
| 1001 | 6590460631 | CHANG JEN CHIAO | 25.–26.7.2027 | 3 | ne |

Ovo je ulaz za Fazu 1 **verify/repair ARI** (zatvaranje inventara), ne za ručni cancel gostiju.

---

## 4) Reconcile (`reconcile_booking_units --only-issues`)

- Skenirano: **266** rezervacija (units_count≥2 ili channex import)
- S issue flagom: **229** — većina je šum `Channex rooms=0` / `Nema Channex revision` na single-room bookingima
- High-signal (future multi-room + PDF lock mismatch): **#159, #82, #708** (vidi tablicu gore)
- Ostalih multi-room `rooms=0`: **12** (isti skup kao §3 minus PDF-lock trio)

---

## 5) Popis prioriteta (bez ops #1008)

1. **Konflikt R3 danas:** #159 (Lada) vs **#1008 (Primož)** — ostaje za kasniji ops ticket; ovaj PR samo detekcija/inventar.
2. **ARI under-report rizik:** 15 multi-room rezervacija s `channex_rooms=0` dok stay.hr ima 2–4 mapped sobe — kandidati za `verify_channex_availability` / ARI re-push.
3. **Nema unit-mapping rupa** u stay.hr za buduće multi-room (`gap_count=0`).

---

## Raw CLI izlaz (overbooking)

```
Tenant 2 (Uzorita): 1 conflict(s).
R3  overlap 2026-07-20 .. 2026-07-21
  OSTAJE:     channex:… Lada Rakigjija (check-in 2026-07-20)   → #159
  AKCIJA:     channex:… Primož Juhart (check-in 2026-07-20)    → #1008
```

---

## 6) Post-deploy smoke — `verify_channex_availability` (tenant 2 / uzorita)

**Datum:** 2026-07-20 (nakon deploy Faza 1 verify/repair)

```bash
docker compose exec django python manage.py verify_channex_availability \
  --tenant-slug uzorita --from-date 2026-07-20 --days 90 --dry-run
docker compose exec django python manage.py verify_channex_availability \
  --tenant-slug uzorita --from-date 2026-07-20 --days 90
```

**Rezultat:** `units=5 mismatches=0 repaired=0` (raspon 2026-07-20 .. 2026-10-17).  
stay.hr occupancy i live Channex GET `/availability` su usklađeni za mapirane unitove; #1008 overbooking konflikt ostaje ops ticket (nije inventar mismatch).
