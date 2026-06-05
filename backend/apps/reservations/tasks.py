from celery import shared_task


@shared_task(name="reservations.process_document_intake_job")
def process_document_intake_job_task(job_id: int) -> None:
    from apps.reservations.document_intake_service import process_document_intake_job

    process_document_intake_job(job_id)
