"use client";

import { useEffect, useState } from "react";
import { use } from "react";

type Partner = { id: string; name: string; intro: string | null; capabilities: string | null; service_areas: string | null; industries: string | null; ai_profile: string | null; created_at: string; };
type Case = { id: string; partner_id: string; title: string; description: string | null; created_at: string; };
type Deliverable = { id: string; case_id: string; filename: string; file_path: string; created_at: string; };
type PartnerDoc = { id: string; partner_id: string; filename: string; file_type: string; doc_category: string | null; extracted_text: string | null; created_at: string; };

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function PartnerProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [partner, setPartner] = useState<Partner | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [docs, setDocs] = useState<PartnerDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [caseTitle, setCaseTitle] = useState("");
  const [caseDesc, setCaseDesc] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deliverablesMap, setDeliverablesMap] = useState<Record<string, Deliverable[]>>({});
  const [uploadingCaseId, setUploadingCaseId] = useState<string | null>(null);
  const [generatingProfile, setGeneratingProfile] = useState(false);
  const [uploadingDoc, setUploadingDoc] = useState(false);

  async function loadPartner() {
    setLoading(true); setError(null);
    try {
      const [pRes, cRes, dRes] = await Promise.all([fetch(`${apiBaseUrl}/partners/${id}`, { cache: "no-store", headers: authHeaders() }), fetch(`${apiBaseUrl}/cases/by-partner/${id}`, { cache: "no-store", headers: authHeaders() }), fetch(`${apiBaseUrl}/partners/${id}/documents`, { cache: "no-store", headers: authHeaders() })]);
      if (!pRes.ok) throw new Error(`Partner HTTP ${pRes.status}`);
      if (!cRes.ok) throw new Error(`Cases HTTP ${cRes.status}`);
      if (!dRes.ok) throw new Error(`Docs HTTP ${dRes.status}`);
      setPartner(await pRes.json());
      const caseList: Case[] = await cRes.json();
      setCases(caseList);
      setDocs(await dRes.json());
      const dMap: Record<string, Deliverable[]> = {};
      await Promise.all(caseList.map(async (c) => { const dr = await fetch(`${apiBaseUrl}/cases/${c.id}/deliverables`, { cache: "no-store", headers: authHeaders() }); if (dr.ok) dMap[c.id] = await dr.json(); }));
      setDeliverablesMap(dMap);
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); } finally { setLoading(false); }
  }

  useEffect(() => { loadPartner(); }, [id]);

  async function handleCreateCase(e: React.FormEvent) {
    e.preventDefault(); setSubmitting(true); setError(null);
    try { const res = await fetch(`${apiBaseUrl}/cases`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ partner_id: id, title: caseTitle, description: caseDesc || null }) }); if (!res.ok) throw new Error(`HTTP ${res.status}`); setCaseTitle(""); setCaseDesc(""); await loadPartner(); } catch (e) { setError(e instanceof Error ? e.message : "新增案例失败"); } finally { setSubmitting(false); }
  }

  async function handleUploadDeliverable(caseId: string, file: File) {
    setUploadingCaseId(caseId); setError(null);
    try { const fd = new FormData(); fd.append("file", file); const res = await fetch(`${apiBaseUrl}/cases/${caseId}/deliverables`, { method: "POST", headers: authHeaders(), body: fd }); if (!res.ok) throw new Error(`HTTP ${res.status}`); await loadPartner(); } catch (e) { setError(e instanceof Error ? e.message : "上传失败"); } finally { setUploadingCaseId(null); }
  }

  async function handleUploadDoc(file: File) {
    setUploadingDoc(true); setError(null);
    try { const fd = new FormData(); fd.append("file", file); const res = await fetch(`${apiBaseUrl}/partners/${id}/documents`, { method: "POST", headers: authHeaders(), body: fd }); if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); } await loadPartner(); } catch (e) { setError(e instanceof Error ? e.message : "文档上传失败"); } finally { setUploadingDoc(false); }
  }

  async function handleDeleteDoc(docId: string) {
    if (!confirm("确定删除该文档？")) return;
    try { const res = await fetch(`${apiBaseUrl}/partners/${id}/documents/${docId}`, { method: "DELETE", headers: authHeaders() }); if (!res.ok) throw new Error(`HTTP ${res.status}`); await loadPartner(); } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
  }

  async function handleGenerateProfile() {
    setGeneratingProfile(true); setError(null);
    try { const res = await fetch(`${apiBaseUrl}/partners/${id}/profile`, { method: "POST", headers: authHeaders() }); if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); } await loadPartner(); } catch (e) { setError(e instanceof Error ? e.message : "生成画像失败"); } finally { setGeneratingProfile(false); }
  }

  return (
    <main className="page">
      <p className="eyebrow">Partner Profile</p>
      <h1>伙伴画像详情</h1>
      <p className="lead">伙伴标识：{id}</p>

      <section className="card">
        <h2>基础信息</h2>
        {loading && <p>加载中...</p>}
        {error && <p className="error-text">{error}</p>}
        {partner && (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "16px" }}>
            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>名称</div>
                <div style={{ fontSize: "16px", fontWeight: 600 }}>{partner.name}</div>
              </div>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>创建时间</div>
                <div style={{ fontSize: "14px" }}>{partner.created_at.slice(0, 10)}</div>
              </div>
            </div>
            {partner.intro && (
              <div style={{ padding: "16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>简介</div>
                <div style={{ fontSize: "14px", lineHeight: 1.8 }}>{partner.intro}</div>
              </div>
            )}
            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#fff1f2", borderRadius: "8px", border: "1px solid #ffd0d4" }}>
                <div style={{ fontSize: "12px", color: "var(--brand-dark)", fontWeight: 600, marginBottom: "8px" }}>能力标签</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {(partner.capabilities || "未分析").split(/[,，]/).filter(Boolean).map((tag, i) => (
                    <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: "white", color: "var(--brand-dark)", border: "1px solid #ffd0d4", fontWeight: 500 }}>{tag.trim()}</span>
                  ))}
                </div>
              </div>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#f0f5ff", borderRadius: "8px", border: "1px solid #d6e4ff" }}>
                <div style={{ fontSize: "12px", color: "#1a4fa0", fontWeight: 600, marginBottom: "8px" }}>覆盖区域</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {(partner.service_areas || "未分析").split(/[,，]/).filter(Boolean).map((tag, i) => (
                    <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: "white", color: "#1a4fa0", border: "1px solid #d6e4ff", fontWeight: 500 }}>{tag.trim()}</span>
                  ))}
                </div>
              </div>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#f0fdf4", borderRadius: "8px", border: "1px solid #bbf7d0" }}>
                <div style={{ fontSize: "12px", color: "var(--success)", fontWeight: 600, marginBottom: "8px" }}>行业经验</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {(partner.industries || "未分析").split(/[,，]/).filter(Boolean).map((tag, i) => (
                    <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: "white", color: "var(--success)", border: "1px solid #bbf7d0", fontWeight: 500 }}>{tag.trim()}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <h2>伙伴文档资料</h2>
        <p style={{ fontSize: "14px", marginBottom: "12px" }}>支持上传 PPT、DOC、EXCEL、PDF 文件，系统自动提取文本用于 AI 画像分析。</p>
        <label className="upload-btn" style={{ display: "inline-block" }}>{uploadingDoc ? "上传中..." : "上传文档"}<input type="file" hidden accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls" disabled={uploadingDoc} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadDoc(f); e.target.value = ""; }} /></label>
        {docs.length > 0 ? (<ul className="deliverable-list" style={{ marginTop: "16px" }}>{docs.map((d) => (<li key={d.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><span>{d.filename} <span className="partner-tag">{d.file_type}</span></span><button onClick={() => handleDeleteDoc(d.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>删除</button></li>))}</ul>) : <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无文档。</p>}
      </section>

      <section className="card">
        <h2>AI 能力画像</h2>
        {partner?.ai_profile ? (<div className="ai-profile"><pre className="ai-profile-text">{partner.ai_profile}</pre><button onClick={handleGenerateProfile} disabled={generatingProfile} className="secondary-btn">{generatingProfile ? "生成中..." : "重新生成"}</button></div>) : (<div className="ai-profile-empty"><p className="placeholder-text">暂无 AI 画像。上传文档后点击生成，AI 将从文档中分析能力画像。</p><button onClick={handleGenerateProfile} disabled={generatingProfile}>{generatingProfile ? "生成中（可能需要数十秒）..." : "生成 AI 画像"}</button></div>)}
      </section>

      <section className="card">
        <h2>新增案例</h2>
        <form onSubmit={handleCreateCase} className="partner-form"><div className="form-row"><label htmlFor="caseTitle">案例标题</label><input id="caseTitle" type="text" value={caseTitle} onChange={(e) => setCaseTitle(e.target.value)} required maxLength={300} placeholder="案例标题" /></div><div className="form-row"><label htmlFor="caseDesc">案例描述</label><textarea id="caseDesc" value={caseDesc} onChange={(e) => setCaseDesc(e.target.value)} placeholder="选填" rows={3} /></div><button type="submit" disabled={submitting}>{submitting ? "提交中..." : "新增案例"}</button></form>
      </section>

      <section className="card">
        <h2>案例与交付物</h2>
        {cases.length === 0 ? <p className="placeholder-text">暂无案例。</p> : (<ul className="case-list">{cases.map((c) => (<li key={c.id} className="case-item"><h3>{c.title}</h3>{c.description && <p>{c.description}</p>}<p className="meta-text">创建时间：{c.created_at}</p><div className="deliverable-section"><h4>交付物</h4>{(deliverablesMap[c.id] || []).length === 0 ? <p className="placeholder-text">暂无交付物。</p> : <ul className="deliverable-list">{(deliverablesMap[c.id] || []).map((d) => <li key={d.id}>{d.filename}</li>)}</ul>}<label className="upload-btn">{uploadingCaseId === c.id ? "上传中..." : "上传交付物"}<input type="file" hidden disabled={uploadingCaseId === c.id} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadDeliverable(c.id, f); e.target.value = ""; }} /></label></div></li>))}</ul>)}
      </section>
    </main>
  );
}
