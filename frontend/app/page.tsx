"use client";

import { useState, useEffect, useRef } from "react";

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
  "正在分析伙伴画像...",
  "正在匹配交付能力...",
  "正在生成推荐依据...",
];

function getRecommendLevel(score: string): { label: string; color: string; bg: string } {
  const num = parseInt(score) || 0;
  if (num >= 80) return { label: "强推荐", color: "var(--brand)", bg: "#fff1f2" };
  if (num >= 50) return { label: "可考虑", color: "#e8a317", bg: "#fffbeb" };
  if (num >= 20) return { label: "备选", color: "var(--muted)", bg: "#f8f9fa" };
  return { label: "不推荐", color: "var(--danger)", bg: "#fef2f2" };
}

function parseTags(val: string): string[] {
  if (!val) return [];
  return val.split(/[,，]/).map(t => t.trim()).filter(Boolean);
}

function copyToClipboard(text: string) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text);
  } else {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

function buildCopyText(req: string, r: Recommendation, rank: number): string {
  const level = getRecommendLevel(r.matchScore);
  const lines = [
    `【推荐排名】第${rank}名`,
    `【伙伴名称】${r.partnerName}`,
    `【匹配度】${r.matchScore}`,
    `【推荐等级】${level.label}`,
    `【推荐理由】${r.recommendationReason || "暂无"}`,
    `【命中能力】${r.matchedCapabilities || "无"}`,
    `【命中行业】${r.matchedIndustries || "无"}`,
    `【命中区域】${r.matchedRegions || "无"}`,
    `【支撑案例】${r.evidenceCases || "暂无支撑案例"}`,
    `【支撑交付物】${r.evidenceDeliverables || "暂无交付物证据"}`,
    `【风险/缺口】${r.riskNotes || "暂无"}`,
    `【项目需求】${req}`,
  ];
  return lines.join("\n");
}

function TagPills({ tags, color, bg, border }: { tags: string[]; color: string; bg: string; border: string }) {
  if (tags.length === 0) return <span style={{ fontSize: "13px", color: "var(--muted)" }}>无</span>;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
      {tags.map((tag, i) => (
        <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: bg, color, border: `1px solid ${border}`, fontWeight: 500 }}>{tag}</span>
      ))}
    </div>
  );
}

