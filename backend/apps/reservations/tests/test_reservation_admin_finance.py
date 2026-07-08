from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.properties.models import Property
from apps.reservations.admin import ReservationAdmin
from apps.reservations.booking_payout_admin import extend_reservation_admin
from apps.reservations.booking_payout_models import BookingPayoutImport, BookingPayoutLine
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

User = get_user_model()


class ReservationAdminFinanceDisplayTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Hotel Demo",
            slug="hotel-demo",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="FIN-001",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            booker_name="Test Guest",
            amount=Decimal("92.65"),
            commission_amount=Decimal("16.68"),
            currency="EUR",
        )
        self.superuser = User.objects.create_superuser(
            username="admin_finance",
            password="test-pass-123",
            email="admin@stay.hr",
        )
        self.client = Client()
        self.client.force_login(self.superuser)
        self.change_url = reverse(
            "admin:reservations_reservation_change",
            args=[self.reservation.pk],
        )

    def test_change_form_shows_owner_net_label_and_value(self):
        response = self.client.get(self.change_url, HTTP_HOST="admin.stay.hr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Neto vlasniku")
        self.assertContains(response, "75.97")
        self.assertContains(response, "EUR")

    def test_owner_net_always_shows_two_decimal_places(self):
        self.reservation.amount = Decimal("100.00")
        self.reservation.commission_amount = Decimal("24.10")
        self.reservation.save(update_fields=["amount", "commission_amount"])

        response = self.client.get(self.change_url, HTTP_HOST="admin.stay.hr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "75.90")
        self.assertNotContains(response, ">75.9<")

    def test_change_form_without_payout_shows_fieldsets_and_empty_values(self):
        response = self.client.get(self.change_url, HTTP_HOST="admin.stay.hr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Financije (rezervacija)")
        self.assertContains(response, "Booking.com payout")
        self.assertNotContains(response, "74.77")
        self.assertNotContains(response, "PAYOUT-123")

        admin_instance = ReservationAdmin(Reservation, admin.site)
        empty_display = admin_instance.get_empty_value_display()
        content = response.content.decode()
        self.assertTrue(
            empty_display in content or "&mdash;" in content,
            msg=f"Expected empty display ({empty_display!r}) in change form",
        )

    def test_change_form_shows_booking_payout_section_and_net(self):
        self.reservation.booking_payout_net = Decimal("74.77")
        self.reservation.booking_payout_id = "PAYOUT-123"
        self.reservation.save(update_fields=["booking_payout_net", "booking_payout_id"])

        response = self.client.get(self.change_url, HTTP_HOST="admin.stay.hr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Booking.com payout")
        self.assertContains(response, "74.77")

    def test_change_form_links_payout_import_batch(self):
        import_batch = BookingPayoutImport.objects.create(
            tenant=self.tenant,
            property_obj=self.property,
            payout_id="PAY-LINK-001",
            payout_date=date(2026, 6, 11),
            currency="EUR",
            status="applied",
            source_file=ContentFile(b"Type\n", name="payout.csv"),
        )
        line = BookingPayoutLine.objects.create(
            import_batch=import_batch,
            line_number=1,
            booking_number="FIN-001",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            gross_amount=Decimal("92.65"),
            commission_amount=Decimal("16.68"),
            net_amount=Decimal("74.77"),
            currency="EUR",
        )
        self.reservation.booking_payout_line = line
        self.reservation.booking_payout_net = Decimal("74.77")
        self.reservation.save(update_fields=["booking_payout_line", "booking_payout_net"])

        response = self.client.get(self.change_url, HTTP_HOST="admin.stay.hr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("admin:reservations_bookingpayoutimport_change", args=[import_batch.pk]),
        )
        self.assertContains(response, "PAY-LINK-001")


class ExtendReservationAdminTests(TestCase):
    def test_extend_reservation_admin_is_idempotent(self):
        class BareReservationAdmin(admin.ModelAdmin):
            list_filter = ("status",)
            readonly_fields = ("booking_payout_net",)

        extend_reservation_admin(BareReservationAdmin)
        fieldset_count = len(BareReservationAdmin.fieldsets)
        readonly_count = len(BareReservationAdmin.readonly_fields)
        list_filter_count = len(BareReservationAdmin.list_filter)

        extend_reservation_admin(BareReservationAdmin)

        self.assertEqual(len(BareReservationAdmin.fieldsets), fieldset_count)
        self.assertEqual(len(BareReservationAdmin.readonly_fields), readonly_count)
        self.assertEqual(len(BareReservationAdmin.list_filter), list_filter_count)
        self.assertEqual(
            BareReservationAdmin.readonly_fields.count("booking_payout_net"),
            1,
        )

    def test_extend_appends_finance_fieldsets_after_existing(self):
        class PrefixedReservationAdmin(admin.ModelAdmin):
            fieldsets = (
                ("Guest", {"fields": ("booker_name", "booker_email")}),
            )

        extend_reservation_admin(PrefixedReservationAdmin)

        titles = [title for title, _ in PrefixedReservationAdmin.fieldsets]
        self.assertEqual(titles[0], "Guest")
        self.assertEqual(titles[-2], "Financije (rezervacija)")
        self.assertEqual(titles[-1], "Booking.com payout")

    def test_extend_handles_empty_fieldsets_tuple(self):
        class EmptyFieldsetsAdmin(admin.ModelAdmin):
            fieldsets = ()

        extend_reservation_admin(EmptyFieldsetsAdmin)

        titles = [title for title, _ in EmptyFieldsetsAdmin.fieldsets]
        self.assertEqual(titles, ["Financije (rezervacija)", "Booking.com payout"])
