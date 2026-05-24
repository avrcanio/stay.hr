type AppConfigProperty = {
  slug: string;
  name?: string;
};

export type AppConfigLike = {
  properties?: AppConfigProperty[];
};

/** Auto-select slug only when tenant has exactly one property. */
export function singlePropertySlug(config: AppConfigLike): string {
  const properties = config.properties ?? [];
  return properties.length === 1 ? properties[0].slug : "";
}
