"use client";

import { useState, useEffect } from "react";

type DemandProfile = {
  id: string; matchRecordId: string | null; requirementText: string;
  industryTags: string | null; capabilityTags: string | null; deliveryTypeTags: string | null;
  regionTags: string | null; complexityLevel: string | null; urgencyLevel: string | null;
  projectKeywords: string | null; matchedPartnerCount: number; topPartnerNames: string | null;
  supplyStatus: string | null; gapAnalysis: string | null; createdAt: string;
};

type Overview = {
  totalDemands: number; thisMonthDemands: number; topCapabilityTags: string;
  gapDemandCount: number; avgPartnerCount: number;
};

type DemandResponse = {
  overview: Overview; profiles: DemandProfile[];
  industryDistribution: Record<string, number>; capabilityDistribution: Record<string, number>;
  regionDistribution: Record<string, number>; deliveryTypeDistribution: Record<string, number>;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function supplyBadge(status: string | null) {
  if (status === "sufficient") return { label: "供给充足", color: "var(--success)", bg: "#f0fdf4", border: "#bbf7d0" };
  if (status === "partial") return { label: "部分满足", color: "#e8a317", bg: "#fffbeb", border: "#fde68a" };
  return { label: "明显缺口", color: "var(--danger)", bg: "#fef2f2", border: "#fecaca" };
}

function MetricCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ flex: "1 1 160px", padding: "20px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)", textAlign: "center" }}>
      <div style={{ fontSize: "28px", fontWeight: 700, color: color || "var(--brand)" }}>{value}</div>
      <div style={{ fontSize: "13px", color: "var(--muted)", marginTop: "6px" }}>{label}</div>
    </div>
  );
}

