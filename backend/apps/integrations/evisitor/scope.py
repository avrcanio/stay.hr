from __future__ import annotations

from typing import Any

from apps.integrations.models import IntegrationConfig


def build_config_scope(row: IntegrationConfig) -> dict[str, Any]:
    if row.property_id is not None:
        return {
            "level": "property",
            "tenant_slug": row.tenant.slug,
            "property_slug": row.property.slug,
        }
    return {
        "level": "tenant",
        "tenant_slug": row.tenant.slug,
        "property_slug": None,
    }


def format_config_scope_label(scope: dict[str, Any]) -> str:
    if scope["level"] == "property":
        return f"property/{scope['tenant_slug']}/{scope['property_slug']}"
    return f"tenant/{scope['tenant_slug']}"
