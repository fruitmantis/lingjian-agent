"use client";

import { useState, useEffect } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ============ User Management Tab ============
type User = { id: string; username: string; display_name: string | null; role: string; created_at: string };

function UsersTab() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [submitting, setSubmitting] = useState(false);

  async function loadUsers() {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/users`, { cache: "no-store", headers: authHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setUsers(await res.json());
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); } finally { setLoading(false); }
  }

  useEffect(() => { loadUsers(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault(); setSubmitting(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/users`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ username: newUsername, password: newPassword, display_name: newDisplayName || null, role: newRole }) });
      if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      setNewUsername(""); setNewPassword(""); setNewDisplayName(""); setNewRole("user");
      await loadUsers();
    } catch (e) { setError(e instanceof Error ? e.message : "创建失败"); } finally { setSubmitting(false); }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除该用户？")) return;
    try {
      const res = await fetch(`${apiBaseUrl}/auth/users/${id}`, { method: "DELETE", headers: authHeaders() });
      if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      await loadUsers();
    } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
  }

  return (
    <div>
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
    </div>
  );
}

// ============ Capability Tags Tab ============
type Tag = { id: string; name: string; category: string; description: string | null; enabled: boolean; sortOrder: number; isPreset: boolean; createdAt: string; updatedAt: string };

const CATEGORIES = ["AI 与智能体", "云平台与迁移", "数据与数据库", "应用开发与现代化", "运维与安全", "咨询与项目管理", "其他"];

