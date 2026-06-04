# Hospira — timeline filter „danas rezervirano + otkazano“

**Repo:** [github.com/avrcanio/uzorita_flutter](https://github.com/avrcanio/uzorita_flutter) (`hr.finestar.hospira`)

Endpoint: `GET /api/v1/reception/reservations/`

---

## Kombinirani dnevni filter (preporučeno)

Za ekran **„today reservations & cancellations“** jedan API poziv:

```http
GET /api/v1/reception/reservations/?booked_from=YYYY-MM-DD&booked_to=YYYY-MM-DD&include_canceled=1
Authorization: Bearer {api_token}
```

| Parametar | Obavezno | Opis |
|-----------|----------|------|
| `booked_from` | da | Početak dana (uključivo), kalendarski dan u **Europe/Zagreb** |
| `booked_to` | da | Sljedeći dan (isključivo) — npr. za 5.6.: `booked_from=2026-06-05&booked_to=2026-06-06` |
| `include_canceled` | da (za combined) | `1`, `true` ili `yes` — uključuje i otkaze istog dana |

**Vraća union:**

- rezervacije **rezervirane** u tom danu (`booked_at`, status ≠ `canceled`)
- rezervacije **otkazane** u tom danu (`canceled_at`, status = `canceled`)

Sortirano po vremenu aktivnosti (najnovije prvo). Polja `booked_at`, `canceled_at` i `status` omogućuju razlikovanje u UI-u.

### Primjer — „danas“ u Flutteru

```dart
import 'package:timezone/timezone.dart' as tz;

final zagreb = tz.getLocation('Europe/Zagreb');
final now = tz.TZDateTime.now(zagreb);
final today = DateTime(now.year, now.month, now.day);
final tomorrow = today.add(const Duration(days: 1));

final uri = Uri.parse('$baseUrl/api/v1/reception/reservations/').replace(
  queryParameters: {
    'booked_from': _formatDate(today),
    'booked_to': _formatDate(tomorrow),
    'include_canceled': '1',
  },
);
```

**Ne koristiti UTC datum** za `booked_from`/`booked_to` — API koristi `[00:00, 00:00)` u Zagrebu.

---

## Alternativa — implicitni combined mode

Ako se pošalju **oba** para datuma (bez `include_canceled`), API također vraća union:

```http
GET /api/v1/reception/reservations/?booked_from=2026-06-05&booked_to=2026-06-06&canceled_from=2026-06-05&canceled_to=2026-06-06
```

Preporuka: koristiti `include_canceled=1` s jednim parom datuma — manje parametara, isti rezultat kad su rasponi jednaki.

---

## Samo rezervirano / samo otkazano (postojeće ponašanje)

| Filter | Parametri |
|--------|-----------|
| Samo **rezervirano danas** | `booked_from` + `booked_to` (bez `include_canceled`) — isključuje `canceled` |
| Samo **otkazano danas** | `canceled_from` + `canceled_to` |

---

## UI preporuke

| `status` | Prikaz |
|----------|--------|
| `expected`, `checked_in`, … | Nova rezervacija (zelena / neutralna) |
| `canceled` | Otkazano (badge, npr. crvena) |

Check-in datum (`check_in_date`) može biti u budućnosti (npr. 2027.) — filter je po **datumu rezervacije/otkaza**, ne po dolasku.

---

## Napomena o ponoći (timezone)

Otkazi nakon ponoći po Zagrebu ulaze u **sljedeći** kalendarski dan.

Primjer: otkaz u `2026-06-05 00:11` (Zagreb) → vidljiv u filteru za **5.6.**, ne za 4.6.

---

## Flutter todo (uzorita_flutter)

Na ekranu „today reservations & cancellations“:

1. Dodati `include_canceled=1` uz postojeći `booked_from`/`booked_to` poziv (ili zamijeniti dva odvojena poziva jednim).
2. Datum „danas“ računati u `Europe/Zagreb`, ne UTC.
3. Otkazane stavke vizualno označiti prema `status == "canceled"`.

Backend podrška dodana u `ReservationTimelineListView` (stay.hr, `reception_views.py`).
