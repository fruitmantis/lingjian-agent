"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, useAuth } from "./auth-provider";
import { LingjianMark, UiIcon, type IconName } from "./ui-icons";

type NavItem = { label: string; href: string; icon: IconName };
type RecentTask = { id: string; requirement: string; topPartner: string; partnerCount: number; createdAt: string };

const workspaceNav: NavItem[] = [
  { label: "开启新任务", href: "/", icon: "add" },
  { label: "场景广场", href: "/scenes", icon: "apps" },
];

const adminNav: { group: string; items: NavItem[] }[] = [
  { group: "管理概览", items: [
    { label: "后台概览", href: "/admin", icon: "home" },
    { label: "全量任务", href: "/admin/tasks", icon: "clock" },
  ] },
  { group: "业务运营", items: [
    { label: "伙伴管理", href: "/admin/partners", icon: "users" },
    { label: "需求画像", href: "/admin/demands", icon: "file" },
    { label: "项目机会", href: "/admin/opportunities", icon: "spark" },
    { label: "运营报表", href: "/admin/reports", icon: "chart" },
    { label: "能力标签", href: "/admin/tags", icon: "tag" },
  ] },
  { group: "系统管理", items: [
    { label: "用户管理", href: "/admin/users", icon: "user" },
    { label: "模型配置", href: "/admin/models", icon: "grid" },
    { label: "系统状态", href: "/admin/system", icon: "settings" },
  ] },
];

function active(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");
}

function SidebarLink({ item, pathname }: { item: NavItem; pathname: string }) {
  return <Link href={item.href} className={`nav-item ${active(pathname, item.href) ? "active" : ""}`}><UiIcon name={item.icon} size={19} /><span>{item.label}</span></Link>;
}

function taskTime(value: string): string {
  const date = new Date(value);
  const now = new Date();
  if (date.toDateString() === now.toDateString()) return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [health, setHealth] = useState<boolean | null>(null);
  const [recentTasks, setRecentTasks] = useState<RecentTask[]>([]);
  const isPublic = pathname === "/login" || pathname === "/403";
  const isAdmin = pathname.startsWith("/admin");

  useEffect(() => {
    if (isPublic) return;
    const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    fetch(`${base}/health`).then(r => r.ok).then(setHealth).catch(() => setHealth(false));
  }, [isPublic]);

  useEffect(() => {
    if (isPublic || isAdmin) return;
    apiFetch("/agent/tasks?status=active&page=1&pageSize=4", { cache: "no-store" })
      .then(async response => response.ok ? response.json() : { items: [] })
      .then(data => setRecentTasks(data.items || []))
      .catch(() => setRecentTasks([]));
  }, [isAdmin, isPublic, pathname]);

  if (isPublic) return <>{children}</>;

  return (
    <div className={`app-layout ${isAdmin ? "admin-layout" : "workspace-layout"}`}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <Link href={isAdmin ? "/admin" : "/"} className="sidebar-brand">
            <LingjianMark />
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
            <>
              <div className="nav-group primary-nav-group">
                <div className="nav-items">{workspaceNav.map(item => <SidebarLink key={item.href} item={item} pathname={pathname} />)}</div>
              </div>
              <div className="sidebar-task-section">
                <div className="sidebar-section-heading"><span>任务</span><Link href="/tasks" aria-label="筛选和查看全部任务"><UiIcon name="filter" size={16} /></Link></div>
                <Link href="/tasks" className={`sidebar-all-tasks ${active(pathname, "/tasks") ? "active" : ""}`}><span>全部</span><UiIcon name="clock" size={16} /></Link>
                <div className="sidebar-task-list">
                  {recentTasks.length === 0 ? <p className="sidebar-task-empty">暂无任务</p> : recentTasks.map(task => (
                    <Link href={`/tasks/${task.id}`} className="sidebar-task-item" key={task.id}>
                      <strong>{task.requirement}</strong>
                      <span><em>{task.topPartner || `${task.partnerCount} 个推荐伙伴`}</em><time>{taskTime(task.createdAt)}</time></span>
                    </Link>
                  ))}
                </div>
              </div>
              <div className="nav-group sidebar-tools">
                <div className="nav-group-title">伙伴</div>
                <div className="nav-items"><SidebarLink item={{ label: "伙伴洞察", href: "/partners", icon: "users" }} pathname={pathname} /></div>
              </div>
            </>
          )}
        </nav>
        <div className="sidebar-footer">
          <Link href="/account" className="sidebar-footer-link"><UiIcon name="user" size={18} /><span>个人中心</span></Link>
          {isAdmin ? <Link href="/" className="sidebar-footer-link"><UiIcon name="spark" size={18} /><span>返回灵鉴助手</span></Link> : user?.role === "admin" ? <Link href="/admin" className="sidebar-footer-link"><UiIcon name="settings" size={18} /><span>管理后台</span></Link> : null}
          <button type="button" onClick={logout} className="sidebar-footer-link sidebar-logout"><UiIcon name="logout" size={18} /><span>退出登录</span></button>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar-new">
          <div className="topbar-spacer" aria-hidden="true" />
          <div className="topbar-right">
            <span className={`status-dot-new ${health === true ? "online" : health === false ? "offline" : ""}`} />
            <span className="status-label-new">{health === true ? "系统正常" : health === false ? "系统异常" : "检测中"}</span>
            <Link href="/account" className="topbar-user"><UiIcon name="user" size={17} /><span>{user?.display_name || user?.username || "账号"}</span></Link>
          </div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