function DistBar({ title, dist }: { title: string; dist: Record<string, number> }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const max = Math.max(...entries.map(e => e[1]), 1);
  return (
    <div style={{ flex: "1 1 240px" }}>
      <h3 style={{ fontSize: "14px", marginBottom: "10px" }}>{title}</h3>
      {entries.length === 0 ? <p className="placeholder-text">暂无数据</p> : entries.map(([tag, count]) => (
        <div key={tag} style={{ marginBottom: "8px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "3px" }}>
            <span>{tag}</span><span style={{ color: "var(--muted)" }}>{count}</span>
          </div>
          <div style={{ height: "6px", background: "var(--line)", borderRadius: "3px", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${(count / max) * 100}%`, background: "var(--brand)", borderRadius: "3px" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function TagsDisplay({ val }: { val: string | null }) {
  if (!val) return <span style={{ fontSize: "13px", color: "var(--muted)" }}>无</span>;
  const tags = val.split(",").map(t => t.trim()).filter(Boolean);
  if (tags.length === 0) return <span style={{ fontSize: "13px", color: "var(--muted)" }}>无</span>;
  return <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>{tags.map((t, i) => <span key={i} className="partner-tag">{t}</span>)}</div>;
}

export default function DemandsPage() {
  const [data, setData] = useState<DemandResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function loadData() {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/agent/demand-profiles`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) { setError(e instanceof Error ? e.message : "需求画像加载失败，请稍后重试"); } finally { setLoading(false); }
  }

  useEffect(() => { loadData(); }, []);

  if (loading) return <main className="page"><p>加载中...</p></main>;

  return (
    <main className="page">
      <p className="eyebrow">Demand Operations</p>
      <h1>项目需求画像</h1>
      <p className="lead">基于历史项目需求和智能匹配记录，分析需求趋势、能力热度与伙伴供给缺口。</p>
      <div style={{ marginBottom: "16px" }}>
        <button onClick={loadData} className="secondary-btn">刷新数据</button>
      </div>

      {error && <p className="error-text">{error}</p>}

      {!error && data && data.profiles.length === 0 && (
        <section className="card"><p className="placeholder-text" style={{ marginTop: "12px" }}>暂无需求画像，请先在 Agent 工作台完成一次智能匹配。</p></section>
      )}

      {!error && data && data.profiles.length > 0 && (
        <>
          {/* 总览指标卡 */}
          <section className="card">
            <h2>总览指标</h2>
            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "16px" }}>
              <MetricCard label="累计需求数" value={data.overview.totalDemands} />
              <MetricCard label="本月新增" value={data.overview.thisMonthDemands} />
              <MetricCard label="供给不足需求数" value={data.overview.gapDemandCount} color="var(--danger)" />
              <MetricCard label="平均推荐伙伴数" value={data.overview.avgPartnerCount} />
            </div>
            <div style={{ marginTop: "12px", padding: "12px 16px", background: "#fff1f2", borderRadius: "8px", border: "1px solid #ffd0d4" }}>
              <span style={{ fontSize: "13px", color: "var(--brand-dark)", fontWeight: 600 }}>高频能力标签：</span>
              <span style={{ fontSize: "14px" }}>{data.overview.topCapabilityTags}</span>
            </div>
          </section>

          {/* 需求分类分布 */}
          <section className="card">
            <h2>需求分类分布</h2>
            <div style={{ display: "flex", gap: "24px", flexWrap: "wrap", marginTop: "16px" }}>
              <DistBar title="行业分布" dist={data.industryDistribution} />
              <DistBar title="能力分布" dist={data.capabilityDistribution} />
              <DistBar title="区域分布" dist={data.regionDistribution} />
              <DistBar title="交付类型分布" dist={data.deliveryTypeDistribution} />
            </div>
          </section>

          {/* 高频需求列表 */}
          <section className="card">
            <h2>高频需求列表</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "12px" }}>
              {data.profiles.map((p) => {
                const badge = supplyBadge(p.supplyStatus);
                const isExpanded = expandedId === p.id;
                return (
                  <div key={p.id} className="case-item" style={{ padding: "16px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: "14px", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.requirementText}</div>
                        <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
                          <span>行业: {p.industryTags || "未分类"}</span>
                          <span>能力: {p.capabilityTags || "未分类"}</span>
                          <span>区域: {p.regionTags || "未分类"}</span>
                          <span>推荐伙伴: {p.matchedPartnerCount}个</span>
                          <span>Top1: {p.topPartnerNames?.split(",")[0] || "无"}</span>
                          <span>{p.createdAt.slice(0, 19).replace("T", " ")}</span>
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center", flexShrink: 0 }}>
                        <span style={{ padding: "4px 10px", borderRadius: "999px", fontSize: "12px", fontWeight: 600, background: badge.bg, color: badge.color, border: `1px solid ${badge.border}` }}>{badge.label}</span>
                        <button onClick={() => setExpandedId(isExpanded ? null : p.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>{isExpanded ? "收起" : "展开"}</button>
                      </div>
                    </div>
                    {isExpanded && (
                      <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid var(--line)" }}>
                        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                          <div style={{ flex: "1 1 200px" }}><div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>原始需求</div><div style={{ fontSize: "13px", lineHeight: 1.6 }}>{p.requirementText}</div></div>
                          <div style={{ flex: "1 1 150px" }}><div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>行业标签</div><TagsDisplay val={p.industryTags} /></div>
                          <div style={{ flex: "1 1 150px" }}><div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>能力标签</div><TagsDisplay val={p.capabilityTags} /></div>
                          <div style={{ flex: "1 1 150px" }}><div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>区域标签</div><TagsDisplay val={p.regionTags} /></div>
                        </div>
                        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "10px" }}>
                          <div style={{ flex: "1 1 150px" }}><div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>交付类型</div><TagsDisplay val={p.deliveryTypeTags} /></div>
                          <div style={{ flex: "1 1 150px" }}><div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>复杂度/紧急度</div><span style={{ fontSize: "13px" }}>{p.complexityLevel || "中"} / {p.urgencyLevel || "中"}</span></div>
                          <div style={{ flex: "1 1 150px" }}><div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "4px" }}>推荐伙伴</div><span style={{ fontSize: "13px" }}>{p.topPartnerNames || "无"}</span></div>
                        </div>
                        <div style={{ marginTop: "10px", padding: "10px 14px", background: "#fef2f2", borderRadius: "8px", border: "1px solid #fecaca" }}>
                          <div style={{ fontSize: "12px", color: "var(--danger)", fontWeight: 600, marginBottom: "4px" }}>缺口分析</div>
                          <div style={{ fontSize: "13px", color: "#991b1b" }}>{p.gapAnalysis || "暂无分析"}</div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          {/* 供需缺口分析 */}
          <section className="card">
            <h2>供需缺口分析</h2>
            {data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").length === 0 ? (
              <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无供给缺口需求。</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "12px" }}>
                {data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").map((p) => {
                  const badge = supplyBadge(p.supplyStatus);
                  return (
                    <div key={p.id} style={{ padding: "12px 16px", background: badge.bg, borderRadius: "8px", border: `1px solid ${badge.border}` }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                        <span style={{ fontSize: "14px", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{p.requirementText}</span>
                        <span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: "white", color: badge.color, border: `1px solid ${badge.border}`, flexShrink: 0, marginLeft: "8px" }}>{badge.label}</span>
                      </div>
                      <div style={{ fontSize: "13px", color: "#666", lineHeight: 1.6 }}>{p.gapAnalysis || "暂无分析"}</div>
                      {p.supplyStatus === "gap" && <div style={{ fontSize: "12px", color: "var(--danger)", marginTop: "4px" }}>建议：补充相关行业案例和交付资源</div>}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}