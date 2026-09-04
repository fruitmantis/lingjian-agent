"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "./auth-provider";

type NavItem = { label: string; href: string; icon: string };

const workspaceNav: NavItem[] = [
  { label: "开启新任务", href: "/", icon: "＋" },
  { label: "场景广场", href: "/scenes", icon: "◇" },
  { label: "我的任务", href: "/tasks", icon: "◷" },
  { label: "伙伴洞察", href: "/partners", icon: "◎" },
];

const adminNav: { group: string; items: NavItem[] }[] = [
  { group: "管理概览", items: [
    { label: "后台概览", href: "/admin", icon: "▦" },
    { label: "全量任务", href: "/admin/tasks", icon: "◷" },
  ] },
  { group: "业务运营", items: [
    { label: "伙伴管理", href: "/admin/partners", icon: "◎" },
    { label: "需求画像", href: "/admin/demands", icon: "▤" },
    { label: "项目机会", href: "/admin/opportunities", icon: "◈" },
    { label: "运营报表", href: "/admin/reports", icon: "▥" },
    { label: "能力标签", href: "/admin/tags", icon: "◇" },
  ] },
  { group: "系统管理", items: [
    { label: "用户管理", href: "/admin/users", icon: "♙" },
    { label: "模型配置", href: "/admin/models", icon: "⌘" },
    { label: "系统状态", href: "/admin/system", icon: "⚙" },
  ] },
];

function active(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");
}

function pageTitle(pathname: string): string {
  const items = [...workspaceNav, ...adminNav.flatMap(group => group.items), { label: "个人中心", href: "/account", icon: "" }];
  return items.find(item => active(pathname, item.href))?.label || "灵鉴助手";
}

function SidebarLink({ item, pathname }: { item: NavItem; pathname: string }) {
  return <Link href={item.href} className={`nav-item ${active(pathname, item.href) ? "active" : ""}`}><span className="nav-glyph">{item.icon}</span><span>{item.label}</span></Link>;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [health, setHealth] = useState<boolean | null>(null);
  const isPublic = pathname === "/login" || pathname === "/403";
  const isAdmin = pathname.startsWith("/admin");

  useEffect(() => {
    if (isPublic) return;
    const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    fetch(`${base}/health`).then(r => r.ok).then(setHealth).catch(() => setHealth(false));
  }, [isPublic]);

  if (isPublic) return <>{children}</>;

  return (
    <div className={`app-layout ${isAdmin ? "admin-layout" : "workspace-layout"}`}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <Link href={isAdmin ? "/admin" : "/"} className="sidebar-brand">
            <span aria-hidden="true" className="brand-mark" />
            <span><span className="brand-text">{isAdmin ? "灵鉴管理后台" : "灵鉴助手"}</span><small>{isAdmin ? "平台运营与系统管理" : "伙伴能力智能助手"}</small></span>
          </Link>
        </div>
        <nav className="sidebar-nav" aria-label={isAdmin ? "后台导航" : "工作台导航"}>
          {isAdmin ? adminNav.map(group => (
            <div className="nav-group" key={group.group}>
              <div className="nav-group-title">{group.group}</div>
              <div className="nav-items">{group.items.map(item => <SidebarLink key={item.href} item={item} pathname={pathname} />)}</div>
            </div>
          )) : (
            <div className="nav-group">
              <div className="nav-group-title">灵鉴助手</div>
              <div className="nav-items">{workspaceNav.map(item => <SidebarLink key={item.href} item={item} pathname={pathname} />)}</div>
            </div>
          )}
        </nav>
        <div className="sidebar-footer">
          {isAdmin ? <Link href="/" className="sidebar-switch">← 返回灵鉴助手</Link> : user?.role === "admin" ? <Link href="/admin" className="sidebar-switch">进入管理后台 →</Link> : null}
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar-new">
          <div className="topbar-left"><h1 className="topbar-title">{pageTitle(pathname)}</h1><span className="topbar-breadcrumb">{isAdmin ? "管理后台" : "工作台"} / {pageTitle(pathname)}</span></div>
          <div className="topbar-right">
            <span className={`status-dot-new ${health === true ? "online" : health === false ? "offline" : ""}`} />
            <span className="status-label-new">{health === true ? "系统正常" : health === false ? "系统异常" : "检测中"}</span>
            <Link href="/account" className="topbar-user">{user?.display_name || user?.username || "账号"}</Link>
            <button type="button" onClick={logout} className="topbar-logout">退出</button>
          </div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
