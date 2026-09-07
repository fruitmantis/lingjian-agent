"use client";

import { useState, useEffect } from "react";
import { fetchWithTimeout, responseError } from "../lib/api-request";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function fetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetchWithTimeout(input, { ...init, headers }).then(response => {
    if (response.status === 401) {
      localStorage.removeItem("token"); localStorage.removeItem("user"); window.location.assign("/login");
    }
    return response;
  });
}

// ============ Capability Tags Tab (inline edit) ============
type Tag = { id: string; name: string; category: string; description: string | null; enabled: boolean; sortOrder: number; isPreset: boolean; createdAt: string; updatedAt: string };

const DEFAULT_CATEGORIES = ["AI 与智能体", "云平台与迁移", "数据与数据库", "应用开发与现代化", "运维与安全", "咨询与项目管理", "其他"];

export function CapabilityTagsTab() {
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
      const res = await fetch(`${apiBaseUrl}/admin/capability-tags?${params}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTags(await res.json());
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); } finally { setLoading(false); }
  }

  useEffect(() => { loadTags(); }, [search, filterCategory]);

  async function loadCategories() {
    try {
      const res = await fetch(`${apiBaseUrl}/admin/capability-tags/categories?enabled=true`, { cache: "no-store" });
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
        const res = await fetch(`${apiBaseUrl}/admin/capability-tags/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body });
        if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      } else {
        const res = await fetch(`${apiBaseUrl}/admin/capability-tags`, { method: "POST", headers: { "Content-Type": "application/json" }, body });
        if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      }
      cancelEdit(); await loadTags();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
  }

  async function handleToggle(t: Tag) {
    try {
      const res = await fetch(`${apiBaseUrl}/admin/capability-tags/${t.id}/enable`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !t.enabled }) });
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
      const r = await fetch(`${apiBaseUrl}/admin/capability-tags/categories?${p}`, { cache: "no-store" });
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
      const url = id ? `${apiBaseUrl}/admin/capability-tags/categories/${id}` : `${apiBaseUrl}/admin/capability-tags/categories`;
      const method = id ? "PUT" : "POST";
      const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body });
      if (!r.ok) { const ed = await r.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${r.status}`); }
      cancelCatEdit(); await loadCatList(); await loadCategories();
    } catch (e) { setCatError(e instanceof Error ? e.message : "保存失败"); }
  }
  async function toggleCatEnable(c: any) {
    try { const r = await fetch(`${apiBaseUrl}/admin/capability-tags/categories/${c.id}/enable`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !c.enabled }) }); if (!r.ok) throw new Error(`HTTP ${r.status}`); await loadCatList(); await loadCategories(); }
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
      const r = await fetch(`${apiBaseUrl}/admin/capability-tags/suggestions?${p}`, { cache: "no-store" });
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
      const r = await fetch(`${apiBaseUrl}/admin/capability-tags/suggestions/${id}/adopt`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: adoptName, categoryId: adoptCat || null, description: adoptDesc || null, sortOrder: adoptSort }) });
      if (!r.ok) { const ed = await r.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${r.status}`); }
      cancelAdopt(); await loadSugList(); await loadCategories();
    } catch (e) { setSugError(e instanceof Error ? e.message : "采纳失败"); }
  }
  async function scanSuggestions() {
    setScanning(true); setSugError(null);
    try {
      const r = await fetch(`${apiBaseUrl}/admin/capability-tags/suggestions/scan`, { method: "POST" });
      if (!r.ok) throw await responseError(r, "扫描失败");
      const d = await r.json();
      await loadSugList();
      setSugError(d.created > 0 ? `扫描完成，新增 ${d.created} 条建议` : "扫描完成，未发现新建议");
    } catch (e) { setSugError(e instanceof Error ? e.message : "扫描失败"); } finally { setScanning(false); }
  }

  const isCatEditing = editCatId !== null || isNewCat;
  const inpStyle = { padding: "4px 8px", border: "1px solid var(--brand)", borderRadius: "4px", fontSize: "13px", width: "100%", boxSizing: "border-box" as const };
  const checkBtn = { fontSize: "16px", padding: "2px 10px", background: "var(--success)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", lineHeight: 1 };
  const crossBtn = { fontSize: "16px", padding: "2px 10px", background: "var(--danger)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", lineHeight: 1 };

  return (
    <div>
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
        <button onClick={() => setSubTab("tags")} className="secondary-btn" style={{ fontSize: "13px", padding: "6px 14px", fontWeight: subTab === "tags" ? 700 : 400, color: subTab === "tags" ? "var(--brand)" : "var(--muted)", borderColor: subTab === "tags" ? "var(--brand-border)" : "var(--line)", background: subTab === "tags" ? "var(--brand-soft)" : "var(--surface)" }}>能力标签</button>
        <button onClick={() => setSubTab("categories")} className="secondary-btn" style={{ fontSize: "13px", padding: "6px 14px", fontWeight: subTab === "categories" ? 700 : 400, color: subTab === "categories" ? "var(--brand)" : "var(--muted)", borderColor: subTab === "categories" ? "var(--brand-border)" : "var(--line)", background: subTab === "categories" ? "var(--brand-soft)" : "var(--surface)" }}>标签分类</button>
        <button onClick={() => setSubTab("suggestions")} className="secondary-btn" style={{ fontSize: "13px", padding: "6px 14px", fontWeight: subTab === "suggestions" ? 700 : 400, color: subTab === "suggestions" ? "var(--brand)" : "var(--muted)", borderColor: subTab === "suggestions" ? "var(--brand-border)" : "var(--line)", background: subTab === "suggestions" ? "var(--brand-soft)" : "var(--surface)" }}>AI 标签建议</button>
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
                      <td style={{ padding: "8px" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: !c.enabled ? "#fef2f2" : !c.apiKeyConfigured ? "#fffbeb" : "#f0fdf4", color: !c.enabled ? "var(--danger)" : !c.apiKeyConfigured ? "#e8a317" : "var(--success)", border: `1px solid ${c.enabled ? "#bbf7d0" : "#fecaca"}` }}>{!c.enabled ? "停用" : !c.apiKeyConfigured ? "配置不完整" : "启用"}</span></td>
                      <td style={{ padding: "8px" }}>{c.isPreset ? <span className="partner-tag">预置</span> : <span className="partner-tag" style={{ background: "var(--brand-soft)", color: "var(--brand-dark)", border: "1px solid var(--brand-border)" }}>自定义</span>}</td>
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
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>建议标签</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>分类</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>说明</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>次数</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>置信度</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>状态</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>操作</th>
              </tr></thead>
              <tbody>
                {sugList.map((s) => (
                  <tr key={s.id} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "10px 8px", fontSize: "14px", fontWeight: 600, whiteSpace: "nowrap" }}>
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
                    <td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: s.status === "adopted" ? "#f0fdf4" : "#fffbeb", color: s.status === "adopted" ? "var(--success)" : "#e8a317", border: `1px solid ${s.status === "adopted" ? "#bbf7d0" : "#fde68a"}`, whiteSpace: "nowrap" }}>{s.status === "adopted" ? "已采纳" : "待采纳"}</span></td>
                    <td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
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
          <h2>能力标签</h2>
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
                    <td style={{ padding: "8px" }}>{t.isPreset ? <span className="partner-tag">预置</span> : <span className="partner-tag" style={{ background: "var(--brand-soft)", color: "var(--brand-dark)", border: "1px solid var(--brand-border)" }}>自定义</span>}</td>
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
export function SystemStatusTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/admin/system/status`, { cache: "no-store" });
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
      unknown: { label: "未知", color: "var(--muted)", bg: "var(--bg-hover)", border: "var(--line)" },
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
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: "var(--bg-hover)", borderRadius: "8px", border: "1px solid var(--line)" }}>
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
    normal: { label: "本次检查未发现异常", color: "var(--success)" },
    partial: { label: `系统部分异常：${data.summary.abnormalModules.slice(0, 3).map((m: any) => m.module).join("、")}${data.summary.abnormalModules.length > 3 ? `等 ${data.summary.abnormalModules.length} 项` : ""}`, color: "#e8a317" },
    error: { label: "系统异常", color: "var(--danger)" },
    unknown: { label: "部分运行状态尚未验证", color: "var(--muted)" },
  };
  const overall = overallMap[data.overallStatus] || overallMap.unknown;

  return (
    <div>
      {/* Overall status */}
      <p className="placeholder-text" style={{ marginBottom: "16px" }}>本页仅执行只读查询和配置检查，不测试数据库写入，也不发送模型请求。需要验证模型连接时，请前往<a href="/admin/models">模型配置</a>手动测试。</p>
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
          <div style={{ padding: "8px 16px", background: "var(--bg-hover)", borderRadius: "8px", border: "1px solid var(--line)" }}><span style={{ fontSize: "20px", fontWeight: 700, color: "var(--muted)" }}>{data.summary.unknownCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>未知</span></div>
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


// ============ Model Config Tab ============
export function ModelConfigTab() {
  const [configs, setConfigs] = useState<any[]>([]);
  const [usages, setUsages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [eName, setEName] = useState(""); const [eProvider, setEProvider] = useState("OpenAI Compatible");
  const [eUrl, setEUrl] = useState(""); const [eKey, setEKey] = useState(""); const [eModel, setEModel] = useState("");
  const [eTemp, setETemp] = useState(0.3); const [eMaxTokens, setEMaxTokens] = useState(131072);
  const [eTimeout, setETimeout] = useState(60); const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function loadData() {
    setLoading(true); setError(null);
    try {
      const [r1, r2] = await Promise.all([
        fetch(`${apiBaseUrl}/admin/model-configs`, { cache: "no-store" }),
        fetch(`${apiBaseUrl}/admin/model-configs/usage`, { cache: "no-store" })
      ]);
      if (!r1.ok || !r2.ok) throw new Error("模型配置加载失败");
      setConfigs(await r1.json()); setUsages(await r2.json());
    } catch (e) { setError(e instanceof Error ? e.message : "模型配置加载失败"); } finally { setLoading(false); }
  }
  useEffect(() => { loadData(); }, []);

  function startEdit(c: any) { setEditingId(c.id); setIsNew(false); setEName(c.name); setEProvider(c.provider||""); setEUrl(c.baseUrl||""); setEKey(""); setEModel(c.modelName||""); setETemp(c.temperature); setEMaxTokens(c.maxTokens); setETimeout(c.timeoutSeconds); }
  function startNew() { setIsNew(true); setEditingId(null); setEName(""); setEProvider("OpenAI Compatible"); setEUrl(""); setEKey(""); setEModel(""); setETemp(0.3); setEMaxTokens(131072); setETimeout(60); }
  function cancelEdit() { setEditingId(null); setIsNew(false); }

  async function saveEdit(id: string | null) {
    if (saving) return;
    setSaving(true); setError(null);
    try {
      const body = JSON.stringify({ name: eName, provider: eProvider, baseUrl: eUrl || undefined, apiKey: eKey || undefined, modelName: eModel || undefined, temperature: eTemp, maxTokens: eMaxTokens, timeoutSeconds: eTimeout });
      const url = id ? `${apiBaseUrl}/admin/model-configs/${id}` : `${apiBaseUrl}/admin/model-configs`;
      const method = id ? "PUT" : "POST";
      const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body });
      if (!r.ok) throw await responseError(r, "保存失败");
      cancelEdit(); await loadData();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); } finally { setSaving(false); }
  }

  async function toggleEnable(c: any) {
    await saveConfigAction(() => fetch(`${apiBaseUrl}/admin/model-configs/${c.id}/enable?enabled=${!c.enabled}`, { method: "PATCH" }));
  }
  async function setDefault(c: any) {
    await saveConfigAction(() => fetch(`${apiBaseUrl}/admin/model-configs/${c.id}/default`, { method: "PATCH" }));
  }
  async function testConn(c: any) {
    setTesting(c.id); setTestResult(null);
    try {
      const r = await fetch(`${apiBaseUrl}/admin/model-configs/${c.id}/test`, { method: "POST" });
      if (!r.ok) throw await responseError(r, "连接测试失败");
      const d = await r.json();
      setTestResult(d.success ? `连接成功（${d.latencyMs}ms）` : `失败: ${d.message}`);
    } catch (e) { setTestResult(e instanceof Error ? e.message : "测试失败"); } finally { setTesting(null); }
  }
  async function updateUsage(scene: string, configId: string) {
    await saveConfigAction(() => fetch(`${apiBaseUrl}/admin/model-configs/usage/${scene}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ modelConfigId: configId || null }) }));
  }

  async function saveConfigAction(action: () => Promise<Response>) {
    if (saving) return;
    setSaving(true); setError(null);
    try {
      const response = await action();
      if (!response.ok) throw await responseError(response);
      await loadData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "配置保存失败");
    } finally {
      setSaving(false);
    }
  }

  const inp = { padding: "4px 8px", border: "1px solid var(--brand)", borderRadius: "4px", fontSize: "13px", width: "100%", boxSizing: "border-box" as const };

  if (loading) return <div><p>加载中...</p></div>;

  return (
    <div>
      {error && <div className="inline-error-actions"><p className="error-text" role="alert">{error}</p><button onClick={loadData} className="secondary-btn">重试</button></div>}
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <h2>模型配置</h2>
          <button onClick={startNew} disabled={saving || Boolean(editingId) || isNew} style={{ fontSize: "13px", padding: "6px 16px", opacity: Boolean(editingId) || isNew ? 0.5 : 1 }}>新增配置</button>
        </div>
        {testResult && <p style={{ fontSize: "13px", color: "var(--brand)", marginTop: "8px" }}>{testResult}</p>}
        {configs.length === 0 && !isNew ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无模型配置。</p> : (
          <div className="table-wrap"><table style={{ width: "100%", borderCollapse: "collapse", marginTop: "12px" }}>
            <thead><tr style={{ borderBottom: "1px solid var(--line)" }}>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>名称</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>供应商</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>模型</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>最大输出</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>API 地址</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>API Key</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>状态</th>
              <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>操作</th>
            </tr></thead>
            <tbody>
              {isNew && (
                <tr style={{ borderBottom: "1px solid var(--line)", background: "#fffbeb" }}>
                  <td style={{ padding: "8px" }}><input type="text" value={eName} onChange={(e) => setEName(e.target.value)} placeholder="配置名称" style={inp} autoFocus /></td>
                  <td style={{ padding: "8px" }}><input type="text" value={eProvider} onChange={(e) => setEProvider(e.target.value)} style={inp} /></td>
                  <td style={{ padding: "8px" }}><input type="text" value={eModel} onChange={(e) => setEModel(e.target.value)} placeholder="模型名称" style={inp} /></td>
                  <td style={{ padding: "8px" }}><input type="number" min={1} step={1} value={eMaxTokens} onChange={(e) => setEMaxTokens(Number(e.target.value))} style={{ ...inp, width: "96px" }} /></td>
                  <td style={{ padding: "8px" }}><input type="text" value={eUrl} onChange={(e) => setEUrl(e.target.value)} placeholder="https://xxx/v1" style={inp} /></td>
                  <td style={{ padding: "8px" }}><input type="password" value={eKey} onChange={(e) => setEKey(e.target.value)} placeholder="输入新Key" style={inp} /></td>
                  <td style={{ padding: "8px" }}></td>
                  <td style={{ padding: "8px", whiteSpace: "nowrap" }}><div style={{ display: "flex", gap: "6px" }}><button disabled={saving} onClick={() => saveEdit(null)} style={{ fontSize: "14px", padding: "2px 10px", background: "var(--success)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}>✓</button><button disabled={saving} onClick={cancelEdit} style={{ fontSize: "14px", padding: "2px 10px", background: "var(--danger)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}>✕</button></div></td>
                </tr>
              )}
              {configs.map((c) => {
                const ic = editingId === c.id;
                return (
                  <tr key={c.id} style={{ borderBottom: "1px solid var(--line)", background: ic ? "#fffbeb" : "transparent" }}>
                    <td style={{ padding: "8px", fontSize: "14px", fontWeight: 600, whiteSpace: "nowrap" }}>{ic ? <input type="text" value={eName} onChange={(e) => setEName(e.target.value)} style={inp} /> : <span>{c.name}{c.isDefault ? <span className="tag-red" style={{ marginLeft: "6px" }}>默认</span> : null}</span>}</td>
                    <td style={{ padding: "8px", fontSize: "13px" }}>{ic ? <input type="text" value={eProvider} onChange={(e) => setEProvider(e.target.value)} style={inp} /> : c.provider}</td>
                    <td style={{ padding: "8px", fontSize: "13px" }}>{ic ? <input type="text" value={eModel} onChange={(e) => setEModel(e.target.value)} style={inp} /> : c.modelName}</td>
                    <td style={{ padding: "8px", fontSize: "13px", whiteSpace: "nowrap" }}>{ic ? <input type="number" min={1} step={1} value={eMaxTokens} onChange={(e) => setEMaxTokens(Number(e.target.value))} style={{ ...inp, width: "96px" }} /> : c.maxTokens.toLocaleString()}</td>
                    <td style={{ padding: "8px", fontSize: "12px", color: "var(--muted)" }}>{ic ? <input type="text" value={eUrl} onChange={(e) => setEUrl(e.target.value)} placeholder="https://xxx/v1" style={inp} /> : (c.baseUrl ? c.baseUrl.replace(/https?:\/\//, "").split("/")[0] : "-")}</td>
                    <td style={{ padding: "8px" }}>{ic ? <input type="password" value={eKey} onChange={(e) => setEKey(e.target.value)} placeholder="留空保留原Key" style={inp} /> : <span style={{ fontSize: "12px", color: c.apiKeyConfigured ? "var(--success)" : "var(--danger)" }}>{c.apiKeyConfigured ? "已配置" : "未配置"}</span>}</td>
                    <td style={{ padding: "8px" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: !c.enabled ? "#fef2f2" : !c.apiKeyConfigured ? "#fffbeb" : "#f0fdf4", color: !c.enabled ? "var(--danger)" : !c.apiKeyConfigured ? "#e8a317" : "var(--success)", border: `1px solid ${c.enabled ? "#bbf7d0" : "#fecaca"}`, whiteSpace: "nowrap" }}>{!c.enabled ? "停用" : !c.apiKeyConfigured ? "配置不完整" : "启用"}</span></td>
                    <td style={{ padding: "8px", whiteSpace: "nowrap" }}>
                      {ic ? (
                        <div style={{ display: "flex", gap: "6px" }}><button disabled={saving} onClick={() => saveEdit(c.id)} style={{ fontSize: "14px", padding: "2px 10px", background: "var(--success)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}>✓</button><button disabled={saving} onClick={cancelEdit} style={{ fontSize: "14px", padding: "2px 10px", background: "var(--danger)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}>✕</button></div>
                      ) : (
                        <div style={{ display: "flex", gap: "4px" }}>
                          <button onClick={() => startEdit(c)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>编辑</button>
                          <button onClick={() => testConn(c)} disabled={testing === c.id} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>{testing === c.id ? "测试中" : "测试"}</button>
                          <button disabled={saving} onClick={() => toggleEnable(c)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>{c.enabled ? "停用" : "启用"}</button>
                          {!c.isDefault && c.enabled && <button disabled={saving} onClick={() => setDefault(c)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>设默认</button>}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table></div>
        )}
      </section>

      <section className="card">
        <h2>业务场景模型配置</h2>
        <p className="placeholder-text">未绑定时依次使用默认场景、启用的默认模型、首个启用模型或环境变量配置。显式绑定的模型不可用时会报错。</p>
        <div style={{ marginTop: "12px" }}>
          {usages.map((u) => (
            <div key={u.sceneKey} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: "var(--bg-hover)", borderRadius: "8px", border: "1px solid var(--line)", marginBottom: "8px" }}>
              <div><span style={{ fontSize: "14px", fontWeight: 600 }}>{u.sceneName}</span><span style={{ fontSize: "12px", color: "var(--muted)", marginLeft: "8px" }}>{u.modelConfigName || "使用默认配置"}</span></div>
              {u.sceneKey === "recommendation_summary" && <span className="placeholder-text">当前暂无独立调用，推荐理由随伙伴匹配生成。</span>}
              <select aria-label={`${u.sceneName}模型`} disabled={saving} value={u.modelConfigId || ""} onChange={(e) => updateUsage(u.sceneKey, e.target.value)} style={{ padding: "6px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "13px" }}>
                <option value="">使用默认配置</option>
                {u.modelConfigId && !configs.some(c => c.id === u.modelConfigId && c.enabled) && <option value={u.modelConfigId} disabled>{u.modelConfigName || "原绑定模型"}（不可用，请重新选择）</option>}
                {configs.filter(c => c.enabled).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ============ Main Admin Page ============
export default function AdminPage() {
  const [data, setData] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);
  function loadData() {
    setError(null);
    fetch(`${apiBaseUrl}/admin/dashboard`, { cache: "no-store" })
      .then(async response => { if (!response.ok) throw new Error("概览加载失败"); setData(await response.json()); })
      .catch(reason => setError(reason instanceof Error ? reason.message : "概览加载失败"));
  }
  useEffect(() => { loadData(); }, []);
  const cards = [
    ["内部用户", "users"], ["待审批账号", "pendingUserApplications"], ["停用用户", "disabledUsers"], ["启用伙伴", "partners"],
    ["待完善画像", "partnersWithoutProfile"], ["累计任务", "tasks"], ["本月任务", "monthTasks"],
    ["项目机会", "opportunities"], ["供给不足", "gapDemands"], ["待采纳建议", "pendingSuggestions"],
  ];

  return (
    <main className="page">
      <p className="eyebrow">Administration</p><h1>后台概览</h1><p className="lead">查看平台用户、伙伴、任务和运营待办。</p>
      {error && <div className="inline-error-actions"><p className="error-text">{error}</p><button className="secondary-btn" onClick={loadData}>重试</button></div>}
      <section className="admin-metric-grid">{cards.map(([label, key]) => <div className="card admin-metric-card" key={key}><span>{label}</span><strong>{data ? data[key] ?? 0 : "--"}</strong></div>)}</section>
      <section className="card"><h2>管理重点</h2><div className="admin-shortcuts"><a href="/admin/users?tab=applications">审批账号申请</a><a href="/admin/partners">完善伙伴资料</a><a href="/admin/tasks">查看全量任务</a><a href="/admin/tags">处理标签建议</a></div></section>
    </main>
  );
}
