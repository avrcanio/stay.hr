"""Helpers for tenant-scoped Django admin access."""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser

from apps.tenants.models import Tenant, TenantMembership


def is_platform_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.is_superuser)


def get_allowed_tenant_ids(request) -> list[int] | None:
    """
    Return None for superuser (no filter), or a list of tenant PKs for staff.
    Staff without memberships get an empty list.
    """
    user = request.user
    if not user.is_authenticated or user.is_superuser:
        return None
    if not user.is_staff:
        return []
    return list(
        TenantMembership.objects.filter(user=user).values_list("tenant_id", flat=True),
    )


def get_allowed_tenants(request):
    ids = get_allowed_tenant_ids(request)
    if ids is None:
        return Tenant.objects.all()
    if not ids:
        return Tenant.objects.none()
    return Tenant.objects.filter(pk__in=ids)


def user_has_tenant_access(request, tenant_id: int | None) -> bool:
    if tenant_id is None:
        return False
    allowed = get_allowed_tenant_ids(request)
    if allowed is None:
        return True
    return tenant_id in allowed


def staff_has_tenant_membership(request) -> bool:
    user = request.user
    if not user.is_authenticated or isinstance(user, AnonymousUser):
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    return TenantMembership.objects.filter(user=user).exists()


def get_object_tenant_id(obj, tenant_field: str = "tenant") -> int | None:
    if obj is None:
        return None
    if tenant_field == "tenant":
        return getattr(obj, "tenant_id", None)
    parts = tenant_field.split("__")
    value = obj
    for part in parts:
        if value is None:
            return None
        value = getattr(value, part, None)
    return value if isinstance(value, int) else getattr(value, "pk", value)
