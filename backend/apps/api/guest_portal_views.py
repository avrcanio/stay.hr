"""Public token-scoped guest portal API (AllowAny)."""

from __future__ import annotations

from django.http import FileResponse, Http404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reservations.guest_portal_access import (
    evaluate_portal_access,
    get_access_by_token,
)
from apps.reservations.guest_portal_context import (
    build_guest_portal_context,
    entrance_image_file_for_access,
    key_guide_step_file_for_access,
    serialize_guest_portal_context,
)


def _load_access_or_404(token):
    access = get_access_by_token(token)
    if access is None:
        raise Http404("Guest portal access not found.")
    return access


def _access_error_response(access_result) -> Response:
    payload: dict = {"status": access_result.gate_status}
    if access_result.opens_at is not None:
        payload["opens_at"] = access_result.opens_at.isoformat()
    return Response(payload, status=access_result.http_status)


class GuestPortalView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        access = _load_access_or_404(token)
        gate = evaluate_portal_access(access)
        if not gate.allowed:
            return _access_error_response(gate)

        lang = request.query_params.get("lang") or request.query_params.get("language")
        ctx = build_guest_portal_context(access, language=lang)
        return Response(serialize_guest_portal_context(ctx))


class GuestPortalEntranceImageView(APIView):
    """Serve property entrance image for an open portal token."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        access = _load_access_or_404(token)
        gate = evaluate_portal_access(access)
        if not gate.allowed:
            return _access_error_response(gate)

        path = entrance_image_file_for_access(access)
        if path is None:
            raise Http404("Entrance image not found.")
        response = FileResponse(path.open("rb"), content_type="image/jpeg")
        response["Cache-Control"] = "no-store, must-revalidate"
        return response


class GuestPortalKeyGuideStepImageView(APIView):
    """Serve a key-guide step image for an open portal token."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token, index: int):
        access = _load_access_or_404(token)
        gate = evaluate_portal_access(access)
        if not gate.allowed:
            return _access_error_response(gate)

        path = key_guide_step_file_for_access(access, index)
        if path is None:
            raise Http404("Key guide step image not found.")
        response = FileResponse(path.open("rb"), content_type="image/jpeg")
        response["Cache-Control"] = "no-store, must-revalidate"
        return response
