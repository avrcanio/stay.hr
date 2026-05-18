from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class ApiTokenEncryptionError(Exception):
    """Missing or invalid API token encryption settings."""


def _fernet() -> Fernet:
    key = (getattr(settings, "STAY_INTEGRATION_FERNET_KEY", None) or "").strip()
    if not key:
        raise ApiTokenEncryptionError(
            "STAY_INTEGRATION_FERNET_KEY nije postavljen (potreban za pohranu API tokena)."
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (TypeError, ValueError) as exc:
        raise ApiTokenEncryptionError(
            "STAY_INTEGRATION_FERNET_KEY nije valjani Fernet ključ."
        ) from exc


def encrypt_api_token(raw: str) -> str:
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode("utf-8")).decode("ascii")


def decrypt_api_token(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ApiTokenEncryptionError(
            "Ne mogu dešifrirati API token (pogrešan STAY_INTEGRATION_FERNET_KEY?)."
        ) from exc
