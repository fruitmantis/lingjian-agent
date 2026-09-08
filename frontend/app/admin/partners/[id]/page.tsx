"use client";
import {ClassificationFields, ClassificationNotice} from "@/components/business-taxonomy";


import Link from "next/link";
import { FormEvent, use, useEffect, useState } from "react";
import { apiFetch } from "../../../../components/auth-provider";

type Partner = { classification_pending?: Record<string,string[]>; id: string; name: string; intro: string | null; capabilities: string | null; service_areas: string | null; industries: string | null; ai_profile: string | null; status: "active" | "disabled" };
type Document = { id: string; filename: string; file_type: string; extracted_text: string | null; created_at: string };
type PartnerCase = { id: string; title: string; description: string | null; created_at: string };
type Deliverable = { id: string; filename: string; created_at: string };

export default function AdminPartnerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [partner, setPartner] = useState<Partner | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [cases, setCases] = useState<PartnerCase[]>([]);
  const [deliverables, setDeliverables] = useState<Record<string, Deliverable[]>>({});
  const [form, setForm] = useState<Record<string, string>>({});
  const [caseTitle, setCaseTitle] = useState("");
  const [caseDescription, setCaseDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Document | null>(null);

  async function load() {
    setError(null);
    try {
      const [partnerResponse, docsResponse, casesResponse] = await Promise.all([
        apiFetch(`/partners/${id}`, { cache: "no-store" }),
        apiFetch(`/partners/${id}/documents`, { cache: "no-store" }),
        apiFetch(`/cases/by-partner/${id}`, { cache: "no-store" }),
      ]);
      if (!partnerResponse.ok) throw new Error("伙伴不存在");
      const partnerData = await partnerResponse.json() as Partner;
      const caseData = casesResponse.ok ? await casesResponse.json() as PartnerCase[] : [];
      setPartner(partnerData); setDocs(docsResponse.ok ? await docsResponse.json() : []); setCases(caseData);
      setForm({ name: partnerData.name, intro: partnerData.intro || "", capabilities: partnerData.capabilities || "", service_areas: partnerData.service_areas || "", industries: partnerData.industries || "" });
      const pairs = await Promise.all(caseData.map(async item => { const response = await apiFetch(`/cases/${item.id}/deliverables`); return [item.id, response.ok ? await response.json() : []] as const; }));
      setDeliverables(Object.fromEntries(pairs));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "加载失败"); }
  }
  useEffect(() => { void load(); }, [id]);

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

  async function save(event: FormEvent) {
    event.preventDefault();
    await runAction(async () => {
      const response = await apiFetch(`/partners/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      if (response.ok) await load(); else setError((await response.json().catch(() => ({}))).detail || "保存失败");
    });
  }
  async function uploadDocument(file: File) {
    await runAction(async () => {
      const body = new FormData(); body.append("file", file);
      const response = await apiFetch(`/partners/${id}/documents`, { method: "POST", body });
      if (response.ok) await load(); else setError((await response.json().catch(() => ({}))).detail || "上传失败");
    });
  }
  async function deleteDocument(docId: string) {
    if (!confirm("确定删除该伙伴资料？")) return;
    await runAction(async () => {
      const response = await apiFetch(`/partners/${id}/documents/${docId}`, { method: "DELETE" });
      if (response.ok) await load(); else setError("删除失败");
    });
  }
  async function downloadDocument(doc: Document) {
    await runAction(async () => {
      const response = await apiFetch(`/partners/${id}/documents/${doc.id}/file`);
      if (!response.ok) { setError("下载失败"); return; }
      const url = URL.createObjectURL(await response.blob());
      const anchor = window.document.createElement("a"); anchor.href = url; anchor.download = doc.filename; anchor.click(); URL.revokeObjectURL(url);
    });
  }
  async function generateProfile() {
    await runAction(async () => {
      const response = await apiFetch(`/partners/${id}/profile`, { method: "POST" });
      if (response.ok) await load(); else setError((await response.json().catch(() => ({}))).detail || "画像生成失败");
    });
  }
  async function createCase(event: FormEvent) {
    event.preventDefault();
    await runAction(async () => {
      const response = await apiFetch("/cases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ partner_id: id, title: caseTitle, description: caseDescription || null }) });
      if (response.ok) { setCaseTitle(""); setCaseDescription(""); await load(); } else setError("案例新增失败");
    });
  }
  async function uploadDeliverable(caseId: string, file: File) {
    await runAction(async () => {
      const body = new FormData(); body.append("file", file);
      const response = await apiFetch(`/cases/${caseId}/deliverables`, { method: "POST", body });
      if (response.ok) await load(); else setError("交付物上传失败");
    });
  }
  async function deleteCase(caseId: string) {
    if (!confirm("确定删除该案例及其全部交付物？")) return;
    await runAction(async () => {
      const response = await apiFetch(`/cases/${caseId}`, { method: "DELETE" });
      if (response.ok) await load(); else setError("案例删除失败");
    });
  }
  async function deleteDeliverable(caseId: string, deliverableId: string) {
    if (!confirm("确定删除该交付物？")) return;
    await runAction(async () => {
      const response = await apiFetch(`/cases/${caseId}/deliverables/${deliverableId}`, { method: "DELETE" });
      if (response.ok) await load(); else setError("交付物删除失败");
    });
  }
  if (!partner && !error) return <main className="page"><p>伙伴信息加载中...</p></main>;
  return <main className="page"><div className="page-heading-row"><div><p className="eyebrow">Partner Maintenance</p><h1>{partner?.name || "伙伴维护"}</h1><p className="lead">维护正式伙伴信息及匹配证据。</p></div><Link href="/admin/partners" className="secondary-btn">返回伙伴列表</Link></div>{error && <p className="error-text">{error}</p>}
    {partner && <><section className="card"><h2>基础信息</h2><form onSubmit={save} className="form-grid"><div className="form-row"><label>伙伴名称</label><input value={form.name || ""} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} required /></div><ClassificationFields industries={form.industries||""} regions={form.service_areas||""} onIndustries={industries=>setForm(current=>({...current,industries}))} onRegions={service_areas=>setForm(current=>({...current,service_areas}))}/><div className="form-span-two"><ClassificationNotice pending={partner.classification_pending}/></div><div className="form-row"><label>能力标签</label><input value={form.capabilities || ""} onChange={event => setForm(current => ({ ...current, capabilities: event.target.value }))} /></div><div className="form-row form-span-two"><label>伙伴简介</label><textarea rows={3} value={form.intro || ""} onChange={event => setForm(current => ({ ...current, intro: event.target.value }))} /></div><div className="form-span-two"><button disabled={busy}>保存伙伴信息</button></div></form></section>
    <section className="card"><div className="section-heading-row"><div><h2>原始伙伴资料</h2><p>仅管理员可以查看、下载和维护。</p></div><label className="upload-btn">{busy ? "处理中..." : "上传资料"}<input type="file" hidden accept=".pdf,.docx,.pptx,.xlsx" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (file) void uploadDocument(file); event.target.value = ""; }} /></label></div>{docs.length === 0 ? <p className="placeholder-text">暂无资料。</p> : <div className="document-list">{docs.map(doc => <div key={doc.id}><div><strong>{doc.filename}</strong><span>{doc.file_type.toUpperCase()} · {new Date(doc.created_at).toLocaleDateString("zh-CN")}</span></div><div className="table-actions"><button className="secondary-btn" onClick={() => setPreview(preview?.id === doc.id ? null : doc)}>提取文本</button><button disabled={busy} className="secondary-btn" onClick={() => downloadDocument(doc)}>下载</button><button disabled={busy} className="secondary-btn danger-outline" onClick={() => deleteDocument(doc.id)}>删除</button></div>{preview?.id === doc.id && <pre className="document-preview">{doc.extracted_text || "未提取到文本内容"}</pre>}</div>)}</div>}</section>
    <section className="card card-highlight"><div className="section-heading-row"><h2>AI 能力画像</h2><button onClick={generateProfile} disabled={busy}>{partner.ai_profile ? "重新生成" : "生成画像"}</button></div>{partner.ai_profile ? <pre className="ai-profile-text">{partner.ai_profile}</pre> : <p className="placeholder-text">尚未生成画像。</p>}</section>
    <section className="card"><h2>案例与交付物</h2><form onSubmit={createCase} className="form-grid compact-form"><div className="form-row"><label>案例标题</label><input value={caseTitle} onChange={event => setCaseTitle(event.target.value)} required /></div><div className="form-row"><label>案例描述</label><input value={caseDescription} onChange={event => setCaseDescription(event.target.value)} /></div><div className="form-span-two"><button disabled={busy}>新增案例</button></div></form><div className="case-stack">{cases.map(item => <article className="case-item" key={item.id}><div className="section-heading-row"><h3>{item.title}</h3><Link className="secondary-btn" href={`/admin/partners/${id}/cases/${item.id}/sharing`}>共享设置</Link><button disabled={busy} className="secondary-btn danger-outline" onClick={() => deleteCase(item.id)}>删除案例</button></div><p>{item.description || "暂无描述"}</p><div className="deliverable-pills">{(deliverables[item.id] || []).map(file => <span key={file.id}>{file.filename}<button disabled={busy} title="删除交付物" onClick={() => deleteDeliverable(item.id, file.id)}>×</button></span>)}</div><label className="upload-btn small">上传交付物<input hidden type="file" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (file) void uploadDeliverable(item.id, file); event.target.value = ""; }} /></label></article>)}</div></section></>}
  </main>;
}
