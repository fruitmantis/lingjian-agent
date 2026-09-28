"use client";


import { CardEntry } from "../../components/card-entry";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../components/auth-provider";
import { PartnerTagList, splitPartnerTags } from "../../components/partner-tag-list";
import { MultiSelectFilter, OpportunityFilter } from "../../components/opportunity-ui";
import { standardValues } from "../../components/business-taxonomy";

type PartnerCard = {
  id: string; name: string; capabilities: string | null; service_areas: string | null;
  industries: string | null; ai_profile: string | null; case_count: number; deliverable_count: number;
};

export default function PartnersPage() {
  const [partners, setPartners] = useState<PartnerCard[]>([]);
  const [keyword, setKeyword] = useState("");
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [industries, setIndustries] = useState("");
  const [regions, setRegions] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiFetch("/partners/profiles", { cache: "no-store" }).then(async response => {
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "伙伴加载失败");
      setPartners(await response.json());
    }).catch(reason => setError(reason instanceof Error ? reason.message : "伙伴加载失败")).finally(() => setLoading(false));
  }, []);
  const capabilityOptions = useMemo(() => [...new Set(partners.flatMap(partner => splitPartnerTags(partner.capabilities)))].sort((a, b) => a.localeCompare(b, "zh-CN")), [partners]);
  const filtered = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    const selectedIndustries = standardValues(industries, "industry"), selectedRegions = standardValues(regions, "region");
    const matches = (selected: string[], values: string[]) => !selected.length || selected.some(value => values.includes(value));
    return partners.filter(partner =>
      (!key || [partner.name, partner.capabilities, partner.service_areas, partner.industries].some(value => value?.toLowerCase().includes(key))) &&
      matches(capabilities, splitPartnerTags(partner.capabilities)) &&
      matches(selectedIndustries, standardValues(partner.industries || "", "industry")) &&
      matches(selectedRegions, standardValues(partner.service_areas || "", "region"))
    );
  }, [keyword, partners, capabilities, industries, regions]);
  const hasFilters = !!(capabilities.length || industries || regions);
  function clearFilters() { setCapabilities([]); setIndustries(""); setRegions(""); }
  return (
    <main className="page">
      <p className="eyebrow">Partner Insights</p><h1>伙伴洞察</h1><p className="lead">浏览经过平台整理的伙伴能力、行业经验和案例信息。</p>
      <section className="partner-search-toolbar"><div className="inline-search partner-search"><input aria-label="搜索伙伴" value={keyword} onChange={event => setKeyword(event.target.value)} placeholder="搜索伙伴名称、能力、行业或区域" /></div><span className="result-count" role="status">{loading ? "正在读取伙伴…" : error ? "" : `共 ${filtered.length} 家伙伴`}</span></section>
      {!loading && !error && <section className="partner-filter-toolbar" aria-label="伙伴筛选">
        <MultiSelectFilter label="能力标签" selected={capabilities} groups={[{name: "能力标签", values: capabilityOptions}]} onChange={setCapabilities} searchable compact/>
        <OpportunityFilter kind="industry" value={industries} onChange={setIndustries} compact/>
        <OpportunityFilter kind="region" value={regions} onChange={setRegions} compact/>
        {hasFilters && <button type="button" className="partner-filter-clear" onClick={clearFilters}>清除筛选</button>}
      </section>}
      {loading ? <section className="card"><p>加载中...</p></section> : error ? <section className="card"><p className="error-text">{error}</p></section> : (
        filtered.length ? <section className="partner-insight-grid">{filtered.map(partner => <article className="card partner-insight-card" key={partner.id}>
          <div className="partner-card-heading"><div><span className="partner-avatar">{partner.name.slice(0, 1)}</span><h2>{partner.name}</h2></div><span className={`profile-state ${partner.ai_profile ? "ready" : ""}`}>{partner.ai_profile ? "画像已完善" : "画像待完善"}</span></div>
          <div className="partner-field"><span>能力标签</span><PartnerTagList value={partner.capabilities} label="能力标签" emptyText="暂无正式能力标签" compact /></div>
          <div className="partner-field"><span>行业</span><PartnerTagList value={partner.industries} label="行业" emptyText="暂无行业信息" compact /></div>
          <div className="partner-field"><span>区域</span><PartnerTagList value={partner.service_areas} label="区域" emptyText="暂无区域信息" compact /></div>
          <div className="partner-card-footer"><span>{partner.case_count} 个案例 · {partner.deliverable_count} 个交付物</span><CardEntry href={`/partners/${partner.id}`} /></div>
        </article>)}</section> : <section className="card empty-state"><h2>暂无符合条件的伙伴</h2><p>试试其他筛选条件或搜索词。</p>{(hasFilters || keyword) && <button type="button" className="secondary-btn" onClick={() => {clearFilters(); setKeyword("");}}>重置筛选与搜索</button>}</section>
      )}
    </main>
  );
}
