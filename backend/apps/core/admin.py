"""Shared Django admin mixins."""

from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation
from apps.tenants.admin_scope import (
    get_allowed_tenant_ids,
    get_allowed_tenants,
    get_object_tenant_id,
    is_platform_admin,
    staff_has_tenant_membership,
    user_has_tenant_access,
)


class SuperuserOnlyAdminMixin:
    """Restrict admin module to platform superusers."""

    def has_module_permission(self, request):
        return is_platform_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_platform_admin(request.user)

    def has_add_permission(self, request):
        return is_platform_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_platform_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_platform_admin(request.user)


class TenantScopedAdminMixin:
    """
    Filter changelists and FK choices to the request user's tenant memberships.
    Superusers see everything. Staff without memberships see nothing.
    """

    tenant_field = "tenant"

    def _allowed_tenant_ids(self, request) -> list[int] | None:
        return get_allowed_tenant_ids(request)

    def _tenant_filter_kwargs(self, request) -> dict:
        allowed = self._allowed_tenant_ids(request)
        if allowed is None:
            return {}
        if not allowed:
            return {f"{self.tenant_field}__in": []}
        return {f"{self.tenant_field}__in": allowed}

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        filt = self._tenant_filter_kwargs(request)
        if filt:
            qs = qs.filter(**filt)
        return qs

    def _staff_with_membership(self, request) -> bool:
        user = request.user
        return (
            user.is_authenticated
            and user.is_staff
            and not user.is_superuser
            and staff_has_tenant_membership(request)
        )

    def has_module_permission(self, request):
        if is_platform_admin(request.user):
            return super().has_module_permission(request)
        return self._staff_with_membership(request)

    def _object_tenant_allowed(self, request, obj) -> bool:
        if obj is None:
            return True
        tenant_id = get_object_tenant_id(obj, self.tenant_field)
        return user_has_tenant_access(request, tenant_id)

    def has_view_permission(self, request, obj=None):
        if is_platform_admin(request.user):
            return super().has_view_permission(request, obj)
        if not self._staff_with_membership(request):
            return False
        if obj is None:
            return True
        return self._object_tenant_allowed(request, obj)

    def has_add_permission(self, request):
        if is_platform_admin(request.user):
            return super().has_add_permission(request)
        return self._staff_with_membership(request)

    def has_change_permission(self, request, obj=None):
        if is_platform_admin(request.user):
            return super().has_change_permission(request, obj)
        if not self._staff_with_membership(request):
            return False
        if obj is None:
            return True
        return self._object_tenant_allowed(request, obj)

    def has_delete_permission(self, request, obj=None):
        if is_platform_admin(request.user):
            return super().has_delete_permission(request, obj)
        if not self._staff_with_membership(request):
            return False
        if obj is None:
            return True
        return self._object_tenant_allowed(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        allowed = self._allowed_tenant_ids(request)
        if allowed is not None:
            if db_field.name == "tenant":
                kwargs["queryset"] = get_allowed_tenants(request)
            elif db_field.name == "property":
                kwargs["queryset"] = Property.objects.filter(tenant_id__in=allowed)
            elif db_field.name == "unit":
                kwargs["queryset"] = Unit.objects.filter(tenant_id__in=allowed)
            elif db_field.name == "reservation":
                kwargs["queryset"] = Reservation.objects.filter(tenant_id__in=allowed)
            elif db_field.name == "guest":
                kwargs["queryset"] = Guest.objects.filter(tenant_id__in=allowed)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _resolve_tenant_id_for_save(self, request, obj) -> int | None:
        tenant_id = get_object_tenant_id(obj, self.tenant_field)
        if tenant_id is not None:
            return tenant_id
        if self.tenant_field == "tenant" and hasattr(obj, "tenant_id"):
            return obj.tenant_id
        allowed = self._allowed_tenant_ids(request)
        if allowed and len(allowed) == 1 and self.tenant_field == "tenant":
            return allowed[0]
        return tenant_id

    def _enforce_tenant_on_save(self, request, obj) -> None:
        if is_platform_admin(request.user):
            return
        if self.tenant_field == "tenant" and not getattr(obj, "tenant_id", None):
            allowed = self._allowed_tenant_ids(request) or []
            if len(allowed) == 1:
                obj.tenant_id = allowed[0]
        tenant_id = self._resolve_tenant_id_for_save(request, obj)
        if not user_has_tenant_access(request, tenant_id):
            raise PermissionDenied("Nemate pristup ovom tenantu.")

    def save_model(self, request, obj, form, change):
        self._enforce_tenant_on_save(request, obj)
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        allowed = self._allowed_tenant_ids(request)
        parent = form.instance
        parent_tenant_id = getattr(parent, "tenant_id", None)
        if allowed is not None:
            for inline_form in formset.forms:
                if inline_form.cleaned_data.get("DELETE"):
                    continue
                instance = inline_form.instance
                if not inline_form.has_changed() and not instance.pk:
                    continue
                if hasattr(instance, "tenant_id"):
                    if not instance.tenant_id and parent_tenant_id:
                        instance.tenant_id = parent_tenant_id
                    tid = instance.tenant_id
                    if tid and tid not in allowed:
                        raise PermissionDenied("Nemate pristup ovom tenantu.")
        super().save_formset(request, form, formset, change)
