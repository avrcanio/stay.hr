from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class PropertyResolutionError(ValidationError):
    """Raised when a property cannot be resolved for the given context."""


def resolve_property_for_tenant(
    tenant: Tenant,
    *,
    slug: str | None = None,
    reservation: Reservation | None = None,
) -> Property:
    """Resolve which Property to use for display/import operations.

    Priority:
    1. reservation.property when reservation is provided
    2. explicit slug lookup
    3. sole property when tenant has exactly one
    4. otherwise raise PropertyResolutionError
    """
    if reservation is not None:
        if reservation.tenant_id != tenant.pk:
            raise PropertyResolutionError("Reservation does not belong to this tenant.")
        return reservation.property

    slug = (slug or "").strip()
    if slug:
        prop = Property.objects.filter(tenant=tenant, slug=slug).first()
        if prop is None:
            raise PropertyResolutionError(
                {"property_slug": f"Property slug={slug!r} nije pronađen."}
            )
        return prop

    properties = list(Property.objects.filter(tenant=tenant).order_by("name")[:2])
    if len(properties) == 1:
        return properties[0]

    if not properties:
        raise PropertyResolutionError({"property_slug": "Tenant nema definiran property."})

    raise PropertyResolutionError(
        {"property_slug": "Odaberite property (property_slug je obavezan)."}
    )
