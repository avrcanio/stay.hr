from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from apps.integrations.exceptions import IntegrationEncryptionError


def _fernet() -> Fernet:
    key = (getattr(settings, "STAY_INTEGRATION_FERNET_KEY", None) or "").strip()
    if not key:
        raise IntegrationEncryptionError(
            "STAY_INTEGRATION_FERNET_KEY nije postavljen (potreban za šifriranje integracija)."
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (TypeError, ValueError) as exc:
        raise IntegrationEncryptionError("STAY_INTEGRATION_FERNET_KEY nije valjani Fernet ključ.") from exc


def encrypt_config(data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_config(token: str) -> dict[str, Any]:
    if not token:
        return {}
    try:
        raw = _fernet().decrypt(token.encode("ascii"))
    except InvalidToken as exc:
        raise IntegrationEncryptionError("Ne mogu dešifrirati IntegrationConfig (pogrešan ključ?).") from exc
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise IntegrationEncryptionError("Dešifrirani IntegrationConfig nije JSON objekt.")
    return parsed
