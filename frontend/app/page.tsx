"use client";

import { useState } from "react";
import { HealthStatus } from "../components/health-status";

type Recommendation = {
  partnerId: string;
  partnerName: string;
  matchScore: number;
  matchedCapabilities: string;
  matchedIndustries: string;
  matchedRegions: string;
  recommendationReason: string;
  evidenceCases: string;
  evidenceDeliverables: string;
  riskNotes: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function HomePage() {
  const [requirement, setRequirement] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleMatch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/agent/match`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requirement }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setRecommendations(data.recommendations || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "匹配失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <p className="eyebrow">Delivery Partner Intelligence</p>
      <h1>灵鉴 Agent 工作台</h1>
      <p className="lead">归集伙伴档案、项目案例与交付物，形成可信的能力画像，并基于项目需求推荐合适的交付伙伴。</p>

      <section className="card">
        <h2>伙伴智能匹配</h2>
        <form onSubmit={handleMatch} className="match-form">
          <div className="form-row">
            <label htmlFor="requirement">项目需求</label>
            <textarea id="requirement" value={requirement} onChange={(e) => setRequirement(e.target.value)} required rows={4} placeholder="描述你的项目需求，如：需要一个有金融行业经验的Java全栈团队，负责银行核心系统重构" />
          </div>
          <button type="submit" disabled={loading}>{loading ? "匹配中..." : "智能匹配"}</button>
        </form>
        {error && <p className="error-text">{error}</p>}
      </section>

      {recommendations.length > 0 && (
        <section className="card">
          <h2>推荐结果</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "20px", marginTop: "16px" }}>
            {recommendations.map((r, i) => (
              <div key={i} className="case-item">
                <div className="rec-header">
                  <h3><a href={`/partners/${r.partnerId}`}>{r.partnerName}</a></h3>
                  <span className="score-tag">匹配度: {r.matchScore}</span>
                </div>
                {r.matchedCapabilities && (
                  <div style={{ marginTop: "8px" }}>
                    <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginRight: "8px" }}>匹配能力</span>
                    <span style={{ fontSize: "13px" }}>{r.matchedCapabilities}</span>
                  </div>
                )}
                {r.matchedIndustries && (
                  <div style={{ marginTop: "6px" }}>
                    <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginRight: "8px" }}>匹配行业</span>
                    <span style={{ fontSize: "13px" }}>{r.matchedIndustries}</span>
                  </div>
                )}
                {r.matchedRegions && (
                  <div style={{ marginTop: "6px" }}>
                    <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginRight: "8px" }}>匹配区域</span>
                    <span style={{ fontSize: "13px" }}>{r.matchedRegions}</span>
                  </div>
                )}
                <dl className="rec-detail" style={{ marginTop: "8px" }}>
                  <dt>推荐理由</dt><dd>{r.recommendationReason}</dd>
                  <dt>支撑案例</dt><dd>{r.evidenceCases || "无"}</dd>
                  <dt>支撑交付物</dt><dd>{r.evidenceDeliverables || "无"}</dd>
                  <dt>风险提示</dt><dd>{r.riskNotes || "无"}</dd>
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="dashboard-grid" aria-label="工作台概览">
        <HealthStatus />
      </section>
    </main>
  );
}