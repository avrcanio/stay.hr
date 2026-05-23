from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.tenants.models import Tenant, TenantMembership


class StaffSessionAuthentication(SessionAuthentication):
    """Authenticate reception web staff via Django session (BFF forwards sessionid)."""

    def enforce_csrf(self, request):
        return

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, _auth = result
        if not user.is_active:
            raise AuthenticationFailed("User inactive or deleted.")
        if not user.is_staff:
            raise AuthenticationFailed("Staff access required.")

        tenant_id = request.session.get("active_tenant_id")
        if not tenant_id:
            raise AuthenticationFailed("No active tenant in session.")

        try:
            tenant = Tenant.objects.get(pk=tenant_id, status=Tenant.Status.ACTIVE)
        except Tenant.DoesNotExist as exc:
            raise AuthenticationFailed("Invalid tenant.") from exc

        if not user.is_superuser and not TenantMembership.objects.filter(
            user=user,
            tenant=tenant,
        ).exists():
            raise AuthenticationFailed("No tenant access.")

        request.tenant = tenant
        return (user, None)
