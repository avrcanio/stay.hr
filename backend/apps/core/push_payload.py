"""Kanonski FCM data payload za Hospira recepciju."""

from __future__ import annotations


def reception_push_data(
    *,
    event_type: str,
    reservation_id: int,
    origin_installation_id: str = "",
    summary: str = "",
    **extra: str,
) -> dict[str, str]:
    """Svi ključevi i vrijednosti moraju biti stringovi (FCM data)."""
    payload: dict[str, str] = {
        "type": event_type,
        "reservation_id": str(reservation_id),
        "origin_installation_id": origin_installation_id.strip(),
        "summary": summary,
    }
    for key, value in extra.items():
        if value is not None:
            payload[str(key)] = str(value)
    return payload
