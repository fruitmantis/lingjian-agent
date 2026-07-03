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

// ============ Capability Tags Tab (inline edit) ============
type Tag = { id: string; name: string; category: string; description: string | null; enabled: boolean; sortOrder: number; isPreset: boolean; createdAt: string; updatedAt: string };

const DEFAULT_CATEGORIES = ["AI 与智能体", "云平台与迁移", "数据与数据库", "应用开发与现代化", "运维与安全", "咨询与项目管理", "其他"];

function CapabilityTagsTab() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [categories, setCategories] = useState<string[]>(DEFAULT_CATEGORIES);
  const [subTab, setSubTab] = useState<"tags" | "categories" | "suggestions">("tags");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [isNewRow, setIsNewRow] = useState(false);
  const [eName, setEName] = useState("");
  const [eCat, setECat] = useState("其他");
  const [eDesc, setEDesc] = useState("");
  const [eSort, setESort] = useState(0);

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

  async function loadCategories() {
    try {
      const res = await fetch(`${apiBaseUrl}/capability-tags/categories?enabled=true`, { cache: "no-store" });
      if (res.ok) setCategories((await res.json()).map((c: any) => c.name));
    } catch {}
  }
  useEffect(() => { loadCategories(); }, []);

  function startEdit(t: Tag) {
    setEditingId(t.id); setIsNewRow(false);
    setEName(t.name); setECat(t.category); setEDesc(t.description || ""); setESort(t.sortOrder);
  }
  function startNew() {
    setIsNewRow(true); setEditingId(null);
    setEName(""); setECat("其他"); setEDesc(""); setESort(0);
  }
  function cancelEdit() { setEditingId(null); setIsNewRow(false); }

  async function saveEdit(id: string | null) {
    setError(null);
    try {
      const body = JSON.stringify({ name: eName, category: eCat, description: eDesc || null, sortOrder: eSort });
      if (id) {
        const res = await fetch(`${apiBaseUrl}/capability-tags/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body });
        if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      } else {
        const res = await fetch(`${apiBaseUrl}/capability-tags`, { method: "POST", headers: { "Content-Type": "application/json" }, body });
        if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      }
      cancelEdit(); await loadTags();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
  }

  async function handleToggle(t: Tag) {
    try {
      const res = await fetch(`${apiBaseUrl}/capability-tags/${t.id}/enable`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !t.enabled }) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadTags();
    } catch (e) { setError(e instanceof Error ? e.message : "操作失败"); }
  }

  const isEditing = editingId !== null || isNewRow;

  const [catList, setCatList] = useState<any[]>([]);
  const [catLoading, setCatLoading] = useState(false);
  const [catError, setCatError] = useState<string | null>(null);
  const [catSearch, setCatSearch] = useState("");
  const [catFilterEnabled, setCatFilterEnabled] = useState("");
  const [editCatId, setEditCatId] = useState<string | null>(null);
  const [isNewCat, setIsNewCat] = useState(false);
  const [cN, setCN] = useState(""); const [cCo, setCCo] = useState(""); const [cD, setCD] = useState(""); const [cS, setCS] = useState(0);

  async function loadCatList() {
    setCatLoading(true); setCatError(null);
    try {
      const p = new URLSearchParams();
      if (catSearch) p.set("search", catSearch);
      if (catFilterEnabled) p.set("enabled", catFilterEnabled === "true" ? "true" : "false");
      const r = await fetch(`${apiBaseUrl}/capability-tags/categories?${p}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setCatList(await r.json());
    } catch (e) { setCatError(e instanceof Error ? e.message : "加载失败"); } finally { setCatLoading(false); }
  }
  useEffect(() => { if (subTab === "categories") loadCatList(); }, [subTab, catSearch, catFilterEnabled]);

  function startCatEdit(c: any) { setEditCatId(c.id); setIsNewCat(false); setCN(c.name); setCCo(c.code||""); setCD(c.description||""); setCS(c.sortOrder); }
  function startNewCat() { setIsNewCat(true); setEditCatId(null); setCN(""); setCCo(""); setCD(""); setCS(0); }
  function cancelCatEdit() { setEditCatId(null); setIsNewCat(false); }
  async function saveCatEdit(id: string | null) {
    setCatError(null);
    try {
      const body = JSON.stringify({ name: cN, code: cCo||null, description: cD||null, sortOrder: cS });
      const url = id ? `${apiBaseUrl}/capability-tags/categories/${id}` : `${apiBaseUrl}/capability-tags/categories`;
      const method = id ? "PUT" : "POST";
      const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body });
      if (!r.ok) { const ed = await r.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${r.status}`); }
      cancelCatEdit(); await loadCatList(); await loadCategories();
    } catch (e) { setCatError(e instanceof Error ? e.message : "保存失败"); }
  }
  async function toggleCatEnable(c: any) {
    try { const r = await fetch(`${apiBaseUrl}/capability-tags/categories/${c.id}/enable`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !c.enabled }) }); if (!r.ok) throw new Error(`HTTP ${r.status}`); await loadCatList(); await loadCategories(); }
    catch (e) { setCatError(e instanceof Error ? e.message : "操作失败"); }
  }

  // Suggestion tab state
  const [sugList, setSugList] = useState<any[]>([]);
  const [sugLoading, setSugLoading] = useState(false);
  const [sugError, setSugError] = useState<string | null>(null);
  const [sugStatus, setSugStatus] = useState("");
  const [sugKeyword, setSugKeyword] = useState("");
  const [scanning, setScanning] = useState(false);
  const [adoptingId, setAdoptingId] = useState<string | null>(null);
  const [adoptName, setAdoptName] = useState("");
  const [adoptCat, setAdoptCat] = useState("");
  const [adoptDesc, setAdoptDesc] = useState("");
  const [adoptSort, setAdoptSort] = useState(0);

  async function loadSugList() {
    setSugLoading(true); setSugError(null);
    try {
      const p = new URLSearchParams();
      if (sugStatus) p.set("status", sugStatus);
      if (sugKeyword) p.set("keyword", sugKeyword);
      const r = await fetch(`${apiBaseUrl}/capability-tags/suggestions?${p}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSugList(await r.json());
    } catch (e) { setSugError(e instanceof Error ? e.message : "加载失败"); } finally { setSugLoading(false); }
  }
  useEffect(() => { if (subTab === "suggestions") loadSugList(); }, [subTab, sugStatus, sugKeyword]);

  function startAdopt(s: any) { setAdoptingId(s.id); setAdoptName(s.suggestedName); setAdoptCat(""); setAdoptDesc(s.description || ""); setAdoptSort(0); }
  function cancelAdopt() { setAdoptingId(null); }
  async function confirmAdopt(id: string) {
    setSugError(null);
    try {
      const r = await fetch(`${apiBaseUrl}/capability-tags/suggestions/${id}/adopt`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: adoptName, categoryId: adoptCat || null, description: adoptDesc || null, sortOrder: adoptSort }) });
      if (!r.ok) { const ed = await r.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${r.status}`); }
      cancelAdopt(); await loadSugList(); await loadCategories();
    } catch (e) { setSugError(e instanceof Error ? e.message : "采纳失败"); }
  }
  async function scanSuggestions() {
    setScanning(true); setSugError(null);
    try {
      const r = await fetch(`${apiBaseUrl}/capability-tags/suggestions/scan`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setSugError(d.created > 0 ? `扫描完成，新增 ${d.created} 条建议` : "扫描完成，未发现新建议");
      await loadSugList();
    } catch (e) { setSugError(e instanceof Error ? e.message : "扫描失败"); } finally { setScanning(false); }
  }

  const isCatEditing = editCatId !== null || isNewCat;
  const inpStyle = { padding: "4px 8px", border: "1px solid var(--brand)", borderRadius: "4px", fontSize: "13px", width: "100%", boxSizing: "border-box" as const };
  const checkBtn = { fontSize: "16px", padding: "2px 10px", background: "var(--success)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", lineHeight: 1 };
  const crossBtn = { fontSize: "16px", padding: "2px 10px", background: "var(--danger)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", lineHeight: 1 };

  return (
    <div>
      <div style={{ display: "flex", gap: "4px", marginBottom: "16px", borderBottom: "2px solid var(--line)" }}>
        <button onClick={() => setSubTab("tags")} style={{ padding: "8px 16px", fontSize: "13px", fontWeight: 600, border: "none", borderBottom: subTab === "tags" ? "2px solid var(--brand)" : "2px solid transparent", background: "transparent", color: subTab === "tags" ? "var(--brand)" : "var(--muted)", cursor: "pointer", marginBottom: "-2px" }}>能力标签</button>
        <button onClick={() => setSubTab("categories")} style={{ padding: "8px 16px", fontSize: "13px", fontWeight: 600, border: "none", borderBottom: subTab === "categories" ? "2px solid var(--brand)" : "2px solid transparent", background: "transparent", color: subTab === "categories" ? "var(--brand)" : "var(--muted)", cursor: "pointer", marginBottom: "-2px" }}>标签分类</button>
        <button onClick={() => setSubTab("suggestions")} style={{ padding: "8px 16px", fontSize: "13px", fontWeight: 600, border: "none", borderBottom: subTab === "suggestions" ? "2px solid var(--brand)" : "2px solid transparent", background: "transparent", color: subTab === "suggestions" ? "var(--brand)" : "var(--muted)", cursor: "pointer", marginBottom: "-2px" }}>AI 标签建议</button>
      </div>

      {subTab === "categories" && (
        <section className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <h2>标签分类配置</h2>
            <button onClick={startNewCat} disabled={isCatEditing} style={{ fontSize: "13px", padding: "6px 16px", opacity: isCatEditing ? 0.5 : 1 }}>新增分类</button>
          </div>
          <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
            <input type="text" placeholder="搜索分类名称..." value={catSearch} onChange={(e) => setCatSearch(e.target.value)} style={{ flex: "1 1 200px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
            <select value={catFilterEnabled} onChange={(e) => setCatFilterEnabled(e.target.value)} style={{ padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }}><option value="">全部状态</option><option value="true">启用</option><option value="false">停用</option></select>
          </div>
          {catError && <p className="error-text">{catError}</p>}
          {catLoading ? <p style={{ marginTop: "12px" }}>加载中...</p> : (catList.length === 0 && !isNewCat) ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无分类数据。</p> : (
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "12px" }}>
              <thead><tr style={{ borderBottom: "1px solid var(--line)" }}>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>分类名称</th>
                                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>说明</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>排序</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>状态</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>类型</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>操作</th>
              </tr></thead>
              <tbody>
                {isNewCat && (
                  <tr style={{ borderBottom: "1px solid var(--line)", background: "#fffbeb" }}>
                    <td style={{ padding: "8px" }}><input type="text" value={cN} onChange={(e) => setCN(e.target.value)} placeholder="分类名称" style={inpStyle} autoFocus /></td>
                                        <td style={{ padding: "8px" }}><input type="text" value={cD} onChange={(e) => setCD(e.target.value)} placeholder="选填" style={inpStyle} /></td>
                    <td style={{ padding: "8px" }}><input type="number" value={cS} onChange={(e) => setCS(parseInt(e.target.value)||0)} style={{ ...inpStyle, width: "60px" }} /></td>
                    <td style={{ padding: "8px" }}></td><td style={{ padding: "8px" }}></td>
                    <td style={{ padding: "8px" }}><div style={{ display: "flex", gap: "6px" }}><button onClick={() => saveCatEdit(null)} style={checkBtn}>✓</button><button onClick={cancelCatEdit} style={crossBtn}>✕</button></div></td>
                  </tr>
                )}
                {catList.map((c) => {
                  const ic = editCatId === c.id;
                  return (
                    <tr key={c.id} style={{ borderBottom: "1px solid var(--line)", background: ic ? "#fffbeb" : "transparent" }}>
                      <td style={{ padding: "8px" }}>{ic ? <input type="text" value={cN} onChange={(e) => setCN(e.target.value)} style={inpStyle} /> : <span style={{ fontSize: "14px", fontWeight: 600 }}>{c.name}</span>}</td>
                                            <td style={{ padding: "8px" }}>{ic ? <input type="text" value={cD} onChange={(e) => setCD(e.target.value)} placeholder="选填" style={inpStyle} /> : <span style={{ fontSize: "13px", color: "var(--muted)" }}>{c.description || "-"}</span>}</td>
                      <td style={{ padding: "8px" }}>{ic ? <input type="number" value={cS} onChange={(e) => setCS(parseInt(e.target.value)||0)} style={{ ...inpStyle, width: "60px" }} /> : <span style={{ fontSize: "13px" }}>{c.sortOrder}</span>}</td>
                      <td style={{ padding: "8px" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: c.enabled ? "#f0fdf4" : "#fef2f2", color: c.enabled ? "var(--success)" : "var(--danger)", border: `1px solid ${c.enabled ? "#bbf7d0" : "#fecaca"}` }}>{c.enabled ? "启用" : "停用"}</span></td>
                      <td style={{ padding: "8px" }}>{c.isPreset ? <span className="partner-tag">预置</span> : <span className="partner-tag" style={{ background: "#f0f5ff", color: "#1a4fa0", border: "1px solid #d6e4ff" }}>自定义</span>}</td>
                      <td style={{ padding: "8px" }}>
                        {ic ? (
                          <div style={{ display: "flex", gap: "6px" }}><button onClick={() => saveCatEdit(c.id)} style={checkBtn}>✓</button><button onClick={cancelCatEdit} style={crossBtn}>✕</button></div>
                        ) : (
                          <div style={{ display: "flex", gap: "6px" }}><button onClick={() => startCatEdit(c)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>编辑</button><button onClick={() => toggleCatEnable(c)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>{c.enabled ? "停用" : "启用"}</button></div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}

      {subTab === "suggestions" && (
        <section className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <h2>AI 标签建议</h2>
            <button onClick={scanSuggestions} disabled={scanning} style={{ fontSize: "13px", padding: "6px 16px", opacity: scanning ? 0.6 : 1 }}>{scanning ? "扫描中..." : "扫描需求"}</button>
          </div>
          <p style={{ fontSize: "13px", color: "var(--muted)", marginTop: "4px" }}>基于项目需求识别标准能力标签未覆盖的新能力诉求，采纳后可上架为正式能力标签。</p>
          <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
            <input type="text" placeholder="搜索建议名称..." value={sugKeyword} onChange={(e) => setSugKeyword(e.target.value)} style={{ flex: "1 1 200px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
            <select value={sugStatus} onChange={(e) => setSugStatus(e.target.value)} style={{ padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }}><option value="">全部状态</option><option value="pending">待采纳</option><option value="adopted">已采纳</option></select>
          </div>
          {sugError && <p className="error-text">{sugError}</p>}
          {sugLoading ? <p style={{ marginTop: "12px" }}>加载中...</p> : sugList.length === 0 ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无标签建议。</p> : (
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "12px" }}>
              <thead><tr style={{ borderBottom: "1px solid var(--line)" }}>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>建议标签</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>分类</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>说明</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>次数</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>置信度</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>状态</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>操作</th>
              </tr></thead>
              <tbody>
                {sugList.map((s) => (
                  <tr key={s.id} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "10px 8px", fontSize: "14px", fontWeight: 600 }}>
                      {adoptingId === s.id ? <input type="text" value={adoptName} onChange={(e) => setAdoptName(e.target.value)} style={inpStyle} /> : s.suggestedName}
                    </td>
                    <td style={{ padding: "10px 8px", fontSize: "13px" }}>
                      {adoptingId === s.id ? <select value={adoptCat} onChange={(e) => setAdoptCat(e.target.value)} style={inpStyle}><option value="">使用建议分类</option>{categories.map(c => <option key={c} value={c}>{c}</option>)}</select> : s.suggestedCategoryName || "-"}
                    </td>
                    <td style={{ padding: "10px 8px", fontSize: "13px", color: "var(--muted)" }}>
                      {adoptingId === s.id ? <input type="text" value={adoptDesc} onChange={(e) => setAdoptDesc(e.target.value)} style={inpStyle} /> : (s.description || "-")}
                    </td>
                    <td style={{ padding: "10px 8px", fontSize: "13px" }}>{s.occurrenceCount}</td>
                    <td style={{ padding: "10px 8px", fontSize: "13px" }}>{(s.confidence * 100).toFixed(0)}%</td>
                    <td style={{ padding: "10px 8px" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: s.status === "adopted" ? "#f0fdf4" : "#fffbeb", color: s.status === "adopted" ? "var(--success)" : "#e8a317", border: `1px solid ${s.status === "adopted" ? "#bbf7d0" : "#fde68a"}` }}>{s.status === "adopted" ? "已采纳" : "待采纳"}</span></td>
                    <td style={{ padding: "10px 8px" }}>
                      {s.status === "pending" && (
                        adoptingId === s.id ? (
                          <div style={{ display: "flex", gap: "6px" }}><button onClick={() => confirmAdopt(s.id)} style={checkBtn}>✓</button><button onClick={cancelAdopt} style={crossBtn}>✕</button></div>
                        ) : (
                          <button onClick={() => startAdopt(s)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>采纳</button>
                        )
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {subTab === "tags" && (
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <h2>能力标签配置</h2>
          <button onClick={startNew} disabled={isEditing} style={{ fontSize: "13px", padding: "6px 16px", opacity: isEditing ? 0.5 : 1 }}>新增标签</button>
        </div>
        <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
          <input type="text" placeholder="搜索标签名称..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ flex: "1 1 200px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
          <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)} style={{ padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }}>
            <option value="">全部分类</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {error && <p className="error-text">{error}</p>}
        {loading ? <p style={{ marginTop: "12px" }}>加载中...</p> : (tags.length === 0 && !isNewRow) ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无标签数据。</p> : (
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
            <tbody>
              {isNewRow && (
                <tr style={{ borderBottom: "1px solid var(--line)", background: "#fffbeb" }}>
                  <td style={{ padding: "8px" }}><input type="text" value={eName} onChange={(e) => setEName(e.target.value)} placeholder="标签名称" style={inpStyle} autoFocus /></td>
                  <td style={{ padding: "8px" }}><select value={eCat} onChange={(e) => setECat(e.target.value)} style={inpStyle}>{categories.map(c => <option key={c} value={c}>{c}</option>)}</select></td>
                  <td style={{ padding: "8px" }}><input type="text" value={eDesc} onChange={(e) => setEDesc(e.target.value)} placeholder="选填" style={inpStyle} /></td>
                  <td style={{ padding: "8px" }}><input type="number" value={eSort} onChange={(e) => setESort(parseInt(e.target.value) || 0)} style={{ ...inpStyle, width: "60px" }} /></td>
                  <td style={{ padding: "8px" }}></td>
                  <td style={{ padding: "8px" }}></td>
                  <td style={{ padding: "8px" }}><div style={{ display: "flex", gap: "6px" }}>
                    <button onClick={() => saveEdit(null)} style={checkBtn}>✓</button>
                    <button onClick={cancelEdit} style={crossBtn}>✕</button>
                  </div></td>
                </tr>
              )}
              {tags.map((t) => {
                const isThisEditing = editingId === t.id;
                return (
                  <tr key={t.id} style={{ borderBottom: "1px solid var(--line)", background: isThisEditing ? "#fffbeb" : "transparent" }}>
                    <td style={{ padding: "8px" }}>
                      {isThisEditing ? <input type="text" value={eName} onChange={(e) => setEName(e.target.value)} style={inpStyle} /> : <span style={{ fontSize: "14px", fontWeight: 600 }}>{t.name}</span>}
                    </td>
                    <td style={{ padding: "8px" }}>
                      {isThisEditing ? <select value={eCat} onChange={(e) => setECat(e.target.value)} style={inpStyle}>{categories.map(c => <option key={c} value={c}>{c}</option>)}</select> : <span style={{ fontSize: "13px" }}>{t.category}</span>}
                    </td>
                    <td style={{ padding: "8px" }}>
                      {isThisEditing ? <input type="text" value={eDesc} onChange={(e) => setEDesc(e.target.value)} placeholder="选填" style={inpStyle} /> : <span style={{ fontSize: "13px", color: "var(--muted)" }}>{t.description || "-"}</span>}
                    </td>
                    <td style={{ padding: "8px" }}>
                      {isThisEditing ? <input type="number" value={eSort} onChange={(e) => setESort(parseInt(e.target.value) || 0)} style={{ ...inpStyle, width: "60px" }} /> : <span style={{ fontSize: "13px" }}>{t.sortOrder}</span>}
                    </td>
                    <td style={{ padding: "8px" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: t.enabled ? "#f0fdf4" : "#fef2f2", color: t.enabled ? "var(--success)" : "var(--danger)", border: `1px solid ${t.enabled ? "#bbf7d0" : "#fecaca"}` }}>{t.enabled ? "启用" : "停用"}</span></td>
                    <td style={{ padding: "8px" }}>{t.isPreset ? <span className="partner-tag">预置</span> : <span className="partner-tag" style={{ background: "#f0f5ff", color: "#1a4fa0", border: "1px solid #d6e4ff" }}>自定义</span>}</td>
                    <td style={{ padding: "8px" }}>
                      {isThisEditing ? (
                        <div style={{ display: "flex", gap: "6px" }}>
                          <button onClick={() => saveEdit(t.id)} style={checkBtn}>✓</button>
                          <button onClick={cancelEdit} style={crossBtn}>✕</button>
                        </div>
                      ) : (
                        <div style={{ display: "flex", gap: "6px" }}>
                          <button onClick={() => startEdit(t)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>编辑</button>
                          <button onClick={() => handleToggle(t)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>{t.enabled ? "停用" : "启用"}</button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
      )}
    </div>
  );
}


// ============ System Status Tab ============
function SystemStatusTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/system/status`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) { setError(e instanceof Error ? e.message : "状态加载失败"); } finally { setLoading(false); }
  }

  useEffect(() => { loadData(); }, []);

  function statusBadge(status: string) {
    const map: Record<string, { label: string; color: string; bg: string; border: string }> = {
      normal: { label: "正常", color: "var(--success)", bg: "#f0fdf4", border: "#bbf7d0" },
      warning: { label: "警告", color: "#e8a317", bg: "#fffbeb", border: "#fde68a" },
      error: { label: "异常", color: "var(--danger)", bg: "#fef2f2", border: "#fecaca" },
      unknown: { label: "未知", color: "var(--muted)", bg: "#f8f9fa", border: "var(--line)" },
    };
    const s = map[status] || map.unknown;
    return <span style={{ padding: "3px 10px", borderRadius: "999px", fontSize: "12px", fontWeight: 600, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{s.label}</span>;
  }

  function StatusCard({ title, items }: { title: string; items: any[] }) {
    return (
      <section className="card">
        <h2>{title}</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "12px" }}>
          {items.map((item, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
              <div>
                <span style={{ fontSize: "14px", fontWeight: 600 }}>{item.name}</span>
                <span style={{ fontSize: "13px", color: "var(--muted)", marginLeft: "8px" }}>{item.message}</span>
              </div>
              {statusBadge(item.status)}
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (loading) return <div><p>加载中...</p></div>;
  if (error) return <div><p className="error-text">{error}</p><button onClick={loadData} className="secondary-btn">重试</button></div>;
  if (!data) return <div><p className="placeholder-text">暂无状态数据。</p></div>;

  const overallMap: Record<string, { label: string; color: string }> = {
    normal: { label: "全部核心能力运行正常", color: "var(--success)" },
    partial: { label: `系统部分异常：${data.summary.abnormalModules.slice(0, 3).map((m: any) => m.module).join("、")}${data.summary.abnormalModules.length > 3 ? `等 ${data.summary.abnormalModules.length} 项` : ""}`, color: "#e8a317" },
    error: { label: "系统异常", color: "var(--danger)" },
    unknown: { label: "系统状态未知", color: "var(--muted)" },
  };
  const overall = overallMap[data.overallStatus] || overallMap.unknown;

  return (
    <div>
      {/* Overall status */}
      <section className="card" style={{ borderColor: overall.color }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <div>
            <h2 style={{ color: overall.color }}>{overall.label}</h2>
            <p style={{ fontSize: "13px", color: "var(--muted)", marginTop: "4px" }}>最后检查: {data.checkedAt.slice(0, 19).replace("T", " ")}</p>
          </div>
          <button onClick={loadData} className="secondary-btn">刷新状态</button>
        </div>
        {/* Stats */}
        <div style={{ display: "flex", gap: "16px", marginTop: "12px", flexWrap: "wrap" }}>
          <div style={{ padding: "8px 16px", background: "#f0fdf4", borderRadius: "8px", border: "1px solid #bbf7d0" }}><span style={{ fontSize: "20px", fontWeight: 700, color: "var(--success)" }}>{data.summary.normalCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>正常</span></div>
          <div style={{ padding: "8px 16px", background: "#fffbeb", borderRadius: "8px", border: "1px solid #fde68a" }}><span style={{ fontSize: "20px", fontWeight: 700, color: "#e8a317" }}>{data.summary.warningCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>警告</span></div>
          <div style={{ padding: "8px 16px", background: "#fef2f2", borderRadius: "8px", border: "1px solid #fecaca" }}><span style={{ fontSize: "20px", fontWeight: 700, color: "var(--danger)" }}>{data.summary.errorCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>异常</span></div>
          <div style={{ padding: "8px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}><span style={{ fontSize: "20px", fontWeight: 700, color: "var(--muted)" }}>{data.summary.unknownCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>未知</span></div>
        </div>
        {/* Abnormal modules */}
        {data.summary.abnormalModules.length > 0 && (
          <div style={{ marginTop: "12px" }}>
            <h3 style={{ fontSize: "14px", marginBottom: "8px" }}>异常详情</h3>
            {data.summary.abnormalModules.map((m: any, i: number) => (
              <div key={i} style={{ padding: "12px 16px", background: "#fef2f2", borderRadius: "8px", border: "1px solid #fecaca", marginBottom: "8px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                  <span style={{ fontSize: "14px", fontWeight: 600, color: "#991b1b" }}>{m.module}</span>
                  {statusBadge(m.status)}
                </div>
                <div style={{ fontSize: "13px", color: "#666" }}><strong>异常:</strong> {m.message}</div>
                <div style={{ fontSize: "13px", color: "#666", marginTop: "4px" }}><strong>影响范围:</strong> {m.impact}</div>
                <div style={{ fontSize: "13px", color: "#666", marginTop: "4px" }}><strong>处理建议:</strong> {m.suggestion}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      <StatusCard title="基础服务" items={data.services} />
      <StatusCard title="数据库" items={data.database} />
      <StatusCard title="LLM 模型" items={data.llm} />
      <StatusCard title="业务能力" items={data.businessCapabilities} />
    </div>
  );
}

// ============ Main Admin Page ============
export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<"users" | "tags" | "status">("users");

  return (
    <main className="page">
      <p className="eyebrow">System Administration</p>
      <h1>系统管理</h1>
      <p className="lead">维护用户、标签、字典等平台基础配置。</p>

      <div style={{ display: "flex", gap: "4px", marginBottom: "20px", borderBottom: "2px solid var(--line)" }}>
        <button onClick={() => setActiveTab("users")} style={{ padding: "10px 20px", fontSize: "14px", fontWeight: 600, border: "none", borderBottom: activeTab === "users" ? "2px solid var(--brand)" : "2px solid transparent", background: "transparent", color: activeTab === "users" ? "var(--brand)" : "var(--muted)", cursor: "pointer", marginBottom: "-2px" }}>用户管理</button>
        <button onClick={() => setActiveTab("tags")} style={{ padding: "10px 20px", fontSize: "14px", fontWeight: 600, border: "none", borderBottom: activeTab === "tags" ? "2px solid var(--brand)" : "2px solid transparent", background: "transparent", color: activeTab === "tags" ? "var(--brand)" : "var(--muted)", cursor: "pointer", marginBottom: "-2px" }}>能力标签配置</button>
        <button onClick={() => setActiveTab("status")} style={{ padding: "10px 20px", fontSize: "14px", fontWeight: 600, border: "none", borderBottom: activeTab === "status" ? "2px solid var(--brand)" : "2px solid transparent", background: "transparent", color: activeTab === "status" ? "var(--brand)" : "var(--muted)", cursor: "pointer", marginBottom: "-2px" }}>系统状态</button>
      </div>

      {activeTab === "users" ? <UsersTab /> : activeTab === "tags" ? <CapabilityTagsTab /> : <SystemStatusTab />}
    </main>
  );
}
