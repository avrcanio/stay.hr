from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.models import WhatsAppInboundRouting
from apps.integrations.whatsapp.platform_inbound_router import (
    dismiss_routing,
    manual_link_routing,
)
from apps.reservations.models import Reservation


class PlatformUnroutedLinkSerializer(serializers.Serializer):
    reservation_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PlatformUnroutedDismissSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PlatformWhatsAppUnroutedView(APIView):
    """Superuser platform API for unrouted WhatsApp inbox."""

    def get(self, request):
        if not request.user.is_superuser:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        status_filter = (request.query_params.get("status") or "unrouted,ambiguous").strip()
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        qs = (
            WhatsAppInboundRouting.objects.filter(status__in=statuses)
            .select_related(
                "message",
                "resolved_tenant",
                "resolved_reservation",
            )
            .order_by("-created_at")[:100]
        )
        items = []
        for row in qs:
            msg = row.message
            items.append(
                {
                    "id": row.pk,
                    "status": row.status,
                    "routing_method": row.routing_method,
                    "created_at": row.created_at.isoformat(),
                    "message": {
                        "id": msg.pk,
                        "wamid": msg.wamid,
                        "wa_id": msg.wa_id,
                        "body": msg.body,
                        "message_type": msg.message_type,
                        "phone_number_id": msg.phone_number_id,
                        "created_at": msg.created_at.isoformat(),
                    },
                    "candidate_reservations": row.candidate_reservations,
                    "resolved_reservation_id": row.resolved_reservation_id,
                    "resolved_tenant_id": row.resolved_tenant_id,
                    "notes": row.notes,
                }
            )
        return Response({"items": items, "count": len(items)})

    def post(self, request, routing_id: int):
        if not request.user.is_superuser:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        routing = (
            WhatsAppInboundRouting.objects.select_related("message")
            .filter(pk=routing_id)
            .first()
        )
        if routing is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        action = (request.data.get("action") or "").strip().lower()
        if action == "link":
            serializer = PlatformUnroutedLinkSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            reservation = Reservation.objects.filter(
                pk=serializer.validated_data["reservation_id"],
            ).first()
            if reservation is None:
                return Response(
                    {"detail": "reservation_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            manual_link_routing(
                routing=routing,
                reservation=reservation,
                user=request.user,
                notes=serializer.validated_data.get("notes") or "",
            )
            from apps.integrations.whatsapp.tasks import process_inbound_message

            process_inbound_message.delay(
                routing.message_id,
                profile_name="",
            )
            return Response({"status": "linked", "routing_id": routing.pk})

        if action == "dismiss":
            serializer = PlatformUnroutedDismissSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            dismiss_routing(
                routing=routing,
                user=request.user,
                notes=serializer.validated_data.get("notes") or "",
            )
            return Response({"status": "dismissed", "routing_id": routing.pk})

        return Response({"detail": "invalid_action"}, status=status.HTTP_400_BAD_REQUEST)
