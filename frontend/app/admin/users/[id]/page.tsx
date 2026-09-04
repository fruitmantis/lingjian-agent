"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { apiFetch } from "../../../../components/auth-provider";

type User = { id: string; username: string; display_name: string | null; department: string | null; role: "admin" | "user"; status: "active" | "disabled"; must_change_password: boolean; created_at: string; updated_at: string | null; last_login_at: string | null; locked_until: string | null };

export default function AdminUserDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { apiFetch(`/admin/users/${id}`, { cache: "no-store" }).then(async response => { if (!response.ok) throw new Error("用户不存在"); setUser(await response.json()); }).catch(reason => setError(reason instanceof Error ? reason.message : "加载失败")); }, [id]);
  return <main className="page"><div className="page-heading-row"><div><p className="eyebrow">User Detail</p><h1>用户详情</h1><p className="lead">查看账号状态和使用信息。</p></div><Link href="/admin/users" className="secondary-btn">返回用户列表</Link></div>{error ? <p className="error-text">{error}</p> : !user ? <p>加载中...</p> : <section className="card"><h2>{user.display_name || user.username}</h2><div className="detail-grid"><div><span>用户名</span><strong>{user.username}</strong></div><div><span>部门</span><strong>{user.department || "未设置"}</strong></div><div><span>角色</span><strong>{user.role === "admin" ? "管理员" : "普通用户"}</strong></div><div><span>状态</span><strong>{user.status === "active" ? "启用" : "停用"}</strong></div><div><span>登录锁定</span><strong>{user.locked_until && new Date(user.locked_until) > new Date() ? `至 ${new Date(user.locked_until).toLocaleString("zh-CN")}` : "未锁定"}</strong></div><div><span>首次修改密码</span><strong>{user.must_change_password ? "待完成" : "已完成"}</strong></div><div><span>最近登录</span><strong>{user.last_login_at ? new Date(user.last_login_at).toLocaleString("zh-CN") : "未登录"}</strong></div><div><span>创建时间</span><strong>{new Date(user.created_at).toLocaleString("zh-CN")}</strong></div><div><span>更新时间</span><strong>{user.updated_at ? new Date(user.updated_at).toLocaleString("zh-CN") : "-"}</strong></div></div></section>}</main>;
}
