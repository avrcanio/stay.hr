import fs from "fs";
import https from "https";

const url = "https://docs.channex.io/api-v.1-documentation/channel-codes";

https
  .get(url, (res) => {
    let data = "";
    res.on("data", (c) => {
      data += c;
    });
    res.on("end", () => {
      const seen = new Map();
      const re = /([A-Z0-9]{2,4}) - ([A-Za-z0-9][^<\n]{1,120}?)(?=<|$|\n)/g;
      let match;
      while ((match = re.exec(data)) !== null) {
        const code = match[1];
        const name = match[2].trim();
        if (!seen.has(code)) seen.set(code, name);
      }
      const channels = [...seen.entries()]
        .map(([code, name]) => ({ code, name }))
        .sort((a, b) => a.name.localeCompare(b.name, "en"));

      const featured = [
        "BDC",
        "ABB",
        "EXP",
        "VRB",
        "AGO",
        "CTP",
        "HWL",
        "HTL",
        "GHA",
        "HBD",
        "PCL",
        "TRV",
        "LRW",
        "CCK",
        "HRS",
      ];

      const out = `export type ChannexChannel = { code: string; name: string };

export const CHANNEX_FEATURED_CODES = ${JSON.stringify(featured)} as const;

export const CHANNEX_CHANNELS: ChannexChannel[] = ${JSON.stringify(channels, null, 2)};

export function allChannels(): ChannexChannel[] {
  return CHANNEX_CHANNELS;
}

export function featuredChannels(): ChannexChannel[] {
  const byCode = new Map(CHANNEX_CHANNELS.map((c) => [c.code, c]));
  return CHANNEX_FEATURED_CODES.map((code) => byCode.get(code)).filter(
    (c): c is ChannexChannel => Boolean(c),
  );
}
`;

      fs.writeFileSync(new URL("../lib/channex-channels.ts", import.meta.url), out);
      console.log(`Wrote ${channels.length} channels`);
    });
  })
  .on("error", (e) => {
    console.error(e);
    process.exit(1);
  });
