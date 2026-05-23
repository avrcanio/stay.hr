import { defineRouting } from "next-intl/routing";
import { defaultLocale, locales } from "./locale";

export const routing = defineRouting({
  locales: [...locales],
  defaultLocale,
  localePrefix: "never",
  localeCookie: {
    name: "stay_locale",
    maxAge: 60 * 60 * 24 * 365,
  },
});
