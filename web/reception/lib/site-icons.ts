import type { Metadata } from "next";

/** Stay.hr favicon set (public/icons + public/favicon.ico). */
export const siteIcons: NonNullable<Metadata["icons"]> = {
  icon: [
    { url: "/icons/icon-16.ico", sizes: "16x16", type: "image/x-icon" },
    { url: "/icons/icon-24.ico", sizes: "24x24", type: "image/x-icon" },
    { url: "/icons/icon-32.ico", sizes: "32x32", type: "image/x-icon" },
    { url: "/icons/icon-48.ico", sizes: "48x48", type: "image/x-icon" },
    { url: "/icons/icon-64.ico", sizes: "64x64", type: "image/x-icon" },
    { url: "/icons/icon-96.ico", sizes: "96x96", type: "image/x-icon" },
    { url: "/icons/icon-128.ico", sizes: "128x128", type: "image/x-icon" },
  ],
  shortcut: "/favicon.ico",
  apple: "/icons/icon-128.ico",
};
