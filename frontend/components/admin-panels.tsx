"use client";
import { adminApiFetch } from "./auth-provider";
import { ModelConfiguration } from "./model-connections";

import { useState, useEffect, Fragment } from "react";
import { responseError } from "../lib/api-request";
import type { CapabilityCategoryNode, CapabilityL1Tag, CapabilityL2Tag } from "./partner-capability-fields";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

function fetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const path = String(input).slice(apiBaseUrl.length);
  return adminApiFetch(path, init);
}

// ============ Capability Tags Tab (three-tier tree edit) ============
type Tag = {
  id: string;
  name: string;
  category: string;
  level?: number;
  parentId?: string | null;
  parentName?: string | null;
  description: string | null;
  enabled: boolean;
  sortOrder: number;
  isPreset: boolean;
  createdAt: string;
  updatedAt: string;
};

const DEFAULT_CATEGORIES = ["产品技术能力", "场景化能力"];

function buildFallbackTree(tags: Tag[], catNames: string[]): CapabilityCategoryNode[] {
  const l1Map = new Map<string, CapabilityL1Tag>();
  const orderedCats = [...new Set([...catNames, ...tags.map((t) => t.category)])];
  for (const tag of tags) {
    if ((tag.level ?? 1) === 1) {
      l1Map.set(tag.id, {
        id: tag.id,
        name: tag.name,
        category: tag.category,
        description: tag.description,
        enabled: tag.enabled,
        sortOrder: tag.sortOrder,
        isPreset: tag.isPreset,
        level: 1,
        children: [],
      });
    }
  }
  for (const tag of tags) {
    if (tag.level === 2 && tag.parentId && l1Map.has(tag.parentId)) {
      const parent = l1Map.get(tag.parentId)!;
      parent.children.push({
        id: tag.id,
        name: tag.name,
        category: tag.category,
        parentId: tag.parentId,
        parentName: parent.name,
        description: tag.description,
        enabled: tag.enabled,
        sortOrder: tag.sortOrder,
        isPreset: tag.isPreset,
        level: 2,
      });
    }
  }
  return orderedCats.map((name, idx) => ({
    id: name,
    name,
    code: null,
    description: null,
    enabled: true,
    sortOrder: idx + 1,
    isPreset: true,
    tags: Array.from(l1Map.values()).filter((t) => t.category === name),
  }));
}

