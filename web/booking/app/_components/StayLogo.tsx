import Image from "next/image";
import Link from "next/link";

type Props = {
  href?: string | null;
  subtitle?: string;
  className?: string;
};

export function StayLogo({ href = "/", subtitle, className = "" }: Props) {
  const content = (
    <div className={`flex items-center gap-3 ${className}`}>
      <Image
        src="/logo.png"
        alt="stay.hr"
        width={560}
        height={144}
        priority
        unoptimized
        className="h-9 w-auto"
      />
      {subtitle ? <span className="text-sm font-medium text-stay-muted">{subtitle}</span> : null}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="inline-flex shrink-0 items-center rounded-xl transition hover:opacity-90">
        {content}
      </Link>
    );
  }

  return <div className="inline-flex shrink-0 items-center">{content}</div>;
}
