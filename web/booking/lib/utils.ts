import { headers } from "next/headers";

export { addDaysIso, nightsBetween, todayIso } from "@/lib/dates";

export async function requestHost(): Promise<string> {
  const h = await headers();
  return (h.get("x-forwarded-host") || h.get("host") || "localhost").split(":")[0];
}
