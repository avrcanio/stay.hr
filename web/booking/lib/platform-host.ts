export function isPlatformApexHost(host: string): boolean {
  const normalized = host.toLowerCase();
  return normalized === "stay.hr" || normalized === "www.stay.hr";
}
