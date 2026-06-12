import Image from "next/image";

type Aspect = "browser" | "phone";

type Props = {
  label: string;
  hint?: string;
  aspect?: Aspect;
  src?: string;
};

const aspectClass: Record<Aspect, string> = {
  browser: "aspect-[16/10]",
  phone: "aspect-[9/19] max-w-[220px] mx-auto",
};

export function ProductScreenshotPlaceholder({
  label,
  hint,
  aspect = "browser",
  src,
}: Props) {
  if (src) {
    return (
      <figure className="space-y-2">
        <div
          className={`overflow-hidden rounded-xl border border-stay-border ${aspectClass[aspect]}`}
        >
          <Image
            src={src}
            alt={label}
            width={aspect === "phone" ? 440 : 1280}
            height={aspect === "phone" ? 930 : 800}
            className="h-full w-full object-cover object-top"
          />
        </div>
        <figcaption className="text-center text-xs text-stay-muted">{label}</figcaption>
      </figure>
    );
  }

  return (
    <figure
      className={`screenshot-placeholder flex flex-col items-center justify-center gap-2 rounded-xl px-4 py-6 text-center ${aspectClass[aspect]}`}
      aria-label={label}
    >
      <span className="text-xs font-semibold uppercase tracking-wide text-stay-muted">{label}</span>
      {hint ? <span className="max-w-xs text-xs text-stay-muted/80">{hint}</span> : null}
    </figure>
  );
}
