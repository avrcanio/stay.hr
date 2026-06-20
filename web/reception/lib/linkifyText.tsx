import type { ReactNode } from "react";

const URL_REGEX = /https?:\/\/[^\s]+/g;

function splitUrlAndTrailingPunct(url: string): { href: string; trailing: string } {
  const match = url.match(/^(https?:\/\/[^\s]*?)([.,]+)$/);
  if (match) {
    return { href: match[1], trailing: match[2] };
  }
  return { href: url, trailing: "" };
}

type LinkifiedTextProps = {
  children: string;
  className?: string;
};

export function LinkifiedText({ children, className }: LinkifiedTextProps) {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;

  for (const match of children.matchAll(URL_REGEX)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      nodes.push(children.slice(lastIndex, index));
    }
    const raw = match[0];
    const { href, trailing } = splitUrlAndTrailingPunct(raw);
    nodes.push(
      <a
        key={key++}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-stay-blue underline"
      >
        {href}
      </a>,
    );
    if (trailing) {
      nodes.push(trailing);
    }
    lastIndex = index + raw.length;
  }

  if (lastIndex < children.length) {
    nodes.push(children.slice(lastIndex));
  }

  return <p className={className}>{nodes.length ? nodes : children}</p>;
}
