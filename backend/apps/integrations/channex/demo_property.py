"""
Channex staging demo property — matches certification + Booking.com test hotel setup.
"""

CHANNEX_DEMO_PROPERTY_SLUG = "channex-demo"
CHANNEX_DEMO_PROPERTY_TITLE = "Test Property - Stay.hr"
CHANNEX_DEMO_PROPERTY_ID = "e00e6034-c154-4754-b5d9-9fff73ad12f6"

# Channex PMS certification runs on stay.hr tenant Channex (id=3).
CHANNEX_CERT_TENANT_SLUG = "channex"
CHANNEX_CERT_TENANT_ID = 8

# Booking channel uses GBP; certification doc often mentions USD — use GBP for this test hotel.
CHANNEX_DEMO_CURRENCY = "GBP"

UZORITA_LOCATION = {
    "country": "HR",
    "country_name": "Croatia",
    "timezone": "Europe/Zagreb",
    "postal_code": "22000",
    "state_region": "Šibenik-Knin County",
    "city": "Šibenik",
    "address": "Ul. bana Josipa Jelačića 58",
    "latitude": "43.7357",
    "longitude": "15.8952",
}

CHANNEX_DEMO_CONTACT = {
    "email": "room_reservations@uzorita.hr",
    "phone": "+385915000000",
    "website": "https://www.uzorita.hr",
}
