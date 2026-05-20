from __future__ import annotations

import urllib.error
import urllib.request

from apps.integrations.smoobu.mapping import SMOOBU_API_BASE


class SmoobuKeyVerificationError(Exception):
    """Raised when the API key cannot be validated against Smoobu."""


def verify_smoobu_api_key(api_key: str, *, api_base: str = SMOOBU_API_BASE) -> dict:
    """
    Validate credentials with GET /api/me (200 = ok, 401 = invalid key).
    Returns parsed JSON on success.
    """
    key = api_key.strip()
    if not key:
        raise SmoobuKeyVerificationError("Smoobu API ključ je prazan.")

    url = f"{api_base.rstrip('/')}/api/me"
    request = urllib.request.Request(
        url,
        headers={
            "Api-Key": key,
            "Cache-Control": "no-cache",
            # Cloudflare blocks default Python urllib UA (error 1010).
            "User-Agent": "stay.hr/1.0 (+https://stay.hr)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise SmoobuKeyVerificationError(
                    f"Smoobu /api/me vratio status {response.status}."
                )
            import json

            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise SmoobuKeyVerificationError(
                "Smoobu odbio API ključ (401). Rotirajte ključ u Smoobu Advanced → API Keys."
            ) from exc
        raise SmoobuKeyVerificationError(f"Smoobu /api/me greška: HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise SmoobuKeyVerificationError(f"Ne mogu kontaktirati Smoobu: {exc.reason}.") from exc

    if not isinstance(body, dict) or "id" not in body:
        raise SmoobuKeyVerificationError("Neočekivan odgovor Smoobu /api/me.")
    return body
