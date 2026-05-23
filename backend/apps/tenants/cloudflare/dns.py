from __future__ import annotations

from django.conf import settings

from apps.tenants.cloudflare.client import CloudflareAPIError, CloudflareClient
from apps.tenants.models import TenantDomain

RESERVED_STAY_SUBDOMAINS = frozenset({"api", "admin", "app"})

PLATFORM_DNS_HOSTS = (
    "app.stay.hr",
    "*.stay.hr",
)


def apex_zone_name(domain: str) -> str:
    parts = domain.lower().split(".")
    if len(parts) < 2:
        raise CloudflareAPIError(f"Invalid domain: {domain!r}")
    return ".".join(parts[-2:])


def resolve_target_ip(client: CloudflareClient, stay_zone: str) -> str:
    configured = settings.STAY_SERVER_IP.strip()
    if configured:
        return configured

    zone_id = client.get_zone_id(stay_zone)
    apex_ip = client.get_apex_a_record_ip(zone_id, stay_zone)
    if not apex_ip:
        raise CloudflareAPIError(
            "STAY_SERVER_IP is not set and no apex A record was found "
            f"for zone {stay_zone!r}",
        )
    return apex_ip


def provision_platform_dns(*, dry_run: bool = False) -> list[str]:
    client = CloudflareClient()
    client.verify_token()
    stay_zone = settings.CLOUDFLARE_ZONE_STAY
    zone_id = client.get_zone_id(stay_zone)
    target_ip = resolve_target_ip(client, stay_zone)

    provisioned: list[str] = []
    for fqdn in PLATFORM_DNS_HOSTS:
        if dry_run:
            provisioned.append(f"{fqdn} -> {target_ip} (dry-run)")
            continue
        client.upsert_a_record(zone_id, fqdn, target_ip, proxied=True)
        provisioned.append(f"{fqdn} -> {target_ip} (proxied)")
    return provisioned


def zone_name_for_tenant_domain(tenant_domain: TenantDomain) -> str:
    if tenant_domain.domain_type == TenantDomain.DomainType.STAY_SUBDOMAIN:
        return settings.CLOUDFLARE_ZONE_STAY

    if tenant_domain.domain_type == TenantDomain.DomainType.CUSTOM_DOMAIN:
        return apex_zone_name(tenant_domain.domain)

    raise CloudflareAPIError(
        f"Unsupported domain_type: {tenant_domain.domain_type!r}",
    )


def provision_tenant_domain_dns(
    tenant_domain: TenantDomain,
    *,
    dry_run: bool = False,
) -> str:
    subdomain = tenant_domain.domain.split(".")[0].lower()
    if (
        tenant_domain.domain_type == TenantDomain.DomainType.STAY_SUBDOMAIN
        and subdomain in RESERVED_STAY_SUBDOMAINS
    ):
        raise CloudflareAPIError(
            f"Refusing to provision reserved subdomain: {tenant_domain.domain}",
        )

    client = CloudflareClient()
    client.verify_token()
    zone_name = zone_name_for_tenant_domain(tenant_domain)
    zone_id = client.get_zone_id(zone_name)
    target_ip = resolve_target_ip(client, settings.CLOUDFLARE_ZONE_STAY)

    if dry_run:
        return f"{tenant_domain.domain} -> {target_ip} in {zone_name} (dry-run)"

    client.upsert_a_record(zone_id, tenant_domain.domain, target_ip, proxied=True)
    return f"{tenant_domain.domain} -> {target_ip} in {zone_name} (proxied)"
