"use client";

import { useState } from "react";
import type { ChannexChannel } from "@/lib/channex-channels";

type Props = {
  channels: ChannexChannel[];
  allTitle: string;
  allCountLabel: string;
  expandLabel: string;
  collapseLabel: string;
};

export function ProductChannelList({
  channels,
  allTitle,
  allCountLabel,
  expandLabel,
  collapseLabel,
}: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="space-y-3">
      <button
        type="button"
        className="btn-ghost w-full justify-center sm:w-auto"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? collapseLabel : expandLabel}
      </button>

      {open ? (
        <div className="rounded-xl border border-stay-border bg-slate-50 p-4">
          <h4 className="mb-3 text-sm font-semibold text-stay-navy">
            {allTitle}{" "}
            <span className="font-normal text-stay-muted">({allCountLabel})</span>
          </h4>
          <ul className="max-h-96 columns-1 gap-x-6 overflow-y-auto text-sm sm:columns-2 md:columns-3">
            {channels.map((channel) => (
              <li key={channel.code} className="mb-1 break-inside-avoid text-stay-navy/90">
                {channel.name}{" "}
                <span className="text-stay-muted">({channel.code})</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
