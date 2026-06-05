"""Reception guest messaging API (compose, send, timeline)."""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_views import ReceptionReadView, ReceptionWriteView
from apps.communications.guest_compose import compose_guest_message, create_draft_from_body_text
from apps.communications.guest_message_send import (
    build_message_channels,
    default_email_subject,
    send_guest_message,
    _booking_channel_available,
)
from apps.communications.guest_message_timeline import (
    serialize_channex,
    serialize_outbound,
    timeline_for_reservation,
)
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
)
from apps.integrations.models import ChannexMessage
from apps.reservations.models import Reservation


class GuestMessageComposeSerializer(serializers.Serializer):
    intent = serializers.ChoiceField(choices=GuestMessageIntent.choices, required=False)
    hint = serializers.CharField(required=False, allow_blank=True, default="")
    language = serializers.CharField(required=False, allow_blank=True, default="")
    body_text = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=8000,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        body_text = (attrs.get("body_text") or "").strip()
        intent = attrs.get("intent")
        if body_text:
            attrs["body_text"] = body_text
            return attrs
        if intent is None:
            raise serializers.ValidationError(
                {"intent": "Required unless body_text is provided."}
            )
        return attrs


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


def _sync_channex_messages_for_timeline(reservation: Reservation, *, sync_param: str) -> None:
    if sync_param == "0" or not _booking_channel_available(reservation):
        return
    from apps.integrations.channex.ari_service import get_active_channex_integration
    from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
    from apps.integrations.channex.message_service import list_messages_for_reservation

    try:
        integration = get_active_channex_integration(reservation.tenant.slug)
    except ChannexBookingIngestError:
        return

    try:
        list_messages_for_reservation(
            integration,
            reservation,
            sync_if_empty=sync_param == "auto",
            force_sync=sync_param == "1",
        )
    except (ChannexBookingIngestError, ChannexApiError):
        return


class ReceptionGuestMessagesView(ReceptionReadView, APIView):
    def get(self, request, reservation_id: int):
        reservation = _reservation_or_404(request.tenant, reservation_id)
        sync_param = request.query_params.get("sync", "auto")
        _sync_channex_messages_for_timeline(reservation, sync_param=sync_param)
        return Response(timeline_for_reservation(reservation))


class ReceptionGuestMessageComposeView(ReceptionWriteView, APIView):
    def post(self, request, reservation_id: int):
        reservation = _reservation_or_404(request.tenant, reservation_id)
        serializer = GuestMessageComposeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        language = (data.get("language") or "").strip() or None
        api_application = getattr(request, "api_application", None)

        body_text = (data.get("body_text") or "").strip()
        if body_text:
            draft, channels = create_draft_from_body_text(
                reservation,
                body_text,
                api_application=api_application,
            )
            llm_used = False
        else:
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
        if channel == GuestMessageChannel.BOOKING and not channels["booking"]["available"]:
            raise ValidationError({"channel": "Booking.com messaging is not available for this reservation."})

        api_application = getattr(request, "api_application", None)
        subject = (data.get("subject") or "").strip() or None

        try:
            result = send_guest_message(
                reservation=reservation,
                draft=draft,
                channel=channel,
                body_text=body_text,
                api_application=api_application,
                subject=subject or default_email_subject(reservation),
            )
        except ValueError as exc:
            raise ValidationError({"channel": str(exc)}) from exc

        if isinstance(result, ChannexMessage):
            app = getattr(request, "api_application", None)
            payload = serialize_channex(result)
            payload["status"] = "sent"
            payload["sent_by_name"] = app.name if app else None
            payload["edited"] = draft.edited
            return Response(payload, status=status.HTTP_201_CREATED)

        outbound = result
        payload = serialize_outbound(outbound)
        if channel == GuestMessageChannel.WHATSAPP:
            payload["wa_me_url"] = outbound.wa_me_url
        payload["edited"] = draft.edited
        return Response(payload, status=status.HTTP_201_CREATED)
