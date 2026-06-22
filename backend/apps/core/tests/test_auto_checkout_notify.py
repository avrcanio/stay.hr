from unittest.mock import patch

from django.test import TestCase

from apps.core.tasks import (
    _auto_checkout_skipped_body,
    _primary_reservation_id_from_skipped,
    notify_auto_checkout_summary,
)


class AutoCheckoutNotifyTests(TestCase):
    def test_primary_reservation_id_from_single_skip(self):
        skipped = [{"reservation_id": 784, "booking_code": "6110027718"}]
        self.assertEqual(_primary_reservation_id_from_skipped(skipped), 784)

    def test_primary_reservation_id_from_multiple_skips(self):
        skipped = [
            {"reservation_id": 878, "booking_code": "6489463094"},
            {"reservation_id": 784, "booking_code": "6110027718"},
        ]
        self.assertEqual(_primary_reservation_id_from_skipped(skipped), 878)

    def test_skipped_body_includes_reservation_id(self):
        body = _auto_checkout_skipped_body(
            1,
            [{"reservation_id": 784, "booking_code": "6110027718"}],
        )
        self.assertIn("#784", body)
        self.assertIn("6110027718", body)

    @patch("apps.core.notifications.send_tenant_reception_push", return_value=["msg-1"])
    def test_notify_payload_uses_reservation_id(self, mock_push):
        skipped = [
            {
                "reservation_id": 784,
                "booking_code": "6110027718",
                "reason": "evisitor_incomplete",
                "check_out": "2026-06-26",
            }
        ]

        notify_auto_checkout_summary(2, skipped)

        mock_push.assert_called_once()
        data = mock_push.call_args.kwargs["data"]
        self.assertEqual(data["type"], "auto_checkout.skipped")
        self.assertEqual(data["reservation_id"], "784")
        self.assertIn("#784", mock_push.call_args.kwargs["body"])
