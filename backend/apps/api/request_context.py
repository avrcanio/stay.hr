"""HTTP kontekst za recepcijske API pozive."""

from __future__ import annotations

from django.http import HttpRequest

INSTALLATION_ID_HEADER = "HTTP_X_INSTALLATION_ID"


def installation_id_from_request(request: HttpRequest) -> str:
    return (request.META.get(INSTALLATION_ID_HEADER) or "").strip()
