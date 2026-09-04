import type { ReactNode } from "react";

export type IconName =
  | "add"
  | "apps"
  | "archive"
  | "chart"
  | "clock"
  | "file"
  | "filter"
  | "grid"
  | "home"
  | "logout"
  | "refresh"
  | "search"
  | "send"
  | "settings"
  | "spark"
  | "tag"
  | "user"
  | "users";

function iconContent(name: IconName): ReactNode {
  switch (name) {
    case "add": return <><path d="M12 5v14M5 12h14" /></>;
    case "apps": return <><rect x="4" y="4" width="6" height="6" rx="1.4" /><rect x="14" y="4" width="6" height="6" rx="1.4" /><rect x="4" y="14" width="6" height="6" rx="1.4" /><rect x="14" y="14" width="6" height="6" rx="1.4" /></>;
    case "archive": return <><path d="M4 8h16M5 8v11h14V8M3 4h18v4H3zM9 12h6" /></>;
    case "chart": return <><path d="M5 19V9M12 19V5M19 19v-7M3 19h18" /></>;
    case "clock": return <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3.2 2" /></>;
    case "file": return <><path d="M7 3.5h7l4 4V20H7z" /><path d="M14 3.5V8h4M10 12h5M10 15.5h5" /></>;
    case "filter": return <><path d="M4 6h16M7 12h10M10 18h4" /></>;
    case "grid": return <><path d="M4 5.5h16M4 12h16M4 18.5h16" /><circle cx="7" cy="5.5" r="1" fill="currentColor" stroke="none" /><circle cx="17" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="10" cy="18.5" r="1" fill="currentColor" stroke="none" /></>;
    case "home": return <><path d="m4 11 8-7 8 7v9h-6v-6h-4v6H4z" /></>;
    case "logout": return <><path d="M10 5H5v14h5M14 8l4 4-4 4M9 12h9" /></>;
    case "refresh": return <><path d="M19 8a7.5 7.5 0 0 0-12.5-2L4 8.5" /><path d="M4 4v4.5h4.5M5 16a7.5 7.5 0 0 0 12.5 2l2.5-2.5" /><path d="M20 20v-4.5h-4.5" /></>;
    case "search": return <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4 4" /></>;
    case "send": return <><path d="M5 12h14M13 6l6 6-6 6" /></>;
    case "settings": return <><circle cx="12" cy="12" r="3" /><path d="M19 13.5v-3l-2-.7-.6-1.4.9-1.9-2.1-2.1-1.9.9-1.4-.6-.7-2h-3l-.7 2-1.4.6-1.9-.9-2.1 2.1.9 1.9-.6 1.4-2 .7v3l2 .7.6 1.4-.9 1.9 2.1 2.1 1.9-.9 1.4.6.7 2h3l.7-2 1.4-.6 1.9.9 2.1-2.1-.9-1.9.6-1.4z" /></>;
    case "spark": return <><path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z" /><path d="m18.5 16 .6 2.1 2.1.6-2.1.6-.6 2.1-.6-2.1-2.1-.6 2.1-.6z" /></>;
    case "tag": return <><path d="M4 5v6l8.5 8.5 7-7L11 4H5a1 1 0 0 0-1 1Z" /><circle cx="8" cy="8" r="1.2" /></>;
    case "user": return <><circle cx="12" cy="8" r="3.5" /><path d="M5.5 20a6.5 6.5 0 0 1 13 0" /></>;
    case "users": return <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0M15 5.5a3 3 0 0 1 0 5.5M16 14a5 5 0 0 1 4.5 5" /></>;
  }
}

export function UiIcon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {iconContent(name)}
    </svg>
  );
}

export function LingjianMark({ size = 34 }: { size?: number }) {
  return (
    <svg className="lingjian-mark" width={size} height={size} viewBox="0 0 36 36" aria-hidden="true">
      <rect width="36" height="36" rx="10" fill="currentColor" />
      <path d="M10 12.5h7.2L14.4 18H8.8L10 12.5Zm9.7 0H26l1.2 5.5h-4.7l-2.8-5.5ZM8.8 20h5.6l2.8 5.5H10L8.8 20Zm13.7 0h4.7L26 25.5h-6.3l2.8-5.5Z" fill="white" />
    </svg>
  );
}
