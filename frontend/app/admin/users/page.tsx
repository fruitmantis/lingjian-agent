"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { UserDeleteButton } from "../../../components/user-delete-button";
import { UiIcon } from "../../../components/ui-icons";
import { formatAuthMethods, formatIdentityKeyHint, type AuthMethod } from "../../../lib/auth-methods";
import { adminApiFetch as apiFetch } from "../../../components/auth-provider";

type User = {
  id: string; username: string; display_name: string | null; department: string | null;
  role: "admin" | "user"; status: "active" | "disabled"; must_change_password: boolean;
  auth_methods: AuthMethod[]; identity_key_hint: string | null;
  created_at: string; last_login_at: string | null; locked_until: string | null;
};

type AuditLog = {
  id: string; action: string; actorName: string | null; targetName: string | null;
  summary: string | null; ipAddress: string | null; createdAt: string;
};

const actionLabels: Record<string, string> = {
  "identity.created": "启用本机身份", "identity.login": "本机身份进入",
  "auth.login_success": "登录成功", "auth.login_failed": "登录失败", "auth.password_changed": "修改密码",
  "auth.logout_all": "注销全部登录", "user.self_update": "修改个人信息", "user_application.submitted": "提交账号申请",
  "admin.user_deleted": "删除普通用户", "admin.user_created": "创建用户", "admin.user_updated": "修改用户", "admin.user_active": "启用用户",
  "admin.user_disabled": "停用用户", "admin.password_reset": "重置密码", "admin.user_unlocked": "解锁用户",
  "admin.user_application_approved": "批准账号申请", "admin.user_application_rejected": "驳回账号申请",
};


