"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { apiFetch } from "../../../components/auth-provider";

import { PartnerSharedCases } from "@/components/enablement-workspace";

type Partner = { id: string; name: string; intro: string | null; capabilities: string | null; service_areas: string | null; industries: string | null; ai_profile: string | null; created_at: string };
type PartnerCase = { id: string; title: string; description: string | null; created_at: string };
type Deliverable = { id: string; filename: string; created_at: string };

export default function PartnerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [partner, setPartner] = useState<Partner | null>(null);
  const [cases, setCases] = useState<PartnerCase[]>([]);
  const [deliverables, setDeliverables] = useState<Record<string, Deliverable[]>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([apiFetch(`/partners/${id}`, { cache: "no-store" }), apiFetch(`/cases/by-partner/${id}`, { cache: "no-store" })]).then(async ([partnerResponse, caseResponse]) => {
      if (!partnerResponse.ok || !caseResponse.ok) throw new Error("伙伴不存在或无权访问");
      const partnerData = await partnerResponse.json();
      const caseData = await caseResponse.json() as PartnerCase[];
      setPartner(partnerData); setCases(caseData);
      const pairs = await Promise.all(caseData.map(async item => {
        const response = await apiFetch(`/cases/${item.id}/deliverables`, { cache: "no-store" });
        return [item.id, response.ok ? await response.json() : []] as const;
      }));
      setDeliverables(Object.fromEntries(pairs));
    }).catch(reason => setError(reason instanceof Error ? reason.message : "加载失败"));
  }, [id]);
  if (error) return <main className="page"><section className="card empty-state"><h1>无法查看伙伴</h1><p className="error-text">{error}</p><Link href="/partners" className="btn-primary-lg">返回伙伴洞察</Link></section></main>;
  if (!partner) return <main className="page"><p>伙伴信息加载中...</p></main>;
  return (
    <main className="page">
      <div className="page-heading-row"><div><p className="eyebrow">Partner Detail</p><h1>{partner.name}</h1><p className="lead">{partner.intro || "暂无伙伴简介"}</p></div><div className="enablement-actions"><Link href={`/?mode=development&partner_id=${encodeURIComponent(id)}`} className="secondary-btn">制定发展建议</Link><Link href="/partners" className="secondary-btn">返回伙伴洞察</Link></div></div>
      <section className="card"><h2>能力概览</h2><div className="detail-grid"><div><span>正式能力标签</span><strong>{partner.capabilities || "未完善"}</strong></div><div><span>行业经验</span><strong>{partner.industries || "未完善"}</strong></div><div><span>服务区域</span><strong>{partner.service_areas || "未完善"}</strong></div><div><span>收录时间</span><strong>{new Date(partner.created_at).toLocaleDateString("zh-CN")}</strong></div></div></section>
      <section className="card card-highlight"><h2>AI 能力画像</h2>{partner.ai_profile ? <pre className="ai-profile-text">{partner.ai_profile}</pre> : <p className="placeholder-text">管理员尚未生成该伙伴的 AI 能力画像。</p>}</section>
      <section className="card"><h2>伙伴案例与交付物</h2>{cases.length === 0 ? <p className="placeholder-text">暂无公开案例。</p> : <div className="case-stack">{cases.map(item => <article className="case-item" key={item.id}><h3>{item.title}</h3><p>{item.description || "暂无案例描述"}</p>{(deliverables[item.id] || []).length > 0 && <div className="deliverable-pills">{deliverables[item.id].map(deliverable => <span key={deliverable.id}>{deliverable.filename}</span>)}</div>}</article>)}</div>}</section>
      <PartnerSharedCases partnerId={id}/><div className="notice-neutral">伙伴原始资料由平台管理员统一维护，普通用户侧仅展示经过整理的正式信息。</div>
    </main>
  );
}
