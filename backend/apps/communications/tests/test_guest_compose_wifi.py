from datetime import date

from django.test import TestCase

from apps.communications.guest_compose import (
    render_checkin_ready_message,
    render_evisitor_registered_message,
    render_operator_checkin_complete_message,
    render_post_checkin_guest_reply,
)
from apps.properties.models import Property
from apps.properties.uzorita_guest_info import UZORITA_GUEST_INFO
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class GuestComposeWifiTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita", default_language="hr")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita B&B",
            slug="uzorita",
            guest_info=UZORITA_GUEST_INFO,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="François Hartweg",
            booker_phone="+33674174251",
            booker_country="FR",
            check_in=date(2026, 6, 9),
            check_out=date(2026, 6, 10),
            status=Reservation.Status.CHECKED_IN,
        )

    def test_operator_checkin_complete_includes_wifi(self):
        text = render_operator_checkin_complete_message(self.reservation)
        self.assertIn("Uzoritarooms", text)
        self.assertIn("77777777", text)

    def test_evisitor_registered_includes_wifi(self):
        text = render_evisitor_registered_message(self.reservation)
        self.assertIn("Uzoritarooms", text)
        self.assertIn("77777777", text)

    def test_post_checkin_welcome_includes_wifi(self):
        text = render_post_checkin_guest_reply(
            self.reservation,
            mentions_arrival=False,
            mentions_parking=False,
            evening_welcome=False,
        )
        self.assertIn("Uzoritarooms", text)
        self.assertIn("77777777", text)

    def test_checkin_ready_excludes_wifi(self):
        text = render_checkin_ready_message(self.reservation)
        self.assertNotIn("Uzoritarooms", text)
        self.assertNotIn("77777777", text)