export function CapabilityTagsTab() {
  const [tree, setTree] = useState<CapabilityCategoryNode[]>([]);
  const [categories, setCategories] = useState<string[]>(DEFAULT_CATEGORIES);
  const [subTab, setSubTab] = useState<"tags" | "categories" | "suggestions">("tags");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingLevel, setEditingLevel] = useState<1 | 2>(1);
  const [isNewRow, setIsNewRow] = useState(false);
  const [newParentId, setNewParentId] = useState<string | null>(null);
  const [eName, setEName] = useState("");
  const [eCat, setECat] = useState("场景化能力");
  const [eParentId, setEParentId] = useState("");
  const [eDesc, setEDesc] = useState("");
  const [eSort, setESort] = useState(0);

  async function loadTags() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/admin/capability-tags/tree`, { cache: "no-store" });
      if (res.ok) {
        const data: CapabilityCategoryNode[] = await res.json();
        setTree(data);
        return;
      }
      const [tagsRes, catsRes] = await Promise.all([
        fetch(`${apiBaseUrl}/admin/capability-tags`, { cache: "no-store" }),
        fetch(`${apiBaseUrl}/admin/capability-tags/categories?enabled=true`, { cache: "no-store" }),
      ]);
      if (!tagsRes.ok) throw new Error(`HTTP ${tagsRes.status}`);
      const flatTags: Tag[] = await tagsRes.json();
      const catNames: string[] = catsRes.ok ? (await catsRes.json()).map((c: any) => c.name) : DEFAULT_CATEGORIES;
      setTree(buildFallbackTree(flatTags, catNames));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTags();
  }, []);

  async function loadCategories() {
    try {
      const res = await fetch(`${apiBaseUrl}/admin/capability-tags/categories?enabled=true`, { cache: "no-store" });
      if (res.ok) {
        const names = (await res.json()).map((c: any) => c.name);
        if (names.length) setCategories(names);
      }
    } catch {}
  }
  useEffect(() => {
    void loadCategories();
  }, []);

  const allL1Tags = tree.flatMap((cat) => cat.tags);

  function startEditL1(t: CapabilityL1Tag) {
    setEditingId(t.id);
    setEditingLevel(1);
    setIsNewRow(false);
    setNewParentId(null);
    setEName(t.name);
    setECat(t.category);
    setEParentId("");
    setEDesc(t.description || "");
    setESort(t.sortOrder);
  }

  function startEditL2(child: CapabilityL2Tag) {
    setEditingId(child.id);
    setEditingLevel(2);
    setIsNewRow(false);
    setNewParentId(null);
    setEName(child.name);
    setECat(child.category);
    setEParentId(child.parentId);
    setEDesc(child.description || "");
    setESort(child.sortOrder);
  }

  function startNewL1() {
    setIsNewRow(true);
    setEditingId(null);
    setEditingLevel(1);
    setNewParentId(null);
    setEName("");
    setECat(categories[0] || "场景化能力");
    setEParentId("");
    setEDesc("");
    setESort(0);
  }

  function startNewL2(parent: CapabilityL1Tag) {
    setIsNewRow(true);
    setEditingId(null);
    setEditingLevel(2);
    setNewParentId(parent.id);
    setExpandedIds((prev) => ({ ...prev, [parent.id]: true }));
    setEName("");
    setECat(parent.category);
    setEParentId(parent.id);
    setEDesc("");
    setESort(parent.children.length + 1);
  }

  function cancelEdit() {
    setEditingId(null);
    setIsNewRow(false);
    setNewParentId(null);
  }

  async function saveEdit(id: string | null) {
    setError(null);
    try {
      if (id) {
        const payload =
          editingLevel === 1
            ? { name: eName, category: eCat, description: eDesc || null, sortOrder: eSort }
            : { name: eName, parentId: eParentId, description: eDesc || null, sortOrder: eSort };
        const res = await fetch(`${apiBaseUrl}/admin/capability-tags/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const ed = await res.json().catch(() => ({}));
          throw new Error(ed.detail || `HTTP ${res.status}`);
        }
      } else {
        const payload = newParentId
          ? { name: eName, level: 2, parentId: newParentId, description: eDesc || null, sortOrder: eSort }
          : { name: eName, level: 1, category: eCat, description: eDesc || null, sortOrder: eSort };
        const res = await fetch(`${apiBaseUrl}/admin/capability-tags`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const ed = await res.json().catch(() => ({}));
          throw new Error(ed.detail || `HTTP ${res.status}`);
        }
      }
      cancelEdit();
      await loadTags();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    }
  }

  async function handleToggle(t: { id: string; enabled: boolean }) {
    try {
      const res = await fetch(`${apiBaseUrl}/admin/capability-tags/${t.id}/enable`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !t.enabled }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadTags();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    }
  }

  function toggleExpandAll(open: boolean) {
    const next: Record<string, boolean> = {};
    for (const l1 of allL1Tags) next[l1.id] = open;
    setExpandedIds(next);
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
      cancelCatEdit(); await loadCatList(); await loadCategories(); await loadTags();
    } catch (e) { setCatError(e instanceof Error ? e.message : "保存失败"); }
  }
  async function toggleCatEnable(c: any) {
    try { const r = await fetch(`${apiBaseUrl}/admin/capability-tags/categories/${c.id}/enable`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !c.enabled }) }); if (!r.ok) throw new Error(`HTTP ${r.status}`); await loadCatList(); await loadCategories(); await loadTags(); }
    catch (e) { setCatError(e instanceof Error ? e.message : "操作失败"); }
  }

  // Suggestion tab state
  const [sugList, setSugList] = useState<any[]>([]);
  const [sugLoading, setSugLoading] = useState(false);
  const [sugError, setSugError] = useState<string | null>(null);
  const [sugStatus, setSugStatus] = useState("");
  const [sugKeyword, setSugKeyword] = useState("");
  const [adoptingId, setAdoptingId] = useState<string | null>(null);
  const [adoptName, setAdoptName] = useState("");
  const [adoptLevel, setAdoptLevel] = useState<1 | 2>(1);
  const [adoptCat, setAdoptCat] = useState("");
  const [adoptParentId, setAdoptParentId] = useState("");
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
      const data = await r.json();
      setSugList(Array.isArray(data) ? data : (data.items || []));
    } catch (e) { setSugError(e instanceof Error ? e.message : "加载失败"); } finally { setSugLoading(false); }
  }
  useEffect(() => { if (subTab === "suggestions") loadSugList(); }, [subTab, sugStatus, sugKeyword]);

  function startAdopt(s: any) {
    setAdoptingId(s.id);
    setAdoptName(s.suggestedName);
    setAdoptLevel(1);
    setAdoptCat("");
    setAdoptParentId(allL1Tags[0]?.id || "");
    setAdoptDesc(s.description || "");
    setAdoptSort(0);
  }
  function cancelAdopt() { setAdoptingId(null); }
  async function confirmAdopt(id: string) {
    setSugError(null);
    try {
      const payload =
        adoptLevel === 2
          ? { name: adoptName, level: 2, parentId: adoptParentId || null, description: adoptDesc || null, sortOrder: adoptSort }
          : { name: adoptName, level: 1, categoryId: adoptCat || null, description: adoptDesc || null, sortOrder: adoptSort };
      const r = await fetch(`${apiBaseUrl}/admin/capability-tags/suggestions/${id}/adopt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) { const ed = await r.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${r.status}`); }
      cancelAdopt(); await loadSugList(); await loadCategories(); await loadTags();
    } catch (e) { setSugError(e instanceof Error ? e.message : "采纳失败"); }
  }

  const isCatEditing = editCatId !== null || isNewCat;
  const inpStyle = { width: "100%", boxSizing: "border-box" as const };

  const query = search.trim().toLowerCase();
  const visibleTree = tree
    .filter((cat) => !filterCategory || cat.name === filterCategory)
    .map((cat) => {
      const tags = cat.tags
        .map((l1) => {
          if (!query) return l1;
          const l1Match = l1.name.toLowerCase().includes(query);
          const matchingChildren = l1.children.filter((c) => c.name.toLowerCase().includes(query));
          if (l1Match) return l1;
          if (matchingChildren.length > 0) return { ...l1, children: matchingChildren };
          return null;
        })
        .filter((x): x is CapabilityL1Tag => x !== null);
      return { ...cat, tags };
    })
    .filter((cat) => cat.tags.length > 0 || (!query && !filterCategory));

  return (
    <div>
      <div className="page-tabs">
        <button onClick={() => setSubTab("tags")} className={subTab === "tags" ? "active" : ""}>能力标签</button>
        <button onClick={() => setSubTab("categories")} className={subTab === "categories" ? "active" : ""}>顶层分类</button>
        <button onClick={() => setSubTab("suggestions")} className={subTab === "suggestions" ? "active" : ""}>AI 标签建议</button>
      </div>
      {subTab === "categories" && (
        <section className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <h2>顶层分类配置</h2>
            <button onClick={startNewCat} disabled={isCatEditing} style={{ opacity: isCatEditing ? 0.5 : 1 }}>新增分类</button>
          </div>
          <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
            <input type="text" placeholder="搜索分类名称..." value={catSearch} onChange={(e) => setCatSearch(e.target.value)} style={{ flex: "1 1 200px" }} />
            <select value={catFilterEnabled} onChange={(e) => setCatFilterEnabled(e.target.value)} ><option value="">全部状态</option><option value="true">启用</option><option value="false">停用</option></select>
          </div>
          {catError && <p className="error-text">{catError}</p>}
          {catLoading ? <p style={{ marginTop: "12px" }}>加载中...</p> : (catList.length === 0 && !isNewCat) ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无分类数据。</p> : (
            <div className="table-wrap"><table className="data-table" style={{ marginTop: "12px" }}>
              <thead><tr style={{ borderBottom: "1px solid var(--line)" }}>
                <th style={{ textAlign: "left" }}>分类名称</th>
                <th style={{ textAlign: "left" }}>说明</th>
                <th style={{ textAlign: "left" }}>排序</th>
                <th style={{ textAlign: "left" }}>状态</th>
                <th style={{ textAlign: "left" }}>类型</th>
                <th style={{ textAlign: "left" }}>操作</th>
              </tr></thead>
              <tbody>
                {isNewCat && (
                  <tr style={{ borderBottom: "1px solid var(--line)", background: "var(--bg-hover)" }}>
                    <td ><input type="text" value={cN} onChange={(e) => setCN(e.target.value)} placeholder="分类名称" style={inpStyle} autoFocus /></td>
                    <td ><input type="text" value={cD} onChange={(e) => setCD(e.target.value)} placeholder="选填" style={inpStyle} /></td>
                    <td ><input type="number" value={cS} onChange={(e) => setCS(parseInt(e.target.value)||0)} style={{ ...inpStyle, width: "60px" }} /></td>
                    <td ></td><td ></td>
                    <td ><div style={{ display: "flex", gap: "6px" }}><button onClick={() => saveCatEdit(null)} className="table-save" aria-label="保存">✓</button><button onClick={cancelCatEdit} className="table-cancel" aria-label="取消">✕</button></div></td>
                  </tr>
                )}
                {catList.map((c) => {
                  const ic = editCatId === c.id;
                  return (
                    <tr key={c.id} style={{ borderBottom: "1px solid var(--line)", background: ic ? "var(--bg-hover)" : undefined }}>
                      <td >{ic ? <input type="text" value={cN} onChange={(e) => setCN(e.target.value)} style={inpStyle} /> : <span style={{ fontSize: "14px", fontWeight: 400 }}>{c.name}</span>}</td>
                      <td >{ic ? <input type="text" value={cD} onChange={(e) => setCD(e.target.value)} placeholder="选填" style={inpStyle} /> : <span style={{ fontSize: "13px", color: "var(--muted)" }}>{c.description || "-"}</span>}</td>
                      <td >{ic ? <input type="number" value={cS} onChange={(e) => setCS(parseInt(e.target.value)||0)} style={{ ...inpStyle, width: "60px" }} /> : <span style={{ fontSize: "13px" }}>{c.sortOrder}</span>}</td>
                      <td ><span className="ui-status-badge" style={{ background: c.enabled ? "#f0fdf4" : "#fef2f2", color: c.enabled ? "var(--success)" : "var(--danger)", border: `1px solid ${c.enabled ? "#bbf7d0" : "#fecaca"}` }}>{c.enabled ? "启用" : "停用"}</span></td>
                      <td >{c.isPreset ? <span className="partner-tag">预置</span> : <span className="partner-tag" style={{ background: "var(--brand-soft)", color: "var(--brand-dark)", border: "1px solid var(--brand-border)" }}>自定义</span>}</td>
                      <td >
                        {ic ? (
                          <div style={{ display: "flex", gap: "6px" }}><button onClick={() => saveCatEdit(c.id)} className="table-save" aria-label="保存">✓</button><button onClick={cancelCatEdit} className="table-cancel" aria-label="取消">✕</button></div>
                        ) : (
                          <div style={{ display: "flex", gap: "6px" }}><button onClick={() => startCatEdit(c)} className="secondary-btn" >编辑</button><button onClick={() => toggleCatEnable(c)} className="secondary-btn" >{c.enabled ? "停用" : "启用"}</button></div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table></div>
          )}
        </section>
      )}

      {subTab === "suggestions" && (
        <section className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <h2>AI 标签建议</h2>
          </div>
          <p style={{ fontSize: "13px", color: "var(--muted)", marginTop: "4px" }}>基于项目需求识别标准能力标签未覆盖的新能力诉求，采纳后可上架为一级或二级正式能力标签。</p>
          <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
            <input type="text" placeholder="搜索建议名称..." value={sugKeyword} onChange={(e) => setSugKeyword(e.target.value)} style={{ flex: "1 1 200px" }} />
            <select value={sugStatus} onChange={(e) => setSugStatus(e.target.value)} ><option value="">全部状态</option><option value="pending">待采纳</option><option value="adopted">已采纳</option></select>
          </div>
          {sugError && <p className="error-text">{sugError}</p>}
          {sugLoading ? <p style={{ marginTop: "12px" }}>加载中...</p> : sugList.length === 0 ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无标签建议。</p> : (
            <div className="table-wrap"><table className="data-table" style={{ marginTop: "12px" }}>
              <thead><tr style={{ borderBottom: "1px solid var(--line)" }}>
                <th style={{ textAlign: "left", whiteSpace: "nowrap" }}>建议标签</th>
                <th style={{ textAlign: "left", whiteSpace: "nowrap" }}>层级 / 归属</th>
                <th style={{ textAlign: "left" }}>说明</th>
                <th style={{ textAlign: "left", whiteSpace: "nowrap" }}>次数</th>
                <th style={{ textAlign: "left", whiteSpace: "nowrap" }}>置信度</th>
                <th style={{ textAlign: "left", whiteSpace: "nowrap" }}>状态</th>
                <th style={{ textAlign: "left", whiteSpace: "nowrap" }}>操作</th>
              </tr></thead>
              <tbody>
                {sugList.map((s) => (
                  <tr key={s.id} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {adoptingId === s.id ? <input type="text" value={adoptName} onChange={(e) => setAdoptName(e.target.value)} style={inpStyle} /> : s.suggestedName}
                    </td>
                    <td >
                      {adoptingId === s.id ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px", minWidth: "170px" }}>
                          <select value={adoptLevel} onChange={(e) => setAdoptLevel(Number(e.target.value) === 2 ? 2 : 1)} style={inpStyle}>
                            <option value={1}>采纳为一级标签</option>
                            <option value={2}>采纳为二级标签</option>
                          </select>
                          {adoptLevel === 1 ? (
                            <select value={adoptCat} onChange={(e) => setAdoptCat(e.target.value)} style={inpStyle}>
                              <option value="">使用建议分类</option>
                              {categories.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                          ) : (
                            <select value={adoptParentId} onChange={(e) => setAdoptParentId(e.target.value)} style={inpStyle}>
                              {tree.map((cat) => (
                                <optgroup key={cat.name} label={cat.name}>
                                  {cat.tags.map((l1) => <option key={l1.id} value={l1.id}>{l1.name}</option>)}
                                </optgroup>
                              ))}
                            </select>
                          )}
                        </div>
                      ) : s.suggestedCategoryName || "-"}
                    </td>
                    <td style={{ color: "var(--muted)" }}>
                      {adoptingId === s.id ? <input type="text" value={adoptDesc} onChange={(e) => setAdoptDesc(e.target.value)} style={inpStyle} /> : (s.description || "-")}
                    </td>
                    <td >{s.occurrenceCount}</td>
                    <td >{(s.confidence * 100).toFixed(0)}%</td>
                    <td style={{ whiteSpace: "nowrap" }}><span className="ui-status-badge" style={{ background: s.status === "adopted" ? "#f0fdf4" : "#fffbeb", color: s.status === "adopted" ? "var(--success)" : "#e8a317", border: `1px solid ${s.status === "adopted" ? "#bbf7d0" : "#fde68a"}` }}>{s.status === "adopted" ? "已采纳" : "待采纳"}</span></td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {s.status === "pending" && (
                        adoptingId === s.id ? (
                          <div style={{ display: "flex", gap: "6px" }}><button onClick={() => confirmAdopt(s.id)} className="table-save" aria-label="保存">✓</button><button onClick={cancelAdopt} className="table-cancel" aria-label="取消">✕</button></div>
                        ) : (
                          <button onClick={() => startAdopt(s)} className="secondary-btn" >采纳</button>
                        )
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </section>
      )}

      {subTab === "tags" && (
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <h2>能力标签（顶层分组 / 一级 / 二级）</h2>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <button type="button" className="secondary-btn" onClick={() => toggleExpandAll(true)}>展开全部</button>
            <button type="button" className="secondary-btn" onClick={() => toggleExpandAll(false)}>收起全部</button>
            <button onClick={startNewL1} disabled={isEditing} style={{ opacity: isEditing ? 0.5 : 1 }}>新增一级标签</button>
          </div>
        </div>
        <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
          <input type="text" placeholder="搜索一级或二级标签名称..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ flex: "1 1 200px" }} />
          <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)} >
            <option value="">全部顶层分类</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {error && <p className="error-text">{error}</p>}
        {loading ? <p style={{ marginTop: "12px" }}>加载中...</p> : (visibleTree.length === 0 && !isNewRow) ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无标签数据。</p> : (
          <div className="table-wrap"><table className="data-table" style={{ marginTop: "12px" }}>
            <thead><tr style={{ borderBottom: "1px solid var(--line)" }}>
              <th style={{ textAlign: "left" }}>标签名称（一级 / ↳ 二级）</th>
              <th style={{ textAlign: "left" }}>顶层分类 / 所属一级</th>
              <th style={{ textAlign: "left" }}>说明</th>
              <th style={{ textAlign: "left" }}>排序</th>
              <th style={{ textAlign: "left" }}>状态</th>
              <th style={{ textAlign: "left" }}>类型</th>
              <th style={{ textAlign: "left" }}>操作</th>
            </tr></thead>
            <tbody>
              {isNewRow && !newParentId && (
                <tr style={{ borderBottom: "1px solid var(--line)", background: "var(--bg-hover)" }}>
                  <td ><input type="text" value={eName} onChange={(e) => setEName(e.target.value)} placeholder="一级标签名称" style={inpStyle} autoFocus /></td>
                  <td ><select value={eCat} onChange={(e) => setECat(e.target.value)} style={inpStyle}>{categories.map(c => <option key={c} value={c}>{c}</option>)}</select></td>
                  <td ><input type="text" value={eDesc} onChange={(e) => setEDesc(e.target.value)} placeholder="选填" style={inpStyle} /></td>
                  <td ><input type="number" value={eSort} onChange={(e) => setESort(parseInt(e.target.value) || 0)} style={{ ...inpStyle, width: "60px" }} /></td>
                  <td ></td>
                  <td ></td>
                  <td ><div style={{ display: "flex", gap: "6px" }}>
                    <button onClick={() => saveEdit(null)} className="table-save" aria-label="保存">✓</button>
                    <button onClick={cancelEdit} className="table-cancel" aria-label="取消">✕</button>
                  </div></td>
                </tr>
              )}
              {visibleTree.map((cat) => (
                <Fragment key={cat.id || cat.name}>
                  <tr style={{ background: "var(--bg-hover)", borderBottom: "1px solid var(--line)" }}>
                    <td colSpan={7} style={{ fontWeight: 600, fontSize: "13px" }}>
                      {cat.name}（一级 {cat.tags.length} 项 / 二级 {cat.tags.reduce((acc, item) => acc + item.children.length, 0)} 项）
                    </td>
                  </tr>
                  {cat.tags.map((t) => {
                    const isThisEditing = editingId === t.id;
                    const hasChildren = t.children.length > 0;
                    const isAddingChild = isNewRow && newParentId === t.id;
                    const isOpen = !!query || isAddingChild || !!expandedIds[t.id];
                    return (
                      <Fragment key={t.id}>
                        <tr style={{ borderBottom: "1px solid var(--line)", background: isThisEditing ? "var(--bg-hover)" : undefined }}>
                          <td >
                            {isThisEditing ? (
                              <input type="text" value={eName} onChange={(e) => setEName(e.target.value)} style={inpStyle} />
                            ) : (
                              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                {hasChildren ? (
                                  <button
                                    type="button"
                                    className="secondary-btn"
                                    style={{ padding: "1px 6px", fontSize: "12px" }}
                                    onClick={() => setExpandedIds((prev) => ({ ...prev, [t.id]: !isOpen }))}
                                    aria-label={isOpen ? `收起${t.name}` : `展开${t.name}`}
                                  >
                                    {isOpen ? "▾" : "▸"}
                                  </button>
                                ) : (
                                  <span style={{ display: "inline-block", width: "22px" }} />
                                )}
                                <span style={{ fontSize: "14px", fontWeight: 500 }}>{t.name}</span>
                                <span className="partner-tag" style={{ marginLeft: 0 }}>二级 {t.children.length}</span>
                              </div>
                            )}
                          </td>
                          <td >
                            {isThisEditing ? <select value={eCat} onChange={(e) => setECat(e.target.value)} style={inpStyle}>{categories.map(c => <option key={c} value={c}>{c}</option>)}</select> : <span style={{ fontSize: "13px" }}>{t.category}</span>}
                          </td>
                          <td >
                            {isThisEditing ? <input type="text" value={eDesc} onChange={(e) => setEDesc(e.target.value)} placeholder="选填" style={inpStyle} /> : <span style={{ fontSize: "13px", color: "var(--muted)" }}>{t.description || "-"}</span>}
                          </td>
                          <td >
                            {isThisEditing ? <input type="number" value={eSort} onChange={(e) => setESort(parseInt(e.target.value) || 0)} style={{ ...inpStyle, width: "60px" }} /> : <span style={{ fontSize: "13px" }}>{t.sortOrder}</span>}
                          </td>
                          <td ><span className="ui-status-badge" style={{ background: t.enabled ? "#f0fdf4" : "#fef2f2", color: t.enabled ? "var(--success)" : "var(--danger)", border: `1px solid ${t.enabled ? "#bbf7d0" : "#fecaca"}` }}>{t.enabled ? "启用" : "停用"}</span></td>
                          <td >{t.isPreset ? <span className="partner-tag">预置</span> : <span className="partner-tag" style={{ background: "var(--brand-soft)", color: "var(--brand-dark)", border: "1px solid var(--brand-border)" }}>自定义</span>}</td>
                          <td >
                            {isThisEditing ? (
                              <div style={{ display: "flex", gap: "6px" }}>
                                <button onClick={() => saveEdit(t.id)} className="table-save" aria-label="保存">✓</button>
                                <button onClick={cancelEdit} className="table-cancel" aria-label="取消">✕</button>
                              </div>
                            ) : (
                              <div style={{ display: "flex", gap: "6px" }}>
                                <button onClick={() => startNewL2(t)} disabled={isEditing} className="secondary-btn">+ 二级</button>
                                <button onClick={() => startEditL1(t)} disabled={isEditing} className="secondary-btn" >编辑</button>
                                <button onClick={() => handleToggle(t)} className="secondary-btn" >{t.enabled ? "停用" : "启用"}</button>
                              </div>
                            )}
                          </td>
                        </tr>
                        {isAddingChild && (
                          <tr style={{ borderBottom: "1px solid var(--line)", background: "var(--bg-hover)" }}>
                            <td style={{ paddingLeft: "36px" }}><input type="text" value={eName} onChange={(e) => setEName(e.target.value)} placeholder={`新增“${t.name}”二级标签`} style={inpStyle} autoFocus /></td>
                            <td style={{ fontSize: "13px", color: "var(--muted)" }}>归属：{t.name}</td>
                            <td ><input type="text" value={eDesc} onChange={(e) => setEDesc(e.target.value)} placeholder="选填" style={inpStyle} /></td>
                            <td ><input type="number" value={eSort} onChange={(e) => setESort(parseInt(e.target.value) || 0)} style={{ ...inpStyle, width: "60px" }} /></td>
                            <td ></td>
                            <td ></td>
                            <td ><div style={{ display: "flex", gap: "6px" }}>
                              <button onClick={() => saveEdit(null)} className="table-save" aria-label="保存">✓</button>
                              <button onClick={cancelEdit} className="table-cancel" aria-label="取消">✕</button>
                            </div></td>
                          </tr>
                        )}
                        {isOpen && t.children.map((child) => {
                          const isChildEditing = editingId === child.id;
                          return (
                            <tr key={child.id} style={{ borderBottom: "1px solid var(--line)", background: isChildEditing ? "var(--bg-hover)" : undefined }}>
                              <td style={{ paddingLeft: "36px" }}>
                                {isChildEditing ? <input type="text" value={eName} onChange={(e) => setEName(e.target.value)} style={inpStyle} /> : <span style={{ fontSize: "13px" }}>↳ {child.name}</span>}
                              </td>
                              <td >
                                {isChildEditing ? (
                                  <select value={eParentId} onChange={(e) => setEParentId(e.target.value)} style={inpStyle}>
                                    {tree.map((group) => (
                                      <optgroup key={group.name} label={group.name}>
                                        {group.tags.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                                      </optgroup>
                                    ))}
                                  </select>
                                ) : (
                                  <span style={{ fontSize: "12px", color: "var(--muted)" }}>{t.name}</span>
                                )}
                              </td>
                              <td >
                                {isChildEditing ? <input type="text" value={eDesc} onChange={(e) => setEDesc(e.target.value)} placeholder="选填" style={inpStyle} /> : <span style={{ fontSize: "13px", color: "var(--muted)" }}>{child.description || "-"}</span>}
                              </td>
                              <td >
                                {isChildEditing ? <input type="number" value={eSort} onChange={(e) => setESort(parseInt(e.target.value) || 0)} style={{ ...inpStyle, width: "60px" }} /> : <span style={{ fontSize: "13px" }}>{child.sortOrder}</span>}
                              </td>
                              <td ><span className="ui-status-badge" style={{ background: child.enabled ? "#f0fdf4" : "#fef2f2", color: child.enabled ? "var(--success)" : "var(--danger)", border: `1px solid ${child.enabled ? "#bbf7d0" : "#fecaca"}` }}>{child.enabled ? "启用" : "停用"}</span></td>
                              <td >{child.isPreset ? <span className="partner-tag">预置</span> : <span className="partner-tag" style={{ background: "var(--brand-soft)", color: "var(--brand-dark)", border: "1px solid var(--brand-border)" }}>自定义</span>}</td>
                              <td >
                                {isChildEditing ? (
                                  <div style={{ display: "flex", gap: "6px" }}>
                                    <button onClick={() => saveEdit(child.id)} className="table-save" aria-label="保存">✓</button>
                                    <button onClick={cancelEdit} className="table-cancel" aria-label="取消">✕</button>
                                  </div>
                                ) : (
                                  <div style={{ display: "flex", gap: "6px" }}>
                                    <button onClick={() => startEditL2(child)} disabled={isEditing} className="secondary-btn" >编辑</button>
                                    <button onClick={() => handleToggle(child)} className="secondary-btn" >{child.enabled ? "停用" : "启用"}</button>
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </Fragment>
                    );
                  })}
                </Fragment>
              ))}
            </tbody>
          </table></div>
        )}
      </section>
      )}
    </div>
  );
}


// ============ System Status Tab ============
export function SystemStatusTab() {
  const moduleName=(name:string)=>name==="智能匹配"?"伙伴推荐":name;
  function impactText(value:string){
    if(value==="可能影响智能匹配")return "可能影响伙伴推荐";
    if(value==="可能影响伙伴资料、标签配置、匹配历史读取")return "可能影响伙伴资料、标签配置、推荐历史读取";
    if(value==="可能影响 AI 画像生成、智能匹配和需求画像生成")return "可能影响 AI 画像生成、伙伴推荐和需求画像生成";
    return value;
  }
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
    return <span className="ui-status-badge" style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{s.label}</span>;
  }

  function StatusCard({ title, items }: { title: string; items: any[] }) {
    return (
      <section className="card">
        <h2>{title}</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "12px" }}>
          {items.map((item, i) => (
            <div key={i} className="ui-status-row">
              <div>
                <span style={{ fontSize: "14px", fontWeight: 400 }}>{title==="业务能力"?moduleName(item.name):item.name}</span>
                <span style={{ fontSize: "13px", color: "var(--muted)", marginLeft: "8px" }}>{item.message}</span>
                {item.detail && <p className="muted" style={{ margin: "4px 0 0", fontSize: "13px" }}>{item.detail}</p>}
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
    partial: { label: `系统部分异常：${data.summary.abnormalModules.slice(0, 3).map((m: any) => moduleName(m.module)).join("、")}${data.summary.abnormalModules.length > 3 ? `等 ${data.summary.abnormalModules.length} 项` : ""}`, color: "#e8a317" },
    error: { label: "系统异常", color: "var(--danger)" },
    unknown: { label: "部分运行状态尚未验证", color: "var(--muted)" },
  };
  const overall = overallMap[data.overallStatus] || overallMap.unknown;

  return (
    <div>
      {/* Overall status */}
      <p className="placeholder-text" style={{ marginBottom: "16px" }}>本页仅执行只读查询和配置检查，不测试数据库写入，也不发送模型请求。需要验证模型连接时，请前往<a href="/admin/models">模型配置</a>手动测试。</p>
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <div>
            <h2 style={{ color: overall.color }}>{overall.label}</h2>
            <p style={{ fontSize: "13px", color: "var(--muted)", marginTop: "4px" }}>最后检查: {data.checkedAt.slice(0, 19).replace("T", " ")}</p>
          </div>
          <button onClick={loadData} className="secondary-btn">刷新状态</button>
        </div>
        {/* Stats */}
        <div className="ui-status-summary">
          <div><span style={{ fontSize: "20px", fontWeight: 400, color: "var(--success)" }}>{data.summary.normalCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>正常</span></div>
          <div><span style={{ fontSize: "20px", fontWeight: 400, color: "#e8a317" }}>{data.summary.warningCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>警告</span></div>
          <div><span style={{ fontSize: "20px", fontWeight: 400, color: "var(--danger)" }}>{data.summary.errorCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>异常</span></div>
          <div><span style={{ fontSize: "20px", fontWeight: 400, color: "var(--muted)" }}>{data.summary.unknownCount}</span> <span style={{ fontSize: "12px", color: "var(--muted)" }}>未知</span></div>
        </div>
        {/* Abnormal modules */}
        {data.summary.abnormalModules.length > 0 && (
          <div style={{ marginTop: "12px" }}>
            <h3 style={{ fontSize: "14px", marginBottom: "8px" }}>异常详情</h3>
            {data.summary.abnormalModules.map((m: any, i: number) => (
              <div key={i} className="ui-status-issue">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                  <span style={{ fontSize: "14px", fontWeight: 400, color: "#991b1b" }}>{moduleName(m.module)}</span>
                  {statusBadge(m.status)}
                </div>
                <div style={{ fontSize: "13px", color: "#666" }}><strong>异常:</strong> {m.message}</div>
                <div style={{ fontSize: "13px", color: "#666", marginTop: "4px" }}><strong>影响范围:</strong> {impactText(m.impact)}</div>
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
export function ModelConfigTab() { return <ModelConfiguration/>; }

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
    ["内部用户", "users"], ["停用用户", "disabledUsers"], ["启用伙伴", "partners"],
    ["待完善画像", "partnersWithoutProfile"], ["累计任务", "tasks"], ["本月任务", "monthTasks"],
    ["项目机会", "opportunities"], ["供给不足", "gapDemands"], ["待采纳建议", "pendingSuggestions"],
  ];

  return (
    <main className="page">
      <p className="eyebrow">Administration</p><h1>后台概览</h1><p className="lead">查看平台用户、伙伴、任务和运营待办。</p>
      {error && <div className="inline-error-actions"><p className="error-text">{error}</p><button className="secondary-btn" onClick={loadData}>重试</button></div>}
      <section className="admin-metric-grid">{cards.map(([label, key]) => <div className="card admin-metric-card" key={key}><span>{label}</span><strong>{data ? data[key] ?? 0 : "--"}</strong>{data && (key === "tasks" || key === "monthTasks") && <small className="muted">伙伴推荐 {data[key === "tasks" ? "partnerMatchTasks" : "monthPartnerMatchTasks"] ?? 0} · 能力发展 {data[key === "tasks" ? "developmentTasks" : "monthDevelopmentTasks"] ?? 0}</small>}</div>)}</section>
      <section className="card"><h2>管理重点</h2><div className="admin-shortcuts"><a href="/admin/users">管理用户</a><a href="/admin/partners">完善伙伴资料</a><a href="/admin/tasks">查看全量任务</a><a href="/admin/tags">处理标签建议</a></div></section>
    </main>
  );
}
