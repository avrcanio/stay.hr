from __future__ import annotations

from apps.integrations.whatsapp.phone import normalize_phone, phones_match
from apps.tenants.models import TenantReceptionSettings


def normalize_operator_phones(settings: TenantReceptionSettings | None) -> list[dict[str, str]]:
    if settings is None:
        return []
    raw = settings.whatsapp_operator_phones or []
    if not isinstance(raw, list):
        return []

    operators: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        phone = str(item.get("phone") or "").strip()
        if not phone:
            continue
        name = str(item.get("name") or "").strip()
        operators.append({"name": name, "phone": phone})
    return operators


def operator_phones_for_tenant(tenant_id: int) -> list[dict[str, str]]:
    settings = TenantReceptionSettings.objects.filter(tenant_id=tenant_id).first()
    return normalize_operator_phones(settings)


def is_operator_wa_id(*, tenant_id: int, wa_id: str) -> bool:
    wa_id = (wa_id or "").strip()
    if not wa_id:
        return False
    for operator in operator_phones_for_tenant(tenant_id):
        if phones_match(operator["phone"], wa_id):
            return True
    return False


def operator_name_for_wa_id(*, tenant_id: int, wa_id: str) -> str:
    wa_id = (wa_id or "").strip()
    for operator in operator_phones_for_tenant(tenant_id):
        if phones_match(operator["phone"], wa_id):
            return operator.get("name") or normalize_phone(operator["phone"])
    return normalize_phone(wa_id)
