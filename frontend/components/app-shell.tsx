"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState, useEffect } from "react";

const NAV_STRUCTURE = [
  {
    group: "灵鉴 Agent",
    icon: "🎯",
    items: [
      { label: "智能匹配", href: "/" },
      { label: "伙伴画像", href: "/profiles" },
    ],
  },
  {
    group: "伙伴管理",
    icon: "📊",
    items: [
      { label: "伙伴资料", href: "/partners" },
      { label: "需求画像", href: "/demands" },
      { label: "项目机会库", href: "/demands?tab=opportunities" },
      { label: "运营报表", href: "/demands?tab=report" },
      { label: "能力标签", href: "/admin?tab=tags" },
    ],
  },
  {
    group: "系统管理",
    icon: "⚙️",
    items: [
      { label: "用户管理", href: "/admin" },
      { label: "模型配置", href: "/admin?tab=model" },
      { label: "系统状态", href: "/admin?tab=status" },
    ],
  },
];

function getPageTitle(pathname: string, searchParams: URLSearchParams): string {
  for (const group of NAV_STRUCTURE) {
    for (const item of group.items) {
      const itemPath = item.href.split("?")[0];
      const itemParams = new URLSearchParams(item.href.split("?")[1] || "");
      const itemTab = itemParams.get("tab");
      if (pathname === itemPath || pathname.startsWith(itemPath + "/")) {
        // For /demands and /admin, also match tab param
        if ((itemPath === "/demands" || itemPath === "/admin") && itemTab) {
          if (searchParams.get("tab") === itemTab) {
            return `${group.group} / ${item.label}`;
          }
        } else if (!itemTab) {
          // No tab in href = default item, match when no tab in URL
          if (!searchParams.get("tab") || (itemPath !== "/demands" && itemPath !== "/admin")) {
            return `${group.group} / ${item.label}`;
          }
        }
      }
    }
  }
  return "灵鉴 Agent";
}

function isItemActive(pathname: string, href: string, search: URLSearchParams): boolean {
  const itemPath = href.split("?")[0];
  if (itemPath === "/") return pathname === "/";
  if (itemPath === "/demands" || itemPath === "/admin") {
    if (pathname !== itemPath) return false;
    // Check if query params match
    const hrefParams = new URLSearchParams(href.split("?")[1] || "");
    const tab = hrefParams.get("tab");
    if (tab) return search.get("tab") === tab;
    // No tab in href = default (first item), active when no tab in URL
    return !search.get("tab");
  }
  return pathname === itemPath || pathname.startsWith(itemPath + "/");
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [statusOk, setStatusOk] = useState<boolean | null>(null);
  const [currentUser, setCurrentUser] = useState<string>("");

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    fetch(`${apiBase}/health`).then((r) => r.ok).then((ok) => setStatusOk(ok)).catch(() => setStatusOk(false));
    const rawUser = typeof window !== "undefined" ? localStorage.getItem("user") : null; try { const userObj = rawUser ? JSON.parse(rawUser) : null; setCurrentUser(userObj?.display_name || userObj?.username || ""); } catch { setCurrentUser(rawUser || ""); }
    
  }, []);

  const pageTitle = getPageTitle(pathname, searchParams);

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <Link href="/" className="sidebar-brand">
            <span aria-hidden="true" className="brand-mark" />
            <span className="brand-text">灵鉴 Agent</span>
          </Link>
        </div>
        <nav className="sidebar-nav">
          {NAV_STRUCTURE.map((group) => (
            <div key={group.group} className="nav-group">
              <div className="nav-group-title"><span className="nav-group-icon">{group.icon}</span>{group.group}</div>
              <ul className="nav-items">
                {group.items.map((item) => (
                  <li key={item.href}><Link href={item.href} className={`nav-item ${isItemActive(pathname, item.href, searchParams) ? "active" : ""}`}>{item.label}</Link></li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
      <div className="main-area">
        <header className="topbar-new">
          <div className="topbar-left">
            <h1 className="topbar-title">{pageTitle.split(" / ")[1] || pageTitle}</h1>
            <span className="topbar-breadcrumb">{pageTitle}</span>
          </div>
          <div className="topbar-right">
            <span className={`status-dot-new ${statusOk === true ? "online" : statusOk === false ? "offline" : ""}`} />
            <span className="status-label-new">{statusOk === true ? "系统正常" : statusOk === false ? "系统异常" : "检测中"}</span>
            {currentUser && <span className="topbar-user">{currentUser}</span>}
          </div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
