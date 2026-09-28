"use client";
import {ClassificationNotice} from "@/components/business-taxonomy";


import Link from "next/link";
import { use, useEffect, useState } from "react";
import { apiFetch } from "../../../components/auth-provider";

import { PartnerSharedCases } from "@/components/enablement-workspace";
import { PartnerTagList } from "@/components/partner-tag-list";

type Partner = { classification_pending?: Record<string,string[]>; id: string; name: string; intro: string | null; capabilities: string | null; service_areas: string | null; industries: string | null; ai_profile: string | null; created_at: string };
export default function PartnerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [partner, setPartner] = useState<Partner | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiFetch(`/partners/${id}`,{cache:'no-store'}).then(async response=>{if(!response.ok)throw new Error('伙伴不存在或无权访问');setPartner(await response.json());}).catch(reason=>setError(reason instanceof Error?reason.message:'加载失败'));
  }, [id]);
  if (error) return <main className="page"><section className="card empty-state"><h1>无法查看伙伴</h1><p className="error-text">{error}</p><Link href="/partners" className="btn-primary-lg">返回伙伴洞察</Link></section></main>;
  if (!partner) return <main className="page"><p>伙伴信息加载中...</p></main>;
  return (
    <main className="page partner-profile-page">
      <div className="page-heading-row"><div><p className="eyebrow">Partner Detail</p><h1>{partner.name}</h1><p className="lead">{partner.intro || "暂无伙伴简介"}</p></div><div className="enablement-actions"><Link href={`/?mode=development&partner_id=${encodeURIComponent(id)}`} className="secondary-btn">制定发展建议</Link><Link href="/partners" className="secondary-btn">返回伙伴洞察</Link></div></div>
      <section className="card"><h2>能力概览</h2><ClassificationNotice pending={partner.classification_pending}/><div className="detail-grid"><div><span>正式能力标签</span><PartnerTagList value={partner.capabilities} label="正式能力标签" emptyText="未完善" /></div><div><span>行业经验</span><PartnerTagList value={partner.industries} label="行业经验" emptyText="未完善" /></div><div><span>服务区域</span><PartnerTagList value={partner.service_areas} label="服务区域" emptyText="未完善" /></div><div><span>收录时间</span><strong>{new Date(partner.created_at).toLocaleDateString("zh-CN")}</strong></div></div></section>
      <PartnerSharedCases partnerId={id}/><div className="notice-neutral">伙伴原始资料由平台管理员统一维护，普通用户侧仅展示经过整理的正式信息。</div>
    </main>
  );
}
