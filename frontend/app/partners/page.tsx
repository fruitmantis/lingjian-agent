"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

type Partner = { id: string; name: string; ai_profile: string | null; created_at: string; };
type PartnerDoc = { id: string; partner_id: string; filename: string; file_type: string; created_at: string; };

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function PartnersPage() {
  const router = useRouter();
  const [partners, setPartners] = useState<Partner[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [currentUser, setCurrentUser] = useState<string>("");
  const [uploadingPartnerId, setUploadingPartnerId] = useState<string | null>(null);
  const [docsMap, setDocsMap] = useState<Record<string, PartnerDoc[]>>({});
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [batchGenerating, setBatchGenerating] = useState(false);
  const [batchResult, setBatchResult] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.push("/login"); return; }
    fetch(`${apiBaseUrl}/auth/me`, { headers: authHeaders() })
      .then(res => { if (!res.ok) throw new Error("invalid"); return res.json(); })
      .then(user => { setCurrentUser(user.display_name || user.username); setAuthChecked(true); })
      .catch(() => { localStorage.removeItem("token"); localStorage.removeItem("user"); router.push("/login"); });
  }, [router]);

  useEffect(() => { if (authChecked) loadPartners(); }, [authChecked]);

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    router.push("/login");
  }

  async function loadPartners() {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/partners`, { cache: "no-store", headers: authHeaders() });
      if (res.status === 401) { handleLogout(); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const list = await res.json();
      setPartners(list);
      const dMap: Record<string, PartnerDoc[]> = {};
      await Promise.all(list.map(async (p: Partner) => {
        const dr = await fetch(`${apiBaseUrl}/partners/${p.id}/documents`, { cache: "no-store", headers: authHeaders() });
        if (dr.ok) dMap[p.id] = await dr.json();
      }));
      setDocsMap(dMap);
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); } finally { setLoading(false); }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setLoading(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/partners`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ name }) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setName(""); await loadPartners();
    } catch (e) { setError(e instanceof Error ? e.message : "新增失败"); } finally { setLoading(false); }
  }

  async function handleUploadDoc(partnerId: string, file: File) {
    setUploadingPartnerId(partnerId); setError(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await fetch(`${apiBaseUrl}/partners/${partnerId}/documents`, { method: "POST", headers: authHeaders(), body: fd });
      if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      await loadPartners();
    } catch (e) { setError(e instanceof Error ? e.message : "上传失败"); } finally { setUploadingPartnerId(null); }
  }

  async function handleDeleteDoc(partnerId: string, docId: string) {
    if (!confirm("确定删除该文档？")) return;
    try { const res = await fetch(`${apiBaseUrl}/partners/${partnerId}/documents/${docId}`, { method: "DELETE", headers: authHeaders() }); if (!res.ok) throw new Error(`HTTP ${res.status}`); await loadPartners(); } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
  }

  async function handleGenerateProfile(partnerId: string) {
    setGeneratingId(partnerId); setError(null);
    try { const res = await fetch(`${apiBaseUrl}/partners/${partnerId}/profile`, { method: "POST", headers: authHeaders() }); if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); } await loadPartners(); } catch (e) { setError(e instanceof Error ? e.message : "生成画像失败"); } finally { setGeneratingId(null); }
  }

  async function handleBatchGenerate() {
    setBatchGenerating(true); setError(null); setBatchResult(null);
    try {
      const res = await fetch(`${apiBaseUrl}/partners/batch-profile`, { method: "POST", headers: authHeaders() });
      if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      const data = await res.json();
      setBatchResult(`批量生成完成：成功 ${data.success}/${data.total}，失败 ${data.failed}`);
      await loadPartners();
    } catch (e) { setError(e instanceof Error ? e.message : "批量生成失败"); } finally { setBatchGenerating(false); }
  }

  if (!authChecked) return <main className="page"><p>检查登录状态...</p></main>;

  return (
    <main className="page">
      <p className="eyebrow">Partner Management</p>
      <h1>伙伴资料管理</h1>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p className="lead">维护伙伴资料，上传文档后 AI 自动分析生成能力画像。</p>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <span style={{ fontSize: "14px", color: "var(--muted)" }}>当前用户：{currentUser}</span>
          <button onClick={handleLogout} className="secondary-btn" style={{ fontSize: "13px" }}>登出</button>
        </div>
      </div>
      <section className="card">
        <h2>新增伙伴</h2>
        <form onSubmit={handleSubmit} className="partner-form">
          <div className="form-row"><label htmlFor="name">伙伴名称</label><input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} placeholder="伙伴名称" /></div>
          <button type="submit" disabled={loading}>{loading ? "提交中..." : "新增"}</button>
        </form>
        {error && <p className="error-text">{error}</p>}
      </section>
      <section className="card">
        <h2>伙伴列表</h2>
        <div style={{ display: "flex", gap: "12px", alignItems: "center", marginBottom: "12px" }}>
          <button onClick={loadPartners} disabled={loading} className="secondary-btn">刷新列表</button>
          <button onClick={handleBatchGenerate} disabled={batchGenerating || loading} style={{ fontSize: "13px", padding: "8px 16px", background: "var(--brand)", color: "white", border: "none", borderRadius: "8px", cursor: "pointer", fontWeight: 600 }}>{batchGenerating ? "批量生成中..." : "一键重新生成 AI 画像"}</button>
          {batchResult && <span style={{ fontSize: "13px", color: "var(--success)" }}>{batchResult}</span>}
        </div>
        {partners.length === 0 ? <p className="placeholder-text">暂无伙伴。</p> : (
          <div style={{ display: "flex", flexDirection: "column", gap: "20px", marginTop: "16px" }}>
            {partners.map((p) => (
              <div key={p.id} className="case-item">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h3><a href={`/partners/${p.id}`}>{p.name}</a></h3>
                  <span className="partner-tag">创建于 {p.created_at.slice(0, 10)}</span>
                </div>
                {p.ai_profile ? <p style={{ fontSize: "13px", color: "var(--muted)", marginTop: "4px" }}>AI 画像已生成</p> : <p style={{ fontSize: "13px", color: "var(--muted)", marginTop: "4px" }}>暂无 AI 画像</p>}
                <div className="deliverable-section" style={{ marginTop: "12px" }}>
                  <h4>伙伴文档（上传 PPT/DOC/EXCEL/PDF，AI 自动分析）</h4>
                  {(docsMap[p.id] || []).length === 0 ? <p className="placeholder-text">暂无文档。</p> : (
                    <ul className="deliverable-list">
                      {(docsMap[p.id] || []).map((d) => (
                        <li key={d.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span>{d.filename} <span className="partner-tag">{d.file_type}</span></span>
                          <button onClick={() => handleDeleteDoc(p.id, d.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>删除</button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
                    <label className="upload-btn">{uploadingPartnerId === p.id ? "上传中..." : "上传文档"}<input type="file" hidden accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls" disabled={uploadingPartnerId === p.id} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadDoc(p.id, f); e.target.value = ""; }} /></label>
                    <button onClick={() => handleGenerateProfile(p.id)} disabled={generatingId === p.id} className="secondary-btn" style={{ fontSize: "13px" }}>{generatingId === p.id ? "生成中..." : "生成 AI 画像"}</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