export default function AdminUsersPage() {
  const [tab, setTab] = useState<"users" | "audit">("users");
  const [users, setUsers] = useState<User[]>([]);
  const [audits, setAudits] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [role, setRole] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<User | null>(null);
  const [editForm, setEditForm] = useState({ display_name: "", department: "", role: "user" });
  const [createForm, setCreateForm] = useState({ username: "", display_name: "", department: "", role: "admin" });
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function loadUsers(nextPage = page) {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ page: String(nextPage), pageSize: "20" });
      if (keyword.trim()) params.set("keyword", keyword.trim());
      if (role) params.set("role", role);
      if (statusFilter) params.set("status", statusFilter);
      const response = await apiFetch(`/admin/users?${params}`, { cache: "no-store" });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "用户加载失败");
      const data = await response.json();
      setUsers(data.items); setTotal(data.total); setPage(data.page);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "用户加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadUsers(1);
  }, []);
  useEffect(() => {
    if (tab !== "audit") return;
    setLoading(true); setError(null);
    apiFetch("/admin/user-audit-logs?page=1&pageSize=100", { cache: "no-store" }).then(async response => {
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "日志加载失败");
      setAudits((await response.json()).items);
    }).catch(reason => setError(reason instanceof Error ? reason.message : "日志加载失败")).finally(() => setLoading(false));
  }, [tab]);

  async function runAction(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  async function createUser(event: FormEvent) {
    event.preventDefault(); setError(null); setMessage(null);
    await runAction(async () => {
      setTemporaryPassword(null);
      const response = await apiFetch("/admin/users", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(createForm),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) { setError(data.detail || "创建失败"); return; }
      setTemporaryPassword(data.temporaryPassword);
      setCreateForm({ username: "", display_name: "", department: "", role: "admin" });
      await loadUsers(1);
    });
  }

  function startEdit(user: User) {
    setEditing(user);
    setEditForm({ display_name: user.display_name || "", department: user.department || "", role: user.role });
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault(); if (!editing) return;
    await runAction(async () => {
      const response = await apiFetch(`/admin/users/${editing.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(editForm),
      });
      if (response.ok) { setEditing(null); await loadUsers(); }
      else setError((await response.json().catch(() => ({}))).detail || "保存失败");
    });
  }

  async function toggleStatus(user: User) {
    const next = user.status === "active" ? "disabled" : "active";
    if (next === "disabled" && !confirm(`确定停用账号“${user.username}”？`)) return;
    await runAction(async () => {
      const response = await apiFetch(`/admin/users/${user.id}/status`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: next }),
      });
      if (response.ok) await loadUsers();
      else setError((await response.json().catch(() => ({}))).detail || "状态修改失败");
    });
  }

  async function resetPassword(user: User) {
    if (!confirm(`确定重置“${user.username}”的密码？其现有登录状态将立即失效。`)) return;
    await runAction(async () => {
      setTemporaryPassword(null);
      const response = await apiFetch(`/admin/users/${user.id}/reset-password`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (response.ok) { setTemporaryPassword(data.temporaryPassword); await loadUsers(); }
      else setError(data.detail || "重置失败");
    });
  }

  async function unlock(user: User) {
    await runAction(async () => {
      const response = await apiFetch(`/admin/users/${user.id}/unlock`, { method: "POST" });
      if (response.ok) await loadUsers(); else setError("解锁失败");
    });
  }

  return (
    <main className="page">
      <p className="eyebrow">User Management</p>
      <h1>用户管理</h1>
      <p className="lead">管理本机用户、管理员账号和登录安全。</p>
      <div className="page-tabs">
        <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>账号列表</button>
        <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>操作日志</button>
      </div>

      {temporaryPassword && <div className="temporary-password-card"><div><strong>一次性临时密码</strong><p>请立即复制并通过公司内部安全渠道交付。关闭后不再显示。</p></div><code>{temporaryPassword}</code><button className="secondary-btn" onClick={() => navigator.clipboard.writeText(temporaryPassword)}>复制</button><button className="secondary-btn" onClick={() => setTemporaryPassword(null)}>关闭</button></div>}
      {message && <div className="notice-neutral">{message}</div>}
      {error && <div className="inline-error-actions"><p className="error-text">{error}</p><button className="secondary-btn" onClick={() => void (loadUsers(page))}>重试</button></div>}

      {tab === "users" && <>
        <section className="card">
          <h2>创建管理员</h2>
          <p className="meta-text">普通用户由本机自动建立身份，此处仅创建独立管理员账号。</p>
          <form onSubmit={createUser} className="form-grid">
            <div className="form-row"><label>用户名</label><input value={createForm.username} onChange={event => setCreateForm(current => ({ ...current, username: event.target.value }))} pattern="[A-Za-z0-9._-]+" required /></div>
            <div className="form-row"><label>显示名称</label><input value={createForm.display_name} onChange={event => setCreateForm(current => ({ ...current, display_name: event.target.value }))} required /></div>
            <div className="form-row"><label>所属部门</label><input value={createForm.department} onChange={event => setCreateForm(current => ({ ...current, department: event.target.value }))} /></div>

            <div className="form-span-two"><button disabled={busy}>创建管理员并生成临时密码</button></div>
          </form>
        </section>
        <section className="card">
          <div className="user-filter-row"><form onSubmit={event => { event.preventDefault(); void loadUsers(1); }} className="inline-search"><input value={keyword} onChange={event => setKeyword(event.target.value)} placeholder="搜索用户名或姓名" /><select value={role} onChange={event => setRole(event.target.value)}><option value="">全部角色</option><option value="user">普通用户</option><option value="admin">管理员</option></select><select value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">全部状态</option><option value="active">启用</option><option value="disabled">停用</option></select><button>筛选</button></form><span className="result-count">共 {total} 个账号</span></div>
          {loading ? <p>加载中...</p> : <div className="table-wrap"><table className="data-table admin-users-table"><thead><tr><th>用户</th><th>部门</th><th>角色</th><th scope="col">鉴权方式</th><th scope="col">Key 标识</th><th>状态</th><th>首次改密</th><th>最近登录</th><th>操作</th></tr></thead><tbody>{users.map(user => { const locked = Boolean(user.locked_until && new Date(user.locked_until) > new Date()); return <tr key={user.id}><td><Link href={`/admin/users/${user.id}`}><strong>{user.display_name || user.username}</strong></Link><small>{user.username}</small></td><td>{user.department || "-"}</td><td>{user.role === "admin" ? "管理员" : "普通用户"}</td><td>{formatAuthMethods(user.auth_methods)}</td><td><code className="admin-identity-key-hint" title="随机部分前 2 位及末 5 位">{formatIdentityKeyHint(user)}</code></td><td><span className={`status-badge ${locked ? "locked" : user.status}`}>{locked ? "已锁定" : user.status === "active" ? "启用" : "停用"}</span></td><td>{user.role === "user" ? "无需密码" : user.must_change_password ? "待修改" : "已完成"}</td><td>{user.last_login_at ? new Date(user.last_login_at).toLocaleString("zh-CN") : "未登录"}</td><td><div className="table-actions"><button className="secondary-btn" onClick={() => startEdit(user)}>编辑</button><button disabled={busy} className="secondary-btn" onClick={() => toggleStatus(user)}>{user.status === "active" ? "停用" : "启用"}</button>{user.role === "admin" && <button disabled={busy} className="secondary-btn" onClick={() => resetPassword(user)}>重置密码</button>}{user.role === "user" && user.auth_methods?.some(method => method === "browser" || method === "passkey" || method === "key") && <UserDeleteButton userId={user.id} onDeleted={() => { setMessage("用户已删除"); void loadUsers(1); }} />}{user.role === "admin" && locked && <button disabled={busy} className="secondary-btn" onClick={() => unlock(user)}>解锁</button>}</div></td></tr>; })}</tbody></table></div>}
          <div className="pagination"><button className="secondary-btn" disabled={page <= 1} onClick={() => loadUsers(page - 1)}>上一页</button><span>第 {page} / {Math.max(1, Math.ceil(total / 20))} 页</span><button className="secondary-btn" disabled={page * 20 >= total} onClick={() => loadUsers(page + 1)}>下一页</button></div>
        </section>
        {editing && <div className="modal-backdrop"><form onSubmit={saveEdit} className="card modal-card"><h2>编辑用户：{editing.username}</h2><div className="form-row"><label>显示名称</label><input value={editForm.display_name} onChange={event => setEditForm(current => ({ ...current, display_name: event.target.value }))} required /></div><div className="form-row"><label>所属部门</label><input value={editForm.department} onChange={event => setEditForm(current => ({ ...current, department: event.target.value }))} /></div><div className="modal-actions"><button type="button" className="secondary-btn" onClick={() => setEditing(null)}>取消</button><button disabled={busy}>保存</button></div></form></div>}
      </>}

      {tab === "audit" && <section className="card"><h2>用户操作日志</h2>{loading ? <p>加载中...</p> : <div className="table-wrap"><table className="data-table"><thead><tr><th>时间</th><th>操作</th><th>操作者</th><th>目标用户</th><th>摘要</th><th>IP</th></tr></thead><tbody>{audits.map(item => <tr key={item.id}><td>{new Date(item.createdAt).toLocaleString("zh-CN")}</td><td>{actionLabels[item.action] || item.action}</td><td>{item.actorName || "系统"}</td><td>{item.targetName || "-"}</td><td>{item.summary || "-"}</td><td>{item.ipAddress || "-"}</td></tr>)}</tbody></table></div>}</section>}
    </main>
  );
}
