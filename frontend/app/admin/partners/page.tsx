"use client";
import {ClassificationFields} from "@/components/business-taxonomy";


import Link from "next/link";
import { FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { adminApiFetch as apiFetch } from "../../../components/auth-provider";

type Partner = { id: string; name: string; intro: string | null; capabilities: string | null; service_areas: string | null; industries: string | null; ai_profile: string | null; status: "active" | "disabled"; created_at: string; profile_needs_update?: boolean; profile_status?: string };

function closeDisclosure(node:HTMLElement|null) {
  const details=node?.closest("details");
  if(!details)return;
  details.removeAttribute("open");details.querySelector<HTMLElement>("summary")?.focus();
}
function disclosureKey(event:KeyboardEvent<HTMLElement>) {
  if(event.key==="Escape"&&!event.defaultPrevented&&event.currentTarget.hasAttribute("open")){
    event.preventDefault();event.stopPropagation();closeDisclosure(event.currentTarget);
  }
}

export default function AdminPartnersPage() {
  const [partners, setPartners] = useState<Partner[]>([]);
  const [name, setName] = useState("");
  const [industries,setIndustries]=useState(""),[regions,setRegions]=useState("");
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transferBusy, setTransferBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  async function download(template = false) {
    setTransferBusy(true); setError(null); setMessage(null);
    try {
      const response = await apiFetch(`/partners/${template ? 'template' : 'export'}`);
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || '下载失败，请稍后重试');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url;
      link.download = template ? '伴飞伙伴导入模板.xlsx' : '伴飞伙伴信息.xlsx';
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage(template ? '模板已下载，按表头和使用说明填写后导入。' : '全部伙伴信息已导出，不含案例和附件。');
    } catch (reason) { setError(reason instanceof Error ? reason.message : '下载失败'); }
    finally { setTransferBusy(false); }
  }
  async function upload(file: File) {
    setError(null); setMessage(null);
    if (!file.name.toLowerCase().endsWith('.xlsx') || file.size > 10 * 1024 * 1024) {
      setError('请选择不超过10MB的.xlsx文件。'); return;
    }
    if (!confirm('按表格新增或更新伙伴信息和完整画像，空白可选字段会清空原内容。相同ID或唯一同名伙伴会更新；案例与附件保持原样。确认导入？')) return;
    setTransferBusy(true);
    try {
      const body = new FormData(); body.append('file', file);
      const response = await apiFetch('/partners/import', {method: 'POST', body, timeoutMs: 120_000});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '导入失败，请检查表格内容');
      await load();
      setMessage(`导入完成：新增 ${data.created} 家，更新 ${data.updated} 家，未变化 ${data.unchanged} 家。`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '导入失败'); }
    finally { setTransferBusy(false); }
  }
  async function load() {
    setLoading(true); setError(null);
    try {
      const response = await apiFetch("/partners?include_disabled=true", { cache: "no-store" });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "伙伴加载失败");
      setPartners(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "伙伴加载失败");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { void load(); }, []);
  async function create(event: FormEvent) {
    event.preventDefault(); setError(null);
    try {
      const response = await apiFetch("/partners", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, industries, service_areas:regions }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "新增失败");
      setName(""); setIndustries(""); setRegions(""); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "新增失败"); }
  }
  async function toggle(partner: Partner) {
    setError(null);
    try {
      const response = await apiFetch(`/partners/${partner.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: partner.status === "active" ? "disabled" : "active" }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "状态修改失败");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "状态修改失败"); }
  }
  async function remove(partner: Partner) {
    if (!confirm(`确定删除“${partner.name}”？删除后无法恢复；有业务历史的伙伴只能停用。`)) return;
    setDeletingId(partner.id); setError(null); setMessage(null);
    try {
      const response = await apiFetch(`/partners/${partner.id}`, { method: "DELETE" });
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))).detail;
        throw new Error(typeof detail === "string" ? detail : detail?.message || "删除失败，请稍后重试");
      }
      setPartners(current => current.filter(item => item.id !== partner.id));
      setMessage("伙伴已删除");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败，请稍后重试");
    } finally {
      setDeletingId(null);
    }
  }
  async function batchGenerate() {
    if (!confirm(`将为 ${partners.filter(item => item.status === "active").length} 家启用伙伴刷新画像状态；正文需在伙伴详情点击整理画像。确定继续？`)) return;
    setBatchLoading(true); setMessage(null); setError(null);
    try {
      const response = await apiFetch("/partners/batch-profile", {
        method: "POST",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "批量刷新状态失败");
      setMessage(`批量刷新状态完成：成功 ${data.success}，失败 ${data.failed}`); await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量刷新状态失败");
    } finally {
      setBatchLoading(false);
    }
  }
  return (
    <main className="page admin-partners-page"><p className="eyebrow">Partner Management</p><h1>伙伴管理</h1><p className="lead">维护伙伴基础信息、资料、案例和 AI 画像。</p>
      <div className="partner-admin-tools"><details className="partner-admin-disclosure" onKeyDown={disclosureKey}><summary>Excel 导入导出</summary><div className="card partner-admin-editor"><div className="section-heading-row"><div><h2>Excel 导入导出</h2><p className="muted">包含全部伙伴的基础信息、分类、状态和完整画像，不含案例与附件。</p></div><div className="table-actions">
        <button className="secondary-btn" disabled={transferBusy || batchLoading} onClick={() => void download()}>导出全部 Excel</button>
        <button className="secondary-btn" disabled={transferBusy || batchLoading} onClick={() => void download(true)}>下载导入模板</button>
        <button disabled={transferBusy || batchLoading} onClick={() => fileInput.current?.click()}>{transferBusy ? '处理中…' : '导入 Excel'}</button>
        <input ref={fileInput} type="file" hidden accept=".xlsx" aria-label="导入伙伴Excel文件" onChange={e => {const file = e.target.files?.[0]; e.target.value = ''; if (file) void upload(file);}}/>
      </div></div></div></details>
      <details className="partner-admin-disclosure" onKeyDown={disclosureKey}><summary>新增伙伴</summary><div className="card partner-admin-editor"><h2>新增伙伴</h2><form onSubmit={create} className="form-grid"><label className="enablement-field" htmlFor="new-partner-name">伙伴名称<input id="new-partner-name" value={name} onChange={event => setName(event.target.value)} placeholder="伙伴名称" required maxLength={200} /></label><ClassificationFields industries={industries} regions={regions} onIndustries={setIndustries} onRegions={setRegions}/><div className="table-actions"><button>新增伙伴</button><button type="button" className="secondary-btn" onClick={event=>closeDisclosure(event.currentTarget)}>取消</button></div></form></div></details></div>
      <section className="card"><div className="section-heading-row"><h2>伙伴列表</h2><div className="table-actions"><span className="result-count">共 {partners.length} 家</span><details className="advisor-more partner-list-menu" onKeyDown={disclosureKey}><summary>更多操作</summary><div className="advisor-menu" onClick={event=>{if((event.target as HTMLElement).closest("button"))closeDisclosure(event.currentTarget);}}><button className="secondary-btn" onClick={batchGenerate} disabled={batchLoading}>{batchLoading ? "批量刷新状态中..." : "批量刷新状态画像"}</button></div></details></div></div>{transferBusy&&<p className="muted" role="status">正在处理伙伴导入或导出…</p>}{batchLoading&&<p className="muted" role="status">正在刷新伙伴画像状态…</p>}{message && <p className="success-text">{message}</p>}{error && <div className="inline-error-actions"><p className="error-text" role="alert">{error}</p><button className="secondary-btn" onClick={() => void load()}>重试</button></div>}{loading ? <p>加载中...</p> : <div className="table-wrap"><table className="data-table"><thead><tr><th>伙伴名称</th><th>能力标签</th><th>行业经验</th><th>画像状态</th><th>伙伴状态</th><th>操作</th></tr></thead><tbody>{partners.map(partner => <tr key={partner.id}><td>{partner.name}</td><td>{partner.capabilities || "-"}</td><td>{partner.industries || "-"}</td><td>{partner.profile_needs_update ? "待整理" : partner.profile_status === "missing" ? "暂无资料" : "已整理"}</td><td><span className={`status-badge ${partner.status}`}>{partner.status === "active" ? "启用" : "停用"}</span></td><td><div className="table-actions"><Link href={`/admin/partners/${partner.id}`} className="secondary-btn">维护</Link><button className="secondary-btn" onClick={() => toggle(partner)}>{partner.status === "active" ? "停用" : "启用"}</button><button className="secondary-btn danger-outline" disabled={deletingId !== null} onClick={() => remove(partner)}>{deletingId === partner.id ? "删除中..." : "删除"}</button></div></td></tr>)}</tbody></table></div>}</section>
    </main>
  );
}
