import Link from "next/link";
import type { ReactNode } from "react";
import { UiIcon } from "./ui-icons";

/** A shared visual label; the existing link or button owns the interaction. */
export function CardEntryLabel({ children = "查看详情" }: { children?: ReactNode }) {
  return <span className="card-entry-label">{children}<UiIcon name="send" size={14} /></span>;
}

export function CardEntry({ href, children, className = "" }: { href: string; children?: ReactNode; className?: string }) {
  return <Link href={href} className={`card-entry-link ${className}`.trim()}><CardEntryLabel>{children}</CardEntryLabel></Link>;
}
