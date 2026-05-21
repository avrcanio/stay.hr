from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.core.firebase import (
    FirebaseNotConfiguredError,
    is_firebase_configured,
    send_fcm_message,
)


class FirebaseConfigTests(SimpleTestCase):
    def test_not_configured_when_path_empty(self):
        with override_settings(FIREBASE_SERVICE_ACCOUNT_PATH=""):
            self.assertFalse(is_firebase_configured())

    def test_configured_when_path_set(self):
        with override_settings(FIREBASE_SERVICE_ACCOUNT_PATH="/run/secrets/firebase-service-account.json"):
            self.assertTrue(is_firebase_configured())


@override_settings(FIREBASE_SERVICE_ACCOUNT_PATH="")
class SendFcmMessageTests(SimpleTestCase):
    def test_raises_when_not_configured(self):
        with self.assertRaises(FirebaseNotConfiguredError):
            send_fcm_message(token="abc", title="Hi", body="Test")

    def test_raises_on_empty_token(self):
        with self.assertRaises(ValueError):
            send_fcm_message(token="", title="Hi", body="Test")


@override_settings(
    FIREBASE_SERVICE_ACCOUNT_PATH="/run/secrets/firebase-service-account.json",
    FIREBASE_PROJECT_ID="hospira-fc0dc",
)
class SendFcmMessageConfiguredTests(SimpleTestCase):
    @patch("apps.core.firebase.get_firebase_app")
    @patch("firebase_admin.messaging.send")
    def test_sends_data_only_message(self, mock_send, mock_get_app):
        mock_get_app.return_value = MagicMock()
        mock_send.return_value = "projects/hospira-fc0dc/messages/msg-1"

        message_id = send_fcm_message(
            token="device-token-123",
            title="Check-in",
            body="Guest arrived",
            data={"type": "reservation.status_changed", "reservation_id": "42"},
        )

        self.assertEqual(message_id, "projects/hospira-fc0dc/messages/msg-1")
        mock_send.assert_called_once()
        sent_message = mock_send.call_args[0][0]
        self.assertEqual(sent_message.token, "device-token-123")
        self.assertIsNone(sent_message.notification)
        self.assertEqual(
            sent_message.data,
            {
                "type": "reservation.status_changed",
                "reservation_id": "42",
                "title": "Check-in",
                "body": "Guest arrived",
            },
        )
        self.assertEqual(sent_message.android.notification.title, "Check-in")
        self.assertEqual(sent_message.android.notification.body, "Guest arrived")
        self.assertTrue(sent_message.apns.payload.aps.content_available)
        self.assertIsNone(sent_message.apns.payload.aps.alert)
