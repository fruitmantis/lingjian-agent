"use client";

import { useState, useEffect } from "react";

type User = { id: string; username: string; display_name: string | null; role: string; created_at: string };
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [submitting, setSubmitting] = useState(false);

  async function loadUsers() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/users`, { cache: "no-store", headers: authHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setUsers(await res.json());
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); } finally { setLoading(false); }
  }

  useEffect(() => { loadUsers(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/users`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ username: newUsername, password: newPassword, display_name: newDisplayName || null, role: newRole }) });
      if (!res.ok) { const errData = await res.json().catch(() => ({})); throw new Error(errData.detail || `HTTP ${res.status}`); }
      setNewUsername(""); setNewPassword(""); setNewDisplayName(""); setNewRole("user");
      await loadUsers();
    } catch (e) { setError(e instanceof Error ? e.message : "创建失败"); } finally { setSubmitting(false); }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除该用户？")) return;
    try {
      const res = await fetch(`${apiBaseUrl}/auth/users/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok) { const errData = await res.json().catch(() => ({})); throw new Error(errData.detail || `HTTP ${res.status}`); }
      await loadUsers();
    } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
  }

  return (
    <main className="page">
      <p className="eyebrow">User Management</p>
      <h1>用户管理</h1>
      <p className="lead">管理系统用户账号。</p>
      <section className="card">
        <h2>新增用户</h2>
        <form onSubmit={handleCreate} className="partner-form">
          <div className="form-row"><label htmlFor="newUsername">用户名</label><input id="newUsername" type="text" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} required minLength={1} maxLength={50} placeholder="用户名" /></div>
          <div className="form-row"><label htmlFor="newPassword">密码</label><input id="newPassword" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required minLength={6} placeholder="至少6位" /></div>
          <div className="form-row"><label htmlFor="newDisplayName">显示名称</label><input id="newDisplayName" type="text" value={newDisplayName} onChange={(e) => setNewDisplayName(e.target.value)} placeholder="选填" /></div>
          <div className="form-row"><label htmlFor="newRole">角色</label><select id="newRole" value={newRole} onChange={(e) => setNewRole(e.target.value)} style={{ padding: "10px 14px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }}><option value="user">普通用户</option><option value="admin">管理员</option></select></div>
          <button type="submit" disabled={submitting}>{submitting ? "创建中..." : "新增用户"}</button>
        </form>
        {error && <p className="error-text">{error}</p>}
      </section>
      <section className="card">
        <h2>用户列表</h2>
        {loading ? <p>加载中...</p> : (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "12px" }}>
            <thead><tr style={{ borderBottom: "1px solid var(--line)" }}><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>用户名</th><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>显示名称</th><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>角色</th><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>创建时间</th><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>操作</th></tr></thead>
            <tbody>{users.map((u) => (<tr key={u.id} style={{ borderBottom: "1px solid var(--line)" }}><td style={{ padding: "10px 8px", fontSize: "14px" }}>{u.username}</td><td style={{ padding: "10px 8px", fontSize: "14px" }}>{u.display_name || "-"}</td><td style={{ padding: "10px 8px", fontSize: "14px" }}><span className="tag">{u.role === "admin" ? "管理员" : "用户"}</span></td><td style={{ padding: "10px 8px", fontSize: "13px", color: "var(--muted)" }}>{u.created_at.slice(0, 10)}</td><td style={{ padding: "10px 8px" }}><button onClick={() => handleDelete(u.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>删除</button></td></tr>))}</tbody>
          </table>
        )}
      </section>
    </main>
  );
}