export default function HomePage() {
  const [stats, setStats] = useState({totalPartners: 0, withProfile: 0, totalMatches: 0, pendingSuggestions: 0});
  const [requirement, setRequirement] = useState("");
  const [submittedRequirement, setSubmittedRequirement] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [copiedRank, setCopiedRank] = useState<number | null>(null);
  const [matchRecords, setMatchRecords] = useState<{ id: string; requirement: string; topPartner: string; partnerCount: number; createdAt: string }[]>([]);
  const [viewingHistory, setViewingHistory] = useState(false);
  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    loadMatchRecords();
    loadDashboardStats();
    return () => { if (stageTimer.current) clearInterval(stageTimer.current); };
  }, []);

  async function loadMatchRecords() {
    try {
      const res = await fetch(`${apiBaseUrl}/agent/match-records`, { cache: "no-store" });
      if (res.ok) {
        const records = await res.json();
        setMatchRecords(records);
        setStats((current) => ({ ...current, totalMatches: records.length }));
      }
    } catch { /* ignore */ }
  }

  async function loadDashboardStats() {
    try {
      const res = await fetch(`${apiBaseUrl}/agent/report`, { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setStats((current) => ({
          ...current,
          totalPartners: data.overview.totalPartners,
          withProfile: data.overview.partnersWithProfile,
          pendingSuggestions: data.overview.pendingSuggestions,
        }));
      }
    } catch { /* ignore */ }
  }

  async function handleViewRecord(recordId: string) {
    try {
      const res = await fetch(`${apiBaseUrl}/agent/match-records/${recordId}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRequirement(data.requirement);
      setRecommendations(data.recommendations || []);
      setHasSearched(true);
      setViewingHistory(true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载记录失败");
    }
  }

  async function handleMatch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setHasSearched(true);
    setRecommendations([]);
    setLoadingStage(0);
    setCopiedRank(null);

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
      setViewingHistory(false);
      loadMatchRecords();
      setSubmittedRequirement(requirement);
      setRequirement("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "匹配失败");
    } finally {
      if (stageTimer.current) { clearInterval(stageTimer.current); stageTimer.current = null; }
      setLoading(false);
    }
  }

  function handleCopy(rank: number, r: Recommendation) {
    const text = buildCopyText(submittedRequirement || requirement, r, rank);
    copyToClipboard(text);
    setCopiedRank(rank);
    setTimeout(() => setCopiedRank(null), 2000);
  }

  const top3 = recommendations.slice(0, 3);

  return (
    <main className="page">
      <p className="eyebrow">Lingjian Agent Workspace</p>
      <h1>灵鉴 Agent 工作台</h1>
      <p className="lead">归集伙伴档案、项目案例与交付物，形成可信的能力画像，并基于项目需求推荐合适的交付伙伴。</p>

      <section className="card match-entry-card">
        <h2>项目需求</h2>
        <form onSubmit={handleMatch} className="match-form match-composer">
          <div className="form-row">
            <label htmlFor="requirement">描述项目需求</label>
            <textarea id="requirement" value={requirement} onChange={(e) => setRequirement(e.target.value)} required rows={6} placeholder="描述项目背景、行业、区域、交付范围与关键能力要求…" />
          </div>
          <div className="match-composer-footer">
            <p className="match-scope">当前基于 <strong>{stats.totalPartners}</strong> 家伙伴进行寻源，其中 <strong>{stats.withProfile}</strong> 家已生成能力画像</p>
            <button type="submit" disabled={loading} className="btn-primary-lg">{loading ? "匹配中..." : "开始寻源"}</button>
          </div>
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

      {/* History banner */}
      {!loading && viewingHistory && top3.length > 0 && (
        <section className="card" style={{ padding: "12px 24px", display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "13px", color: "var(--muted)" }}>📌 当前展示的是历史匹配记录，未重新调用大模型</span>
        </section>
      )}

      {/* Results */}
      {!loading && top3.length > 0 && (
        <>
          {/* Requirement analysis */}
          <section className="card">
            <h2>项目需求解析</h2>
            <div style={{ marginTop: "12px", padding: "16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
              <p style={{ fontSize: "14px", lineHeight: 1.8, margin: 0, whiteSpace: "pre-wrap" }}>{submittedRequirement || requirement}</p>
            </div>
            <p style={{ fontSize: "13px", color: "var(--muted)", marginTop: "8px" }}>共检索到 {recommendations.length} 个候选伙伴，展示推荐前 {top3.length} 名</p>
          </section>

          {/* Top 3 recommendations */}
          <section className="card">
            <h2>推荐结果详情</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "24px", marginTop: "16px" }}>
              {top3.map((r, i) => {
                const level = getRecommendLevel(r.matchScore);
                const capTags = parseTags(r.matchedCapabilities);
                const indTags = parseTags(r.matchedIndustries);
                const areaTags = parseTags(r.matchedRegions);
                const rank = i + 1;
                return (
                  <div key={i} className="case-item" style={{ position: "relative", padding: "24px" }}>
                    {/* Rank badge */}
                    <div style={{
                      position: "absolute", top: "-10px", left: "20px",
                      width: "32px", height: "32px", borderRadius: "50%",
                      background: i === 0 ? "var(--brand)" : i === 1 ? "#e8a317" : "var(--muted)",
                      color: "white", fontSize: "16px", fontWeight: 700,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
                    }}>{rank}</div>

                    <div style={{ marginTop: "12px" }}>
                      {/* Header: name + level + score + copy */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                          <h3 style={{ margin: 0 }}><a href={`/partners/${r.partnerId}`}>{r.partnerName}</a></h3>
                          <span style={{
                            padding: "4px 12px", borderRadius: "999px", fontSize: "12px", fontWeight: 600,
                            background: level.bg, color: level.color, border: `1px solid ${level.color}40`,
                          }}>{level.label}</span>
                        </div>
                        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                          <span className="score-tag">匹配度: {r.matchScore}</span>
                          <button onClick={() => handleCopy(rank, r)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>
                            {copiedRank === rank ? "已复制 ✓" : "复制推荐说明"}
                          </button>
                        </div>
                      </div>

                      {/* Recommendation reason */}
                      <div style={{ marginTop: "12px", padding: "12px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                        <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>推荐理由</div>
                        <div style={{ fontSize: "14px", lineHeight: 1.7 }}>{r.recommendationReason || "暂无推荐理由"}</div>
                      </div>

                      {/* Matched tags */}
                      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "12px" }}>
                        <div style={{ flex: "1 1 180px" }}>
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>命中能力标签</div>
                          <TagPills tags={capTags} color="var(--brand-dark)" bg="#fff1f2" border="#ffd0d4" />
                        </div>
                        <div style={{ flex: "1 1 180px" }}>
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>命中行业经验</div>
                          <TagPills tags={indTags} color="var(--success)" bg="#f0fdf4" border="#bbf7d0" />
                        </div>
                        <div style={{ flex: "1 1 180px" }}>
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>命中覆盖区域</div>
                          <TagPills tags={areaTags} color="#1a4fa0" bg="#f0f5ff" border="#d6e4ff" />
                        </div>
                      </div>

                      {/* Evidence */}
                      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "12px" }}>
                        <div style={{ flex: "1 1 200px", padding: "12px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>支撑案例</div>
                          <div style={{ fontSize: "13px", lineHeight: 1.6 }}>{r.evidenceCases || "暂无支撑案例"}</div>
                        </div>
                        <div style={{ flex: "1 1 200px", padding: "12px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>支撑交付物</div>
                          <div style={{ fontSize: "13px", lineHeight: 1.6 }}>{r.evidenceDeliverables || "暂无交付物证据"}</div>
                        </div>
                      </div>

                      {/* Risk notes */}
                      <div style={{ marginTop: "12px", padding: "12px 16px", background: "#fef2f2", borderRadius: "8px", border: "1px solid #fecaca" }}>
                        <div style={{ fontSize: "12px", color: "var(--danger)", fontWeight: 600, marginBottom: "4px" }}>风险/缺口提示</div>
                        <div style={{ fontSize: "13px", lineHeight: 1.6, color: "#991b1b" }}>{r.riskNotes || "暂无风险提示"}</div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}

      {/* Match records history */}
      <section className="card">
        <h2>最近匹配记录</h2>
        {matchRecords.length === 0 ? (
          <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无匹配记录，请输入项目需求后点击智能匹配。</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "12px" }}>
            {matchRecords.slice(0, 3).map((r) => (
              <div key={r.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "14px", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.requirement}</div>
                  <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px" }}>
                    Top1: {r.topPartner} | 推荐伙伴: {r.partnerCount}个 | {r.createdAt.slice(0, 19).replace("T", " ")}
                  </div>
                </div>
                <button onClick={() => handleViewRecord(r.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "6px 14px", marginLeft: "12px", flexShrink: 0 }}>查看详情</button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card operations-overview">
        <h2>运营概览</h2>
        <div className="operations-overview-grid">
          <div className="operations-overview-item"><span>已管理伙伴</span><strong>{stats.totalPartners}</strong></div>
          <div className="operations-overview-item"><span>已生成 AI 画像</span><strong>{stats.withProfile}</strong></div>
          <div className="operations-overview-item"><span>累计智能匹配</span><strong>{stats.totalMatches}</strong></div>
          <div className="operations-overview-item"><span>待采纳 AI 建议</span><strong>{stats.pendingSuggestions}</strong></div>
        </div>
      </section>

    </main>
  );
}
