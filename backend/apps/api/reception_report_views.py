"""Reception report API endpoints."""

from __future__ import annotations

import io

from django.http import FileResponse
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from apps.api.reception_report_serializers import property_financial_report_to_dict
from apps.api.reception_views import ReceptionReadView
from apps.reservations.reports.exports.excel import (
    property_financial_report_xlsx_filename,
    render_property_financial_report_xlsx,
)
from apps.reservations.reports.exports.pdf import (
    property_financial_report_pdf_filename,
    render_property_financial_report_pdf,
)
from apps.reservations.reports.property_financial_report import build_property_financial_report
from apps.reservations.reports.types import PropertyFinancialReportParams, PropertyFinancialReportParamsError

_EXPORT_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


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
