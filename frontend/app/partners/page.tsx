"use client";

import { useState } from "react";

type Partner = {
  id: string;
  name: string;
  intro: string | null;
  capabilities: string | null;
  service_areas: string | null;
  industries: string | null;
  created_at: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function PartnersPage() {
  const [partners, setPartners] = useState<Partner[]>([]);
  const [name, setName] = useState("");
  const [intro, setIntro] = useState("");
  const [capabilities, setCapabilities] = useState("");
  const [serviceAreas, setServiceAreas] = useState("");
  const [industries, setIndustries] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPartners() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/partners`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setPartners(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/partners`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          intro: intro || null,
          capabilities: capabilities || null,
          service_areas: serviceAreas || null,
          industries: industries || null,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setName("");
      setIntro("");
      setCapabilities("");
      setServiceAreas("");
      setIndustries("");
      await loadPartners();
    } catch (e) {
      setError(e instanceof Error ? e.message : "新增失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <p className="eyebrow">Partner Management</p>
      <h1>伙伴资料管理</h1>
      <p className="lead">维护伙伴基础信息、能力标签、服务区域、行业经验、案例与交付物。</p>

      <section className="card">
        <h2>新增伙伴</h2>
        <form onSubmit={handleSubmit} className="partner-form">
          <div className="form-row">
            <label htmlFor="name">名称</label>
            <input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} placeholder="伙伴名称" />
          </div>
          <div className="form-row">
            <label htmlFor="intro">简介</label>
            <textarea id="intro" value={intro} onChange={(e) => setIntro(e.target.value)} placeholder="选填" rows={3} />
          </div>
          <div className="form-row">
            <label htmlFor="capabilities">能力标签</label>
            <input id="capabilities" type="text" value={capabilities} onChange={(e) => setCapabilities(e.target.value)} placeholder="逗号分隔，如 Java,React,DevOps" />
          </div>
          <div className="form-row">
            <label htmlFor="serviceAreas">服务区域</label>
            <input id="serviceAreas" type="text" value={serviceAreas} onChange={(e) => setServiceAreas(e.target.value)} placeholder="逗号分隔，如 华东,华北" />
          </div>
          <div className="form-row">
            <label htmlFor="industries">行业经验</label>
            <input id="industries" type="text" value={industries} onChange={(e) => setIndustries(e.target.value)} placeholder="逗号分隔，如 金融,制造" />
          </div>
          <button type="submit" disabled={loading}>{loading ? "提交中..." : "新增"}</button>
        </form>
        {error && <p className="error-text">{error}</p>}
      </section>

      <section className="card">
        <h2>伙伴列表</h2>
        <button onClick={loadPartners} disabled={loading} className="secondary-btn">刷新列表</button>
        {partners.length === 0 ? (
          <p className="placeholder-text">暂无伙伴，点击刷新或新增。</p>
        ) : (
          <ul className="partner-list">
            {partners.map((p) => (
              <li key={p.id}>
                <a href={`/partners/${p.id}`}>{p.name}</a>
                {p.intro && <span className="partner-intro"> — {p.intro}</span>}
                {p.capabilities && <span className="partner-tag">能力: {p.capabilities}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
