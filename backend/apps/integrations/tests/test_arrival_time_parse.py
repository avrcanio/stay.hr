from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import TestCase

from apps.integrations.whatsapp.arrival_time_parse import parse_guest_stated_arrival
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

ZAGREB = ZoneInfo("Europe/Zagreb")


class ArrivalTimeParseTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
            timezone="Europe/Zagreb",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ana Anić",
            check_in=date(2026, 6, 7),
            check_out=date(2026, 6, 9),
        )

    def test_interval_upper_bound(self):
        parsed = parse_guest_stated_arrival("~ 18:00...19:00", self.reservation)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed, datetime(2026, 6, 7, 19, 0, tzinfo=ZAGREB))

    def test_dash_interval(self):
        parsed = parse_guest_stated_arrival("18-19", self.reservation)
        self.assertEqual(parsed, datetime(2026, 6, 7, 19, 0, tzinfo=ZAGREB))

    def test_single_time_colon(self):
        parsed = parse_guest_stated_arrival("Dolazim oko 18:30", self.reservation)
        self.assertEqual(parsed, datetime(2026, 6, 7, 18, 30, tzinfo=ZAGREB))

    def test_single_time_h_suffix(self):
        parsed = parse_guest_stated_arrival("oko 19h", self.reservation)
        self.assertEqual(parsed, datetime(2026, 6, 7, 19, 0, tzinfo=ZAGREB))

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_guest_stated_arrival("vidimo se kasnije", self.reservation))
