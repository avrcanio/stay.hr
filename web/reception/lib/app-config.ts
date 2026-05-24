type AppConfigProperty = {
  slug: string;
};

type AppConfigTenant = {
  slug?: string;
};

export type AppConfigLike = {
  tenant?: AppConfigTenant;
  properties?: AppConfigProperty[];
};

/** Match backend AppConfigView primary property (tenant slug, else first by name). */
export function primaryPropertySlug(config: AppConfigLike): string {
  const tenantSlug = config.tenant?.slug?.trim();
  const properties = config.properties ?? [];
  if (tenantSlug) {
    const match = properties.find((property) => property.slug === tenantSlug);
    if (match) {
      return match.slug;
    }
  }
  return properties[0]?.slug ?? "";
}
