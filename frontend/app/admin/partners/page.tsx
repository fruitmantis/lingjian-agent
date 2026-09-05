"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../../../components/auth-provider";

type Partner = { id: string; name: string; intro: string | null; capabilities: string | null; service_areas: string | null; industries: string | null; ai_profile: string | null; status: "active" | "disabled"; created_at: string };

export default function AdminPartnersPage() {
  const [partners, setPartners] = useState<Partner[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [batchLoading, setBatchLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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
      const response = await apiFetch("/partners", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "新增失败");
      setName(""); await load();
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
  async function batchGenerate() {
    if (!confirm(`将为 ${partners.filter(item => item.status === "active").length} 家启用伙伴依次生成 AI 画像，可能产生模型调用费用。确定继续？`)) return;
    setBatchLoading(true); setMessage(null); setError(null);
    try {
      const response = await apiFetch("/partners/batch-profile", {
        method: "POST",
        timeoutMs: Math.max(1, partners.filter(item => item.status === "active").length) * 180_000 + 30_000,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "批量生成失败");
      setMessage(`批量生成完成：成功 ${data.success}，失败 ${data.failed}`); await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量生成失败");
    } finally {
      setBatchLoading(false);
    }
  }
  return (
    <main className="page"><p className="eyebrow">Partner Management</p><h1>伙伴管理</h1><p className="lead">维护伙伴基础信息、资料、案例和 AI 画像。</p>
      <section className="card"><h2>新增伙伴</h2><form onSubmit={create} className="inline-search"><input value={name} onChange={event => setName(event.target.value)} placeholder="伙伴名称" required maxLength={200} /><button>新增伙伴</button></form></section>
      <section className="card"><div className="section-heading-row"><h2>伙伴列表</h2><div className="table-actions"><span className="result-count">共 {partners.length} 家</span><button onClick={batchGenerate} disabled={batchLoading}>{batchLoading ? "批量生成中..." : "批量生成画像"}</button></div></div>{message && <p className="success-text">{message}</p>}{error && <div className="inline-error-actions"><p className="error-text">{error}</p><button className="secondary-btn" onClick={() => void load()}>重试</button></div>}{loading ? <p>加载中...</p> : <div className="table-wrap"><table className="data-table"><thead><tr><th>伙伴名称</th><th>能力标签</th><th>行业经验</th><th>画像状态</th><th>伙伴状态</th><th>操作</th></tr></thead><tbody>{partners.map(partner => <tr key={partner.id}><td>{partner.name}</td><td>{partner.capabilities || "-"}</td><td>{partner.industries || "-"}</td><td>{partner.ai_profile ? "已生成" : "待生成"}</td><td><span className={`status-badge ${partner.status}`}>{partner.status === "active" ? "启用" : "停用"}</span></td><td><div className="table-actions"><Link href={`/admin/partners/${partner.id}`} className="secondary-btn">维护</Link><button className="secondary-btn" onClick={() => toggle(partner)}>{partner.status === "active" ? "停用" : "启用"}</button></div></td></tr>)}</tbody></table></div>}</section>
    </main>
  );
}