function CapabilityTagsTab() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingTag, setEditingTag] = useState<Tag | null>(null);
  const [formName, setFormName] = useState("");
  const [formCategory, setFormCategory] = useState("其他");
  const [formDesc, setFormDesc] = useState("");
  const [formSort, setFormSort] = useState(0);

  async function loadTags() {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (filterCategory) params.set("category", filterCategory);
      const res = await fetch(`${apiBaseUrl}/capability-tags?${params}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTags(await res.json());
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); } finally { setLoading(false); }
  }

  useEffect(() => { loadTags(); }, [search, filterCategory]);

  function openCreate() { setEditingTag(null); setFormName(""); setFormCategory("其他"); setFormDesc(""); setFormSort(0); setShowForm(true); }
  function openEdit(t: Tag) { setEditingTag(t); setFormName(t.name); setFormCategory(t.category); setFormDesc(t.description || ""); setFormSort(t.sortOrder); setShowForm(true); }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault(); setError(null);
    try {
      if (editingTag) {
        const res = await fetch(`${apiBaseUrl}/capability-tags/${editingTag.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: formName, category: formCategory, description: formDesc || null, sortOrder: formSort }) });
        if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      } else {
        const res = await fetch(`${apiBaseUrl}/capability-tags`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: formName, category: formCategory, description: formDesc || null, sortOrder: formSort }) });
        if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      }
      setShowForm(false); await loadTags();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
  }

  async function handleToggle(t: Tag) {
    try {
      const res = await fetch(`${apiBaseUrl}/capability-tags/${t.id}/enable`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !t.enabled }) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadTags();
    } catch (e) { setError(e instanceof Error ? e.message : "操作失败"); }
  }

  return (
    <div>
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <h2>能力标签配置</h2>
          <button onClick={openCreate} style={{ fontSize: "13px", padding: "6px 16px" }}>新增标签</button>
        </div>
        <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
          <input type="text" placeholder="搜索标签名称..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ flex: "1 1 200px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
          <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)} style={{ padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }}>
            <option value="">全部分类</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {error && <p className="error-text">{error}</p>}
        {loading ? <p style={{ marginTop: "12px" }}>加载中...</p> : tags.length === 0 ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无标签数据。</p> : (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "12px" }}>
            <thead><tr style={{ borderBottom: "1px solid var(--line)" }}>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>标签名称</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>分类</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>说明</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>排序</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>状态</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>类型</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>操作</th>
            </tr></thead>
            <tbody>{tags.map((t) => (
              <tr key={t.id} style={{ borderBottom: "1px solid var(--line)" }}>
                <td style={{ padding: "10px 8px", fontSize: "14px", fontWeight: 600 }}>{t.name}</td>
                <td style={{ padding: "10px 8px", fontSize: "13px" }}>{t.category}</td>
                <td style={{ padding: "10px 8px", fontSize: "13px", color: "var(--muted)" }}>{t.description || "-"}</td>
                <td style={{ padding: "10px 8px", fontSize: "13px" }}>{t.sortOrder}</td>
                <td style={{ padding: "10px 8px" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: t.enabled ? "#f0fdf4" : "#fef2f2", color: t.enabled ? "var(--success)" : "var(--danger)", border: `1px solid ${t.enabled ? "#bbf7d0" : "#fecaca"}` }}>{t.enabled ? "启用" : "停用"}</span></td>
                <td style={{ padding: "10px 8px" }}>{t.isPreset ? <span className="partner-tag">预置</span> : <span className="partner-tag" style={{ background: "#f0f5ff", color: "#1a4fa0", border: "1px solid #d6e4ff" }}>自定义</span>}</td>
                <td style={{ padding: "10px 8px" }}>
                  <div style={{ display: "flex", gap: "6px" }}>
                    <button onClick={() => openEdit(t)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>编辑</button>
                    <button onClick={() => handleToggle(t)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>{t.enabled ? "停用" : "启用"}</button>
                  </div>
                </td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </section>

      {showForm && (
        <section className="card">
          <h2>{editingTag ? "编辑标签" : "新增标签"}</h2>
          <form onSubmit={handleSave} className="partner-form" style={{ marginTop: "12px" }}>
            <div className="form-row"><label htmlFor="formName">标签名称</label><input id="formName" type="text" value={formName} onChange={(e) => setFormName(e.target.value)} required maxLength={50} placeholder="标签名称" /></div>
            <div className="form-row"><label htmlFor="formCategory">分类</label><select id="formCategory" value={formCategory} onChange={(e) => setFormCategory(e.target.value)} style={{ padding: "10px 14px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }}>{CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}</select></div>
            <div className="form-row"><label htmlFor="formDesc">说明</label><input id="formDesc" type="text" value={formDesc} onChange={(e) => setFormDesc(e.target.value)} placeholder="选填" /></div>
            <div className="form-row"><label htmlFor="formSort">排序</label><input id="formSort" type="number" value={formSort} onChange={(e) => setFormSort(parseInt(e.target.value) || 0)} style={{ width: "80px" }} /></div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button type="submit">保存</button>
              <button type="button" onClick={() => setShowForm(false)} className="secondary-btn">取消</button>
            </div>
          </form>
        </section>
      )}
    </div>
  );
}

// ============ Main Admin Page ============
export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<"users" | "tags">("users");

  return (
    <main className="page">
      <p className="eyebrow">System Administration</p>
      <h1>系统管理</h1>
      <p className="lead">维护用户、标签、字典等平台基础配置。</p>

      <div style={{ display: "flex", gap: "4px", marginBottom: "20px", borderBottom: "2px solid var(--line)" }}>
        <button onClick={() => setActiveTab("users")} style={{ padding: "10px 20px", fontSize: "14px", fontWeight: 600, border: "none", borderBottom: activeTab === "users" ? "2px solid var(--brand)" : "2px solid transparent", background: "transparent", color: activeTab === "users" ? "var(--brand)" : "var(--muted)", cursor: "pointer", marginBottom: "-2px" }}>用户管理</button>
        <button onClick={() => setActiveTab("tags")} style={{ padding: "10px 20px", fontSize: "14px", fontWeight: 600, border: "none", borderBottom: activeTab === "tags" ? "2px solid var(--brand)" : "2px solid transparent", background: "transparent", color: activeTab === "tags" ? "var(--brand)" : "var(--muted)", cursor: "pointer", marginBottom: "-2px" }}>能力标签配置</button>
      </div>

      {activeTab === "users" ? <UsersTab /> : <CapabilityTagsTab />}
    </main>
  );
}