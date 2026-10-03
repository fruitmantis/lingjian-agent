"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { PASSWORD_CHANGE_PATH, useAuth } from "./auth-provider";
import { LingjianMark, UiIcon, type IconName } from "./ui-icons";

import { TaskTransitionLayer } from "./task-transition";
import { NEW_TASK, TaskSidebar, useTaskNavigation } from "./task-navigation";

type NavItem = { label: string; href: string; icon: IconName };

const workspaceNav: NavItem[] = [
  { label: "场景广场", href: "/scenes", icon: "apps" },
  { label: "伙伴画像", href: "/partners", icon: "users" },
  { label: "资源中心", href: "/resources", icon: "grid" },
];

const adminNav: { group: string; items: NavItem[] }[] = [
  { group: "管理概览", items: [
    { label: "后台概览", href: "/admin", icon: "home" },
    { label: "全量任务", href: "/admin/tasks", icon: "clock" },
  ] },
  { group: "业务运营", items: [
    { label: "伙伴管理", href: "/admin/partners", icon: "users" },
    { label: "伙伴资料", href: "/admin/partner-materials", icon: "file" },
    { label: "需求画像", href: "/admin/demands", icon: "file" },
    { label: "项目机会", href: "/admin/opportunities", icon: "spark" },
    { label: "运营报表", href: "/admin/reports", icon: "chart" },
    { label: "课程与实验", href: "/admin/resources", icon: "file" },
    { label: "能力标签", href: "/admin/tags", icon: "tag" },
  ] },
  { group: "系统管理", items: [
    { label: "用户管理", href: "/admin/users", icon: "user" },
    { label: "智能体管理", href: "/admin/models", icon: "grid" },
    { label: "系统状态", href: "/admin/system", icon: "settings" },
    { label: "问题反馈", href: "/admin/feedback", icon: "file" },
  ] },
];

function active(pathname: string, href: string): boolean {
  return href === "/" || href === "/admin" ? pathname === href : pathname === href || pathname.startsWith(href + "/");
}

function SidebarLink({ item, pathname }: { item: NavItem; pathname: string }) {
  return <Link href={item.href} aria-current={active(pathname, item.href) ? "page" : undefined} className={`nav-item ${active(pathname, item.href) ? "active" : ""}`}><UiIcon name={item.icon} size={19} /><span>{item.label}</span></Link>;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const {arrival} = useTaskNavigation();
  const { user, logout } = useAuth();
  const [health, setHealth] = useState<boolean | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const isStandalone = pathname === "/admin/login" || pathname === "/login" || pathname === "/403" || pathname === PASSWORD_CHANGE_PATH;
  const isAdmin = pathname.startsWith("/admin");

  useEffect(() => { setNavigationOpen(false); }, [pathname]);

  useEffect(() => {
    if (isStandalone) return;
    const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
    fetch(`${base}/health`).then(r => r.ok).then(setHealth).catch(() => setHealth(false));
  }, [isStandalone]);

  if (isStandalone) return <>{children}</>;

  return (
    <div className={`app-layout ${isAdmin ? "admin-layout" : "workspace-layout"} coze-workspace${navigationOpen ? " navigation-open" : ""}`}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <Link href={isAdmin ? "/admin" : "/"} className="sidebar-brand">
            <LingjianMark />
            <span><span className="brand-text">伴飞 Agent</span><small>{isAdmin ? "平台运营与系统管理" : "伙伴能力智能助手"}</small></span>
          </Link>
          <button type="button" className="workspace-nav-toggle" aria-expanded={navigationOpen} aria-controls="workspace-navigation workspace-footer" onClick={() => setNavigationOpen(value => !value)}><UiIcon name="apps" size={18}/><span>{navigationOpen ? "收起导航" : "展开导航"}</span></button>
        </div>
        <nav id="workspace-navigation" className="sidebar-nav" aria-label={isAdmin ? "后台导航" : "工作台导航"}>
          {isAdmin ? adminNav.map(group => (
            <div className="nav-group" key={group.group}>
              <div className="nav-group-title">{group.group}</div>
              <div className="nav-items">{group.items.map(item => <SidebarLink key={item.href} item={item} pathname={pathname} />)}</div>
            </div>
          )) : (
            <>
              <div className="nav-group primary-nav-group">
                <Link href="/" className="sidebar-new-task" onClick={() => window.dispatchEvent(new Event(NEW_TASK))}><UiIcon name="add" size={20} /><span>开启新任务</span></Link>
                <div className="nav-items">{workspaceNav.map(item => <SidebarLink key={item.href} item={item} pathname={pathname} />)}</div>
              </div>
              <TaskSidebar />
            </>
          )}
        </nav>
        <div id="workspace-footer" className="sidebar-footer">
          {!isAdmin && <Link href="/feedback" className={`sidebar-footer-link ${pathname === "/feedback" ? "active" : ""}`} aria-current={pathname === "/feedback" ? "page" : undefined}><UiIcon name="file" size={18} /><span>问题反馈</span></Link>}
          <Link href={isAdmin ? "/admin/account" : "/account"} className={`sidebar-footer-link ${!isAdmin && pathname === "/account" ? "active" : ""}`} aria-current={pathname === "/account" ? "page" : undefined}><UiIcon name="user" size={18} /><span>个人中心</span></Link>
          {isAdmin ? <Link href="/" className="sidebar-footer-link"><UiIcon name="spark" size={18} /><span>返回伴飞 Agent</span></Link> : <Link href="/admin/login" className="sidebar-footer-link"><UiIcon name="settings" size={18} /><span>管理后台</span></Link>}
          <button type="button" onClick={logout} className="sidebar-footer-link sidebar-logout"><UiIcon name="logout" size={18} /><span>{isAdmin ? "退出登录" : "退出"}</span></button>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar-new">
          <div className="topbar-spacer" aria-hidden="true" />
          <div className="topbar-right">
            <span className={`status-dot-new ${health === true ? "online" : health === false ? "offline" : ""}`} />
            <span className="status-label-new">{health === true ? "系统正常" : health === false ? "系统异常" : "检测中"}</span>
            <Link href={isAdmin ? "/admin/account" : "/account"} className="topbar-user"><UiIcon name="user" size={17} /><span>{user?.display_name || user?.username || "账号"}</span></Link>
          </div>
        </header>
        <main className="page-content"><div className="task-route-content" style={arrival?.phase === "waiting" ? {visibility:"hidden"} : undefined}>{children}</div><TaskTransitionLayer/></main>
      </div>
    </div>
  );
}
