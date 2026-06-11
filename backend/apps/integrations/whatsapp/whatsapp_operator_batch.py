from __future__ import annotations

import logging
import uuid

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.integrations.whatsapp.integration_lookup import get_active_whatsapp_integration
from apps.integrations.whatsapp.whatsapp_operator_service import (
    _send_operator_docs_confirm_prompt,
)
from apps.reservations.models import WhatsAppOperatorSession, WhatsAppOperatorSessionStatus

logger = logging.getLogger(__name__)

OPERATOR_QUIET_SECONDS = 10
_TIMER_CACHE_PREFIX = "wa-op-timer"
_TIMER_CACHE_TTL = 3600

_ACTIVE_PROMPT_STATUSES = frozenset(
    {
        WhatsAppOperatorSessionStatus.COLLECTING,
        WhatsAppOperatorSessionStatus.AWAITING_CONFIRM,
    }
)


def send_operator_collect_prompt_for_session(session_id: int) -> dict:
    session = (
        WhatsAppOperatorSession.objects.select_related("job", "tenant")
        .filter(pk=session_id)
        .first()
    )
    if session is None:
        return {"status": "missing"}

    if session.status != WhatsAppOperatorSessionStatus.COLLECTING:
        return {"status": "skipped", "reason": "not_collecting"}

    integration_row, runtime = get_active_whatsapp_integration(session.tenant)
    if integration_row is None or runtime is None:
        return {"status": "skipped", "reason": "no_integration"}

    image_count = session.job.images.count()
    if image_count == 0:
        return {"status": "skipped", "reason": "no_images"}

    send_result = _send_operator_docs_confirm_prompt(
        integration_row=integration_row,
        runtime=runtime,
        operator_wa_id=session.operator_wa_id,
    )
    session.status = WhatsAppOperatorSessionStatus.AWAITING_CONFIRM
    session.last_activity_at = timezone.now()
    session.save(update_fields=["status", "last_activity_at", "updated_at"])
    return {"status": "prompted", "send": send_result}


def _timer_cache_key(session_id: int, suffix: str) -> str:
    return f"{_TIMER_CACHE_PREFIX}:{session_id}:{suffix}"


def _revoke_scheduled(session_id: int, suffix: str) -> None:
    from config.celery import app

    cache_key = _timer_cache_key(session_id, suffix)
    task_id = cache.get(cache_key)
    if not task_id:
        return
    app.control.revoke(task_id, terminate=False)
    cache.delete(cache_key)


def _schedule_task(*, task, session_id: int, countdown: int, suffix: str):
    _revoke_scheduled(session_id, suffix)
    task_id = f"wa-op-{suffix}-{session_id}-{uuid.uuid4().hex[:12]}"
    cache.set(_timer_cache_key(session_id, suffix), task_id, timeout=_TIMER_CACHE_TTL)
    return task.apply_async(args=[session_id], countdown=countdown, task_id=task_id)


def schedule_operator_quiet_timer(session: WhatsAppOperatorSession) -> None:
    _schedule_task(
        task=operator_collect_quiet_elapsed,
        session_id=session.pk,
        countdown=OPERATOR_QUIET_SECONDS,
        suffix="quiet",
    )


@shared_task
def operator_collect_quiet_elapsed(session_id: int) -> dict:
    session = (
        WhatsAppOperatorSession.objects.select_related("job", "tenant")
        .filter(pk=session_id)
        .first()
    )
    if session is None:
        return {"status": "missing"}

    if session.status not in _ACTIVE_PROMPT_STATUSES:
        return {"status": "skipped", "reason": "not_collecting"}

    if not session.job.images.exists():
        return {"status": "skipped", "reason": "no_images"}

    return send_operator_collect_prompt_for_session(session.pk)
