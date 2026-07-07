"""Reception report API endpoints."""

from __future__ import annotations

import io

from django.http import FileResponse
from rest_framework import serializers, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_report_serializers import property_financial_report_to_dict
from apps.api.reception_views import ReceptionReadView, ReceptionWriteView
from apps.reservations.reports.delivery import deliver_property_financial_report_email
from apps.reservations.reports.exports.excel import (
    property_financial_report_xlsx_filename,
    render_property_financial_report_xlsx,
)
from apps.reservations.reports.exports.pdf import (
    property_financial_report_pdf_filename,
    render_property_financial_report_pdf,
)
from apps.reservations.reports.property_financial_report import build_property_financial_report
from apps.reservations.reports.recipients import parse_financial_report_recipients
from apps.reservations.reports.types import PropertyFinancialReportParams, PropertyFinancialReportParamsError

_EXPORT_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class PropertyFinancialReportSendEmailSerializer(serializers.Serializer):
    property_slug = serializers.CharField()
    check_out_from = serializers.DateField()
    check_out_to = serializers.DateField()
    recipients = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=False,
    )


class PropertyFinancialReportView(ReceptionReadView):
    def perform_content_negotiation(self, request, force=False):
        # DRF treats ?format= as content negotiation; exports are handled in get().
        return (JSONRenderer(), "application/json")

    def get(self, request):
        try:
            params = PropertyFinancialReportParams.from_query(
                request.tenant,
                property_slug=request.query_params.get("property_slug"),
                check_out_from=request.query_params.get("check_out_from"),
                check_out_to=request.query_params.get("check_out_to"),
            )
        except PropertyFinancialReportParamsError as exc:
            payload: dict = {"code": exc.code}
            if exc.detail:
                payload["detail"] = exc.detail
            if exc.max_days is not None:
                payload["max_days"] = exc.max_days
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)

        export_format = (request.query_params.get("format") or "json").strip().lower()
        if export_format not in {"json", "pdf", "xlsx"}:
            return Response({"code": "format_invalid"}, status=status.HTTP_400_BAD_REQUEST)

        result = build_property_financial_report(params)

        if export_format == "pdf":
            return FileResponse(
                io.BytesIO(render_property_financial_report_pdf(result)),
                as_attachment=True,
                filename=property_financial_report_pdf_filename(result),
                content_type=_EXPORT_CONTENT_TYPES["pdf"],
            )
        if export_format == "xlsx":
            return FileResponse(
                io.BytesIO(render_property_financial_report_xlsx(result)),
                as_attachment=True,
                filename=property_financial_report_xlsx_filename(result),
                content_type=_EXPORT_CONTENT_TYPES["xlsx"],
            )

        return Response(property_financial_report_to_dict(result))


class PropertyFinancialReportSendEmailView(ReceptionWriteView, APIView):
    def post(self, request):
        serializer = PropertyFinancialReportSendEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            params = PropertyFinancialReportParams.from_query(
                request.tenant,
                property_slug=data["property_slug"],
                check_out_from=data["check_out_from"].isoformat(),
                check_out_to=data["check_out_to"].isoformat(),
            )
        except PropertyFinancialReportParamsError as exc:
            payload: dict = {"code": exc.code}
            if exc.detail:
                payload["detail"] = exc.detail
            if exc.max_days is not None:
                payload["max_days"] = exc.max_days
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)

        recipients = data.get("recipients")
        if recipients:
            normalized = parse_financial_report_recipients(",".join(recipients))
        else:
            normalized = parse_financial_report_recipients(params.property.financial_report_recipients)

        if not normalized:
            return Response({"code": "no_recipient"}, status=status.HTTP_400_BAD_REQUEST)

        outcome = deliver_property_financial_report_email(params, recipients=normalized)
        if outcome.get("status") != "sent":
            reason = outcome.get("reason", "send_failed")
            code = reason if reason in {"no_smtp", "no_from_address"} else "send_failed"
            return Response({"code": code}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "status": "sent",
                "recipients": outcome.get("recipients", []),
                "subject": outcome.get("subject"),
                "reservation_count": outcome.get("reservation_count"),
            }
        )
