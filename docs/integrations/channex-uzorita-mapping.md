# Channex — Uzorita room type mapping (staging)

Four physical units on Channex staging (each room type has **Count Of Rooms = 1**).

| stay.hr `Unit.code` | Channex title | Channex room type UUID |
|---------------------|---------------|-------------------------|
| R1 | Deluxe King 1 | `e8fc8060-3df5-4e49-bee9-32903786b4ee` |
| R2 | Luxury Room Uzorita - R2 | `0d852a5e-41d5-4801-9bf1-679deabcfbec` |
| D1 | Deluxe Double | `ecc2d4ab-7894-4fc9-8e20-c08d2317e4be` |
| R3 | Luxury Room Uzorita - R3 | `6058e4da-0ed4-48a1-a877-fec38685589a` |

Booking.com listing names may differ; map each channel listing to the matching Channex room type UUID in [staging channels](https://staging.channex.io/channels).

## Booking.com test hotel (certification channel)

| Field | Value |
|-------|--------|
| Channel ID | `8ee9c7aa-6433-4037-924b-4f95598782d5` (Demo tenant → Test Property - Stay.hr) |
| Booking hotel ID | `10745030` (GBP test account) |
| stay.hr property slug | `channex-bcom-test` |

| Booking room | Booking ID | stay.hr unit | Adults | Channex room type |
|--------------|------------|--------------|--------|-------------------|
| Holiday Home | 1074503007 | `BCOM-HOLIDAY` | 11 | `430b1381-dace-44d6-8d5d-a0a1025819fc` |
| Studio | 1074503008 | `BCOM-STUDIO` | 2 | `18c437d7-13e3-4dbc-9565-48fad4832bf5` |

Seed:

```bash
docker compose run --rm django python manage.py seed_channex_booking_test_property --tenant-slug uzorita
docker compose run --rm django python manage.py seed_channex_booking_test_property --tenant-slug demo --also-demo
```

## Store mapping in stay.hr

```bash
# Set from Channex UI (Property + API key), then:
docker compose run --rm django python manage.py seed_uzorita_channex_config \
  --property-id YOUR_CHANNEX_PROPERTY_UUID \
  --api-key YOUR_STAGING_API_KEY
```

Config is saved as encrypted `IntegrationConfig` (`provider=channex`) for tenant `uzorita`.

Code: `backend/apps/integrations/channex/mapping.py`
