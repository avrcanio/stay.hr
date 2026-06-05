"""Reception document intake API (WhatsApp share batch OCR)."""

from __future__ import annotations

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_views import ReceptionWriteView, _max_photo_bytes, _validate_photo_file
from apps.api.request_context import installation_id_from_request
from apps.reservations.document_intake_service import (
    apply_document_intake_job,
    job_to_dict,
    process_document_intake_job,
)
from apps.reservations.models import DocumentIntakeImage, DocumentIntakeJob, DocumentIntakeJobStatus
from apps.reservations.tasks import process_document_intake_job_task

MAX_IMAGES = 20


class DocumentIntakeBatchSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        max_length=MAX_IMAGES,
    )

    def validate_files(self, value):
        validated = []
        for item in value:
            validated.append(_validate_photo_file(item))
        return validated


class DocumentIntakeApplySerializer(serializers.Serializer):
    persons = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class DocumentIntakeBatchView(ReceptionWriteView, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        files = request.FILES.getlist("files")
        if not files:
            single = request.FILES.get("file")
            if single:
                files = [single]
        if not files:
            return Response(
                {"detail": "Nema datoteka (files[])."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(files) > MAX_IMAGES:
            return Response(
                {"detail": f"Maksimalno {MAX_IMAGES} slika."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for f in files:
            if f.size > _max_photo_bytes():
                return Response(
                    {"detail": f"Datoteka prevelika (max {_max_photo_bytes()} bajtova)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        device_id = installation_id_from_request(request) or ""
        job = DocumentIntakeJob.objects.create(
            tenant=request.tenant,
            device_id=device_id,
            status=DocumentIntakeJobStatus.QUEUED,
        )

        for idx, uploaded in enumerate(files):
            DocumentIntakeImage.objects.create(
                tenant=request.tenant,
                job=job,
                image=uploaded,
                sort_order=idx,
            )

        return Response(
            {
                "job_id": job.pk,
                "image_count": len(files),
                "status": job.status,
            },
            status=status.HTTP_201_CREATED,
        )


class DocumentIntakeJobProcessView(ReceptionWriteView, APIView):
    def post(self, request, job_id: int):
        job = DocumentIntakeJob.objects.filter(tenant=request.tenant, pk=job_id).first()
        if job is None:
            return Response({"detail": "Job nije pronađen."}, status=status.HTTP_404_NOT_FOUND)

        if job.status in {DocumentIntakeJobStatus.PROCESSING, DocumentIntakeJobStatus.APPLIED}:
            return Response(job_to_dict(job, request=request))

        job.status = DocumentIntakeJobStatus.QUEUED
        job.error_message = ""
        job.save(update_fields=["status", "error_message", "updated_at"])

        eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
        if eager:
            process_document_intake_job(job.pk)
        else:
            try:
                process_document_intake_job_task.delay(job.pk)
            except Exception:
                process_document_intake_job(job.pk)

        job.refresh_from_db()
        return Response(job_to_dict(job, request=request))


class DocumentIntakeJobDetailView(ReceptionWriteView, APIView):
    def get(self, request, job_id: int):
        job = DocumentIntakeJob.objects.filter(tenant=request.tenant, pk=job_id).first()
        if job is None:
            return Response({"detail": "Job nije pronađen."}, status=status.HTTP_404_NOT_FOUND)
        return Response(job_to_dict(job, request=request))


class DocumentIntakeJobApplyView(ReceptionWriteView, APIView):
    def post(self, request, job_id: int):
        job = DocumentIntakeJob.objects.filter(tenant=request.tenant, pk=job_id).first()
        if job is None:
            return Response({"detail": "Job nije pronađen."}, status=status.HTTP_404_NOT_FOUND)

        serializer = DocumentIntakeApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        selections = serializer.validated_data.get("persons") or []

        device_id = installation_id_from_request(request) or job.device_id or ""
        try:
            applied = apply_document_intake_job(
                job.pk,
                selections=selections,
                device_id=device_id,
                request=request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        job.refresh_from_db()
        return Response(
            {
                "job_id": job.pk,
                "status": job.status,
                "applied": applied,
                "job": job_to_dict(job, request=request),
            }
        )
