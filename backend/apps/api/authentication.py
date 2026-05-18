from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.tenants.models import ApiApplication, Tenant
from apps.tenants.tokens import extract_token_from_request, hash_token, verify_token

LAST_USED_THROTTLE = timedelta(minutes=5)


class AppKeyAuthentication(BaseAuthentication):
    """
  Authenticate Flutter/API clients via Bearer or X-Stay-App-Key.
  Sets request.tenant and request.api_application.
    """

    www_authenticate_header = "Bearer"

    def authenticate(self, request):
        raw_token = extract_token_from_request(request)
        if not raw_token:
            return None

        token_hash = hash_token(raw_token)
        try:
            application = (
                ApiApplication.objects.select_related("tenant")
                .filter(
                    public_key_hash=token_hash,
                    is_active=True,
                    tenant__status=Tenant.Status.ACTIVE,
                )
                .get()
            )
        except ApiApplication.DoesNotExist as exc:
            raise AuthenticationFailed("Invalid API key.") from exc

        if not verify_token(raw_token, application.public_key_hash):
            raise AuthenticationFailed("Invalid API key.")

        request.tenant = application.tenant
        request.api_application = application
        self._touch_last_used(application)
        return (AnonymousUser(), application)

    def _touch_last_used(self, application: ApiApplication) -> None:
        now = timezone.now()
        if (
            application.last_used_at is not None
            and now - application.last_used_at < LAST_USED_THROTTLE
        ):
            return
        ApiApplication.objects.filter(pk=application.pk).update(last_used_at=now)
        application.last_used_at = now
