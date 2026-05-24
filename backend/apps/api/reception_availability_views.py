from __future__ import annotations

from django.utils.dateparse import parse_date
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_views import ReceptionReadView
from apps.properties.models import Unit
from apps.reservations.availability import unit_blocked_nights
from apps.reservations.models import Reservation, ReservationUnit

MAX_AVAILABILITY_RANGE_DAYS = 366


class ReceptionUnitAvailabilityView(ReceptionReadView, APIView):
    def get(self, request, unit_id: int):
        unit = (
            Unit.objects.for_tenant(request.tenant)
            .filter(pk=unit_id, is_active=True)
            .first()
        )
        if unit is None:
            raise NotFound("Unit not found.")

        from_date = parse_date((request.query_params.get("from") or "").strip())
        to_date = parse_date((request.query_params.get("to") or "").strip())
        if from_date is None or to_date is None:
            raise ValidationError({"detail": "Query params from and to (YYYY-MM-DD) are required."})
        if to_date <= from_date:
            raise ValidationError({"detail": "to must be after from."})
        if (to_date - from_date).days > MAX_AVAILABILITY_RANGE_DAYS:
            raise ValidationError(
                {"detail": f"Date range must not exceed {MAX_AVAILABILITY_RANGE_DAYS} days."}
            )

        exclude_reservation_id = None
        exclude_raw = (request.query_params.get("exclude_reservation_id") or "").strip()
        if exclude_raw:
            try:
                exclude_reservation_id = int(exclude_raw)
            except ValueError as exc:
                raise ValidationError(
                    {"exclude_reservation_id": "Must be an integer reservation id."}
                ) from exc
            reservation_exists = ReservationUnit.objects.filter(
                tenant=request.tenant,
                unit_id=unit.id,
                reservation_id=exclude_reservation_id,
            ).exists()
            if not reservation_exists:
                raise NotFound("Reservation not found for this unit.")

        blocked = unit_blocked_nights(
            request.tenant,
            unit.id,
            from_date,
            to_date,
            exclude_reservation_id=exclude_reservation_id,
        )
        return Response(
            {
                "unit_id": unit.id,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "blocked_nights": [night.isoformat() for night in blocked],
            }
        )
