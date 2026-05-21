"""Firebase Cloud Messaging via Admin SDK."""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_firebase_app = None
_firebase_init_attempted = False


class FirebaseNotConfiguredError(RuntimeError):
    """Raised when FCM is used but Firebase credentials are not configured."""


def is_firebase_configured() -> bool:
    return bool(getattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", ""))


def get_firebase_app():
    global _firebase_app, _firebase_init_attempted

    if _firebase_app is not None:
        return _firebase_app

    if _firebase_init_attempted:
        return None

    _firebase_init_attempted = True
    path = getattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", "")
    if not path:
        logger.info("Firebase not configured (FIREBASE_SERVICE_ACCOUNT_PATH empty)")
        return None

    import firebase_admin
    from firebase_admin import credentials

    cred = credentials.Certificate(path)
    options = {}
    project_id = getattr(settings, "FIREBASE_PROJECT_ID", "")
    if project_id:
        options["projectId"] = project_id

    try:
        _firebase_app = firebase_admin.get_app()
    except ValueError:
        _firebase_app = firebase_admin.initialize_app(cred, options or None)

    return _firebase_app


def send_fcm_message(
    *,
    token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> str:
    """
    Send a push notification to a single FCM device token.

    Data-only at the FCM root (no ``notification`` block) so iOS delivers
    ``FirebaseMessaging.onMessage`` in foreground. Title/body are duplicated in
    ``data`` for SnackBar/local notifications. Android still gets a system
    notification via ``AndroidConfig``.

    Returns the FCM message ID on success.
    """
    if not token:
        raise ValueError("FCM device token is required")

    app = get_firebase_app()
    if app is None:
        raise FirebaseNotConfiguredError(
            "Set FIREBASE_SERVICE_ACCOUNT_PATH to enable FCM."
        )

    from firebase_admin import messaging

    payload_data: dict[str, str] = {**(data or {})}
    payload_data["title"] = title
    payload_data["body"] = body

    message = messaging.Message(
        data=payload_data,
        token=token,
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                title=title,
                body=body,
                channel_id="hospira_reception",
            ),
        ),
        apns=messaging.APNSConfig(
            headers={"apns-priority": "10"},
            payload=messaging.APNSPayload(
                aps=messaging.Aps(content_available=True),
            ),
        ),
    )
    message_id = messaging.send(message, app=app)
    logger.info("FCM message sent id=%s", message_id)
    return message_id
