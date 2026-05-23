from django.contrib.auth import authenticate, get_user_model, login, logout
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.staff_authentication import StaffSessionAuthentication
from apps.tenants.models import StaffProfile, Tenant, TenantMembership

User = get_user_model()
ACTIVE_TENANT_SESSION_KEY = "active_tenant_id"


def _authenticate_user(identifier: str, password: str):
    user = authenticate(username=identifier, password=password)
    if user is not None:
        return user

    email_user = User.objects.filter(email__iexact=identifier).first()
    if email_user is None:
        return None
    return authenticate(username=email_user.username, password=password)


def _tenant_payload(tenant: Tenant) -> dict:
    return {"id": tenant.pk, "name": tenant.name, "slug": tenant.slug}


def _user_payload(user) -> dict:
    return {
        "username": user.username,
        "preferred_language": StaffProfile.preferred_language_for(user),
    }


def _membership_tenants(user) -> list[Tenant]:
    if user.is_superuser:
        return list(Tenant.objects.filter(status=Tenant.Status.ACTIVE).order_by("name"))
    return list(
        Tenant.objects.filter(
            status=Tenant.Status.ACTIVE,
            memberships__user=user,
        )
        .distinct()
        .order_by("name"),
    )


class ReceptionLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        tenant_id = request.data.get("tenant_id")

        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = _authenticate_user(username, password)
        if user is None:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not user.is_staff:
            return Response(
                {"detail": "Staff access required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenants = _membership_tenants(user)
        if not tenants:
            return Response(
                {"detail": "No tenant access configured for this user."},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = None
        if tenant_id is not None:
            try:
                tenant_id = int(tenant_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "Invalid tenant_id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            tenant = next((item for item in tenants if item.pk == tenant_id), None)
            if tenant is None:
                return Response(
                    {"detail": "No access to the selected tenant."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif len(tenants) == 1:
            tenant = tenants[0]
        else:
            return Response(
                {
                    "requires_tenant": True,
                    "tenants": [_tenant_payload(item) for item in tenants],
                },
                status=status.HTTP_409_CONFLICT,
            )

        login(request, user)
        request.session[ACTIVE_TENANT_SESSION_KEY] = tenant.pk

        return Response(
            {
                "ok": True,
                "user": _user_payload(user),
                "tenant": _tenant_payload(tenant),
            },
        )


class ReceptionLogoutView(APIView):
    authentication_classes = [StaffSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReceptionSessionView(APIView):
    authentication_classes = [StaffSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = request.tenant
        return Response(
            {
                "ok": True,
                "user": _user_payload(request.user),
                "tenant": _tenant_payload(tenant),
            },
        )
