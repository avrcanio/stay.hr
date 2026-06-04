"""Reception guest messaging API (compose, send, timeline)."""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_views import ReceptionReadView, ReceptionWriteView
from apps.communications.guest_compose import compose_guest_message
from apps.communications.guest_message_send import (
    build_message_channels,
    default_email_subject,
    send_guest_message,
)
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
    GuestOutboundMessage,
)
from apps.integrations.models import ChannexMessage, WhatsAppMessage
from apps.reservations.models import Reservation

WA_ID_OFFSET = 2_000_000_000
CHANNEX_ID_OFFSET = 3_000_000_000


class GuestMessageComposeSerializer(serializers.Serializer):
    intent = serializers.ChoiceField(choices=GuestMessageIntent.choices)
    hint = serializers.CharField(required=False, allow_blank=True, default="")
    language = serializers.CharField(required=False, allow_blank=True, default="")


class GuestMessageSendSerializer(serializers.Serializer):
    draft_id = serializers.IntegerField()
    channel = serializers.ChoiceField(choices=GuestMessageChannel.choices)
    body_text = serializers.CharField(max_length=8000, trim_whitespace=True)
    subject = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)


def _reservation_or_404(tenant, reservation_id: int) -> Reservation:
    reservation = (
        Reservation.objects.filter(tenant=tenant, pk=reservation_id)
        .select_related("property", "tenant")
        .prefetch_related("guests")
        .first()
    )
    if reservation is None:
        raise NotFound("Reservation not found.")
    return reservation


def _serialize_outbound(outbound: GuestOutboundMessage) -> dict:
    app = outbound.api_application
    return {
        "id": outbound.pk,
        "source": "outbound",
        "direction": "outbound",
        "channel": outbound.channel,
        "body_text": outbound.body_text,
        "created_at": outbound.created_at.isoformat(),
        "status": outbound.status,
        "sent_by_name": app.name if app else None,
        "from_email": None,
        "wa_me_url": outbound.wa_me_url or None,
    }


def _serialize_whatsapp(msg: WhatsAppMessage) -> dict:
    return {
        "id": WA_ID_OFFSET + msg.pk,
        "source": "whatsapp",
        "direction": msg.direction,
        "channel": "whatsapp",
        "body_text": msg.body or "",
        "created_at": msg.created_at.isoformat(),
        "status": None,
        "sent_by_name": None,
        "from_email": None,
        "wa_me_url": None,
    }


def _serialize_channex(msg: ChannexMessage) -> dict:
    direction = "inbound" if msg.sender == ChannexMessage.Sender.GUEST else "outbound"
    return {
        "id": CHANNEX_ID_OFFSET + msg.pk,
        "source": "booking",
        "direction": direction,
        "channel": "booking",
        "body_text": msg.body or "",
        "created_at": msg.created_at.isoformat(),
        "status": None,
        "sent_by_name": None,
        "from_email": None,
        "wa_me_url": None,
    }


def _timeline_for_reservation(reservation: Reservation) -> list[dict]:
    rows: list[tuple[str, dict]] = []

    for outbound in GuestOutboundMessage.objects.filter(reservation=reservation).select_related(
        "api_application"
    ):
        rows.append((outbound.created_at.isoformat(), _serialize_outbound(outbound)))

    for msg in WhatsAppMessage.objects.filter(reservation=reservation):
        if (msg.body or "").strip():
            rows.append((msg.created_at.isoformat(), _serialize_whatsapp(msg)))

    for msg in ChannexMessage.objects.filter(reservation=reservation):
        if (msg.body or "").strip():
            rows.append((msg.created_at.isoformat(), _serialize_channex(msg)))

    rows.sort(key=lambda r: r[0])
    return [item for _, item in rows]


class ReceptionGuestMessagesView(ReceptionReadView, APIView):
    def get(self, request, reservation_id: int):
        reservation = _reservation_or_404(request.tenant, reservation_id)
        return Response(_timeline_for_reservation(reservation))


class ReceptionGuestMessageComposeView(ReceptionWriteView, APIView):
    def post(self, request, reservation_id: int):
        reservation = _reservation_or_404(request.tenant, reservation_id)
        serializer = GuestMessageComposeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        language = (data.get("language") or "").strip() or None
        api_application = getattr(request, "api_application", None)

        draft, channels, llm_used = compose_guest_message(
            reservation,
            intent=data["intent"],
            hint=data.get("hint") or "",
            api_application=api_application,
            language=language,
        )

        return Response(
            {
                "draft_id": draft.pk,
                "body_text": draft.llm_body_text,
                "language": draft.language,
                "llm_used": llm_used,
                "channels": channels,
            },
            status=status.HTTP_201_CREATED,
        )


class ReceptionGuestMessageSendView(ReceptionWriteView, APIView):
    def post(self, request, reservation_id: int):
        reservation = _reservation_or_404(request.tenant, reservation_id)
        serializer = GuestMessageSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        draft = GuestMessageDraft.objects.filter(
            tenant=request.tenant,
            reservation=reservation,
            pk=data["draft_id"],
        ).first()
        if draft is None:
            raise ValidationError({"draft_id": "Draft not found for this reservation."})

        channel = data["channel"]
        body_text = data["body_text"]
        channels = build_message_channels(reservation)

        if channel == GuestMessageChannel.EMAIL and not channels["email"]["available"]:
            raise ValidationError({"channel": "No guest email on this reservation."})
        if channel == GuestMessageChannel.WHATSAPP and not channels["whatsapp"]["available"]:
            raise ValidationError({"channel": "No guest phone on this reservation."})

        api_application = getattr(request, "api_application", None)
        subject = (data.get("subject") or "").strip() or None

        try:
            outbound = send_guest_message(
                reservation=reservation,
                draft=draft,
                channel=channel,
                body_text=body_text,
                api_application=api_application,
                subject=subject or default_email_subject(reservation),
            )
        except ValueError as exc:
            raise ValidationError({"channel": str(exc)}) from exc

        payload = _serialize_outbound(outbound)
        if channel == GuestMessageChannel.WHATSAPP:
            payload["wa_me_url"] = outbound.wa_me_url
        payload["edited"] = draft.edited
        return Response(payload, status=status.HTTP_201_CREATED)
