from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.api.fcm_serializers import FcmTokenRegisterSerializer
from apps.api.permissions import DenyAdminScopes, HasApiApplication, HasScope
from apps.api.views import TenantAPIView


class FcmTokenRegisterView(TenantAPIView):
    """
    Register or refresh the FCM device token for the authenticated API application
    (Hospira tablet). Token is stored on ApiApplication and used for push delivery.
    """

    required_scopes = ["reception:read"]
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]

    def put(self, request):
        serializer = FcmTokenRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["token"]
        application = request.api_application
        now = timezone.now()

        application.fcm_token = token
        application.fcm_token_updated_at = now
        application.save(update_fields=["fcm_token", "fcm_token_updated_at", "updated_at"])

        return Response(
            {
                "registered": True,
                "application_id": application.pk,
                "fcm_token_updated_at": now.isoformat(),
            }
        )

    def delete(self, request):
        application = request.api_application
        application.fcm_token = ""
        application.fcm_token_updated_at = None
        application.save(update_fields=["fcm_token", "fcm_token_updated_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
