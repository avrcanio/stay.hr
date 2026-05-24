from __future__ import annotations

from django.utils.dateparse import parse_date
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_views import ReceptionReadView, ReceptionWriteView
from apps.integrations.models import UnitAvailabilityBlock
from apps.integrations.smoobu.blocking_service import block_apartment_dates, unblock_apartment_dates
from apps.integrations.smoobu.calendar_blocks_service import list_calendar_blocks, validate_block_request
from apps.integrations.smoobu.exceptions import SmoobuApiError, SmoobuConfigError, SmoobuRatesError
from apps.integrations.smoobu.resolver import get_active_smoobu_integration
from apps.properties.models import Unit


class ReceptionCalendarBlocksView(ReceptionReadView, APIView):
    def get(self, request):
        date_from = parse_date((request.query_params.get("from") or "").strip())
        date_to = parse_date((request.query_params.get("to") or "").strip())
        if date_from is None or date_to is None:
            raise ValidationError({"detail": "Query params from and to (YYYY-MM-DD) are required."})
        if date_to < date_from:
            raise ValidationError({"detail": "to must be on or after from."})

        blocks = list_calendar_blocks(
            request.tenant,
            date_from=date_from,
            date_to=date_to,
        )
        return Response(blocks)


class UnitBlockCreateSerializer(serializers.Serializer):
    check_in = serializers.DateField()
    check_out = serializers.DateField()


class ReceptionUnitBlockCreateView(ReceptionWriteView, APIView):
    def post(self, request, unit_id: int):
        unit = Unit.objects.for_tenant(request.tenant).filter(pk=unit_id, is_active=True).first()
        if unit is None:
            raise NotFound("Soba nije pronađena.")

        serializer = UnitBlockCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        check_in = serializer.validated_data["check_in"]
        check_out = serializer.validated_data["check_out"]

        try:
            validate_block_request(request.tenant, unit, check_in, check_out)
            integration = get_active_smoobu_integration(request.tenant.slug)
            result = block_apartment_dates(
                integration,
                unit_code=unit.code,
                check_in=check_in,
                check_out=check_out,
            )
        except SmoobuConfigError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except SmoobuRatesError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except SmoobuApiError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        return Response(result, status=status.HTTP_201_CREATED)


class ReceptionUnitBlockDeleteView(ReceptionWriteView, APIView):
    def delete(self, request, block_id: int):
        block_row = (
            UnitAvailabilityBlock.objects.for_tenant(request.tenant)
            .filter(pk=block_id)
            .select_related("unit")
            .first()
        )
        if block_row is None:
            raise NotFound("Blok nije pronađen.")

        if block_row.created_via != UnitAvailabilityBlock.CreatedVia.HOSPIRA:
            return Response(
                {"detail": "Only Hospira-created blocks can be unblocked."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if block_row.reservation_id is not None:
            return Response(
                {
                    "detail": (
                        "Blok je vezan uz rezervaciju i ne može se ručno ukloniti. "
                        "Otkažite rezervaciju da se ukloni blok na Booking.com."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            unblock_apartment_dates(block_row)
        except SmoobuRatesError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except SmoobuApiError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        return Response(status=status.HTTP_204_NO_CONTENT)
