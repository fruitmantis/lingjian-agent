"use client";

import type { Metadata } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import "./globals.css";

export const metadata: Metadata = { title: "灵鉴 Agent", description: "交付伙伴智能匹配智能体" };

const NAV_STRUCTURE = [
  {
    group: "Agent 工作台",
    icon: "🎯",
    items: [
      { label: "智能匹配", href: "/" },
      { label: "匹配历史", href: "/?history=true" },
    ],
  },
  {
    group: "伙伴中心",
    icon: "👥",
    items: [
      { label: "伙伴资料管理", href: "/partners" },
      { label: "伙伴画像", href: "/profiles" },
    ],
  },
  {
    group: "需求运营",
    icon: "📊",
    items: [
      { label: "需求画像", href: "/demands" },
      { label: "项目机会库", href: "/demands?tab=opportunities" },
      { label: "运营报表", href: "/demands?tab=report" },
    ],
  },
  {
    group: "系统管理",
    icon: "⚙️",
    items: [
      { label: "用户管理", href: "/admin" },
      { label: "能力标签", href: "/admin?tab=tags" },
      { label: "标签分类", href: "/admin?tab=tags&sub=categories" },
      { label: "AI 标签建议", href: "/admin?tab=tags&sub=suggestions" },
      { label: "模型配置", href: "/admin?tab=model" },
      { label: "系统状态", href: "/admin?tab=status" },
    ],
  },
];

function getPageTitle(pathname: string): string {
  for (const group of NAV_STRUCTURE) {
    for (const item of group.items) {
      const itemPath = item.href.split("?")[0];
      if (pathname === itemPath || pathname.startsWith(itemPath + "/")) {
        return `${group.group} / ${item.label}`;
      }
    }
  }
  return "灵鉴 Agent";
}

function isItemActive(pathname: string, href: string): boolean {
  const itemPath = href.split("?")[0];
  if (itemPath === "/") return pathname === "/";
  return pathname === itemPath || pathname.startsWith(itemPath + "/");
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const [statusOk, setStatusOk] = useState<boolean | null>(null);
  const [currentUser, setCurrentUser] = useState<string>("");

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    fetch(`${apiBase}/health`)
      .then((r) => r.ok)
      .then((ok) => setStatusOk(ok))
      .catch(() => setStatusOk(false));
    const user = typeof window !== "undefined" ? localStorage.getItem("user") : null;
    if (user) setCurrentUser(user);
  }, []);

  const pageTitle = getPageTitle(pathname);

  return (
    <html lang="zh-CN">
      <body>
        <div className="app-layout">
          {/* Sidebar */}
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
                  <div className="nav-group-title">
                    <span className="nav-group-icon">{group.icon}</span>
                    {group.group}
                  </div>
                  <ul className="nav-items">
                    {group.items.map((item) => (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          className={`nav-item ${isItemActive(pathname, item.href) ? "active" : ""}`}
                        >
                          {item.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </nav>
          </aside>

          {/* Main area */}
          <div className="main-area">
            {/* Top bar */}
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

            {/* Page content */}
            <main className="page-content">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}