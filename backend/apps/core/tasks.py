from celery import shared_task


@shared_task
def ping() -> str:
    return "pong"


@shared_task
def send_push_notification(
    token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> str:
    from apps.core.firebase import send_fcm_message

    return send_fcm_message(token=token, title=title, body=body, data=data)
