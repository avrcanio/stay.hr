from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.serializers import PropertySummarySerializer, TenantSummarySerializer
from apps.properties.models import Property
from apps.tenants.models import TenantDomain


class SiteContextView(APIView):
    """Public bootstrap payload for web booking/reception frontends."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        tenant_domain = getattr(request, "tenant_domain", None)
        if tenant_domain is None:
            return Response(
                {"detail": "Unknown or unverified host."},
                status=status.HTTP_404_NOT_FOUND,
            )

        tenant = tenant_domain.tenant
        property_obj = tenant_domain.property
        branding: dict = {}

        if property_obj is not None:
            branding = property_obj.branding or {}
        else:
            properties = Property.objects.for_tenant(tenant).order_by("name")
            primary = properties.filter(slug=tenant.slug).first() or properties.first()
            if primary is not None:
                branding = primary.branding or {}

        return Response(
            {
                "tenant": TenantSummarySerializer(tenant).data,
                "property": (
                    PropertySummarySerializer(property_obj).data
                    if property_obj is not None
                    else None
                ),
                "domain_type": tenant_domain.domain_type,
                "branding": branding,
                "languages": [tenant.default_language],
            }
        )
