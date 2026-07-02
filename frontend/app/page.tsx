"use client";

import { useState, useEffect, useRef } from "react";
import { HealthStatus } from "../components/health-status";

type Recommendation = {
  partnerId: string;
  partnerName: string;
  matchScore: string;
  matchedCapabilities: string;
  matchedIndustries: string;
  matchedRegions: string;
  recommendationReason: string;
  evidenceCases: string;
  evidenceDeliverables: string;
  riskNotes: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const LOADING_STAGES = [
  "正在理解项目需求...",
  "正在检索伙伴画像...",
  "正在分析匹配关系...",
  "正在生成推荐理由...",
];

function getRecommendLevel(score: string): { label: string; color: string } {
  const num = parseInt(score) || 0;
  if (num >= 80) return { label: "强烈推荐", color: "var(--brand)" };
  if (num >= 60) return { label: "推荐", color: "#e8a317" };
  if (num >= 30) return { label: "可考虑", color: "var(--muted)" };
  return { label: "不推荐", color: "var(--danger)" };
}

function InfoRow({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div style={{ display: "flex", gap: "8px", marginTop: "6px" }}>
      <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, minWidth: "70px", flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: "13px", lineHeight: 1.6 }}>{value}</span>
    </div>
  );
}

export default function HomePage() {
  const [requirement, setRequirement] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => { if (stageTimer.current) clearInterval(stageTimer.current); };
  }, []);

  async function handleMatch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setHasSearched(true);
    setRecommendations([]);
    setLoadingStage(0);

    // Rotate loading stages every 4 seconds
    stageTimer.current = setInterval(() => {
      setLoadingStage(prev => Math.min(prev + 1, LOADING_STAGES.length - 1));
    }, 4000);

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
      if (stageTimer.current) { clearInterval(stageTimer.current); stageTimer.current = null; }
      setLoading(false);
    }
  }

  const top3 = recommendations.slice(0, 3);

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

      {/* Loading state */}
      {loading && (
        <section className="card">
          <h2>智能匹配进行中</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "16px" }}>
            {LOADING_STAGES.map((stage, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={{
                  width: "20px", height: "20px", borderRadius: "50%",
                  border: "2px solid",
                  borderColor: i < loadingStage ? "var(--success)" : i === loadingStage ? "var(--brand)" : "var(--line)",
                  background: i < loadingStage ? "var(--success)" : "transparent",
                  flexShrink: 0,
                }} />
                <span style={{
                  fontSize: "14px",
                  color: i <= loadingStage ? "var(--ink)" : "var(--muted)",
                  fontWeight: i === loadingStage ? 600 : 400,
                }}>{stage}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Empty state */}
      {!loading && hasSearched && !error && top3.length === 0 && (
        <section className="card">
          <h2>推荐结果</h2>
          <p className="placeholder-text" style={{ marginTop: "12px" }}>未找到匹配的伙伴，请尝试调整需求描述。</p>
        </section>
      )}

      {/* Results */}
      {!loading && top3.length > 0 && (
        <>
          {/* Requirement analysis */}
          <section className="card">
            <h2>项目需求解析</h2>
            <div style={{ marginTop: "12px", padding: "16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
              <p style={{ fontSize: "14px", lineHeight: 1.8, margin: 0, whiteSpace: "pre-wrap" }}>{requirement}</p>
            </div>
            <p style={{ fontSize: "13px", color: "var(--muted)", marginTop: "8px" }}>共检索到 {recommendations.length} 个候选伙伴，展示推荐前 {top3.length} 名</p>
          </section>

          {/* Top 3 recommendations */}
          <section className="card">
            <h2>推荐伙伴 Top {top3.length}</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "20px", marginTop: "16px" }}>
              {top3.map((r, i) => {
                const level = getRecommendLevel(r.matchScore);
                return (
                  <div key={i} className="case-item" style={{ position: "relative" }}>
                    {/* Rank badge */}
                    <div style={{
                      position: "absolute", top: "-8px", left: "16px",
                      width: "28px", height: "28px", borderRadius: "50%",
                      background: i === 0 ? "var(--brand)" : i === 1 ? "#e8a317" : "var(--muted)",
                      color: "white", fontSize: "14px", fontWeight: 700,
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}>{i + 1}</div>

                    <div style={{ marginTop: "8px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                        <h3><a href={`/partners/${r.partnerId}`}>{r.partnerName}</a></h3>
                        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                          <span style={{
                            padding: "3px 10px", borderRadius: "999px", fontSize: "12px", fontWeight: 600,
                            background: `${level.color}15`, color: level.color, border: `1px solid ${level.color}40`,
                          }}>{level.label}</span>
                          <span className="score-tag">匹配度: {r.matchScore}</span>
                        </div>
                      </div>

                      <InfoRow label="推荐理由" value={r.recommendationReason} />
                      <InfoRow label="命中能力" value={r.matchedCapabilities} />
                      <InfoRow label="命中行业" value={r.matchedIndustries} />
                      <InfoRow label="命中区域" value={r.matchedRegions} />
                      <InfoRow label="支撑案例" value={r.evidenceCases} />
                      <InfoRow label="支撑交付物" value={r.evidenceDeliverables} />
                      <InfoRow label="风险提示" value={r.riskNotes} />
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}

      <section className="dashboard-grid" aria-label="工作台概览">
        <HealthStatus />
      </section>
    </main>
  );
}