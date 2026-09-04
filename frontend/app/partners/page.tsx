"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../components/auth-provider";

type PartnerCard = {
  id: string; name: string; capabilities: string | null; service_areas: string | null;
  industries: string | null; ai_profile: string | null; case_count: number; deliverable_count: number;
};

export default function PartnersPage() {
  const [partners, setPartners] = useState<PartnerCard[]>([]);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiFetch("/partners/profiles", { cache: "no-store" }).then(async response => {
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "伙伴加载失败");
      setPartners(await response.json());
    }).catch(reason => setError(reason instanceof Error ? reason.message : "伙伴加载失败")).finally(() => setLoading(false));
  }, []);
  const filtered = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    if (!key) return partners;
    return partners.filter(partner => [partner.name, partner.capabilities, partner.service_areas, partner.industries].some(value => value?.toLowerCase().includes(key)));
  }, [keyword, partners]);
  return (
    <main className="page">
      <p className="eyebrow">Partner Insights</p><h1>伙伴洞察</h1><p className="lead">浏览经过平台整理的伙伴能力、行业经验和案例信息。</p>
      <section className="card toolbar-card"><div className="inline-search partner-search"><input value={keyword} onChange={event => setKeyword(event.target.value)} placeholder="搜索伙伴名称、能力、行业或区域" /></div><span className="result-count">共 {filtered.length} 家伙伴</span></section>
      {loading ? <section className="card"><p>加载中...</p></section> : error ? <section className="card"><p className="error-text">{error}</p></section> : (
        <section className="partner-insight-grid">{filtered.map(partner => <article className="card partner-insight-card" key={partner.id}>
          <div className="partner-card-heading"><div><span className="partner-avatar">{partner.name.slice(0, 1)}</span><h2>{partner.name}</h2></div><span className={`profile-state ${partner.ai_profile ? "ready" : ""}`}>{partner.ai_profile ? "画像已完善" : "画像待完善"}</span></div>
          <div className="partner-field"><span>能力标签</span><p>{partner.capabilities || "暂无正式能力标签"}</p></div>
          <div className="partner-field"><span>行业经验</span><p>{partner.industries || "暂无行业信息"}</p></div>
          <div className="partner-field"><span>覆盖区域</span><p>{partner.service_areas || "暂无区域信息"}</p></div>
          <div className="partner-card-footer"><span>{partner.case_count} 个案例 · {partner.deliverable_count} 个交付物</span><Link href={`/partners/${partner.id}`}>查看详情 →</Link></div>
        </article>)}</section>
      )}
    </main>
  );
}
