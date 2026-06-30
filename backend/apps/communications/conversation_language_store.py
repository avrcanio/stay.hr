"""Persisted conversation language on GuestMessageThreadState."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.communications.guest_language_constants import CONVERSATION_UPDATE_THRESHOLD
from apps.communications.guest_language_context import LanguageSource
from apps.communications.language_detection import DetectionResult
from apps.communications.models import GuestMessageThreadState
from apps.reservations.models import Reservation


@dataclass(frozen=True)
class StoredConversationLanguage:
    language: str
    source: LanguageSource
    updated_at: datetime | None


def load(reservation: Reservation) -> StoredConversationLanguage | None:
    try:
        state = reservation.guest_message_thread_state
    except GuestMessageThreadState.DoesNotExist:
        return None
    lang = (state.conversation_language or "").strip()
    if not lang:
        return None
    source_raw = (state.conversation_language_source or "").strip()
    try:
        source = LanguageSource(source_raw)
    except ValueError:
        source = LanguageSource.CONVERSATION
    return StoredConversationLanguage(
        language=lang,
        source=source,
        updated_at=state.conversation_language_updated_at,
    )


def maybe_update(
    reservation: Reservation,
    candidate: DetectionResult,
    *,
    channel: str,
    received_at: datetime | None = None,
) -> bool:
    """
    Update thread conversation language when detection confidence meets threshold.
    Returns True when persisted.
    """
    if candidate.confidence < CONVERSATION_UPDATE_THRESHOLD:
        return False
    if candidate.language in ("", "unknown"):
        return False

    state, _ = GuestMessageThreadState.objects.get_or_create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
    )
    state.conversation_language = candidate.language[:8]
    state.conversation_language_source = LanguageSource.MESSAGE.value
    state.conversation_language_updated_at = received_at or timezone.now()
    state.save(
        update_fields=[
            "conversation_language",
            "conversation_language_source",
            "conversation_language_updated_at",
        ]
    )
    return True
