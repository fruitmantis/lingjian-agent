"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";

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
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [gapPage, setGapPage] = useState(1);
  const [gapPageSize, setGapPageSize] = useState(10);
  const searchParams = useSearchParams();
  const initialTab = (searchParams.get("tab") as "profiles" | "report" | "opportunities") || "profiles";
  const [subTab, setSubTab] = useState<"profiles" | "report" | "opportunities">(initialTab);

  // Sync subTab with URL when searchParams change
  const urlTabStr = searchParams.get("tab") || "";
  useEffect(() => {
    const urlTab = urlTabStr as "profiles" | "report" | "opportunities" | null;
    if (urlTab && urlTab !== subTab) setSubTab(urlTab);
    if (!urlTab && subTab !== "profiles") setSubTab("profiles");
  }, [urlTabStr]);

  // Update URL when subTab changes
  function changeSubTab(tab: "profiles" | "report" | "opportunities") {
    setSubTab(tab);
    const url = new URL(window.location.href); if (tab === "profiles") url.searchParams.delete("tab"); else url.searchParams.set("tab", tab); window.history.pushState({}, "", url);
  }
  const [report, setReport] = useState<any>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [filterDays, setFilterDays] = useState(0);
  const [filterIndustry, setFilterIndustry] = useState("");
  const [filterRegion, setFilterRegion] = useState("");
  const [filterCapability, setFilterCapability] = useState("");
  const [opps, setOpps] = useState<any[]>([]);
  const [oppLoading, setOppLoading] = useState(false);
  const [oppError, setOppError] = useState<string | null>(null);
  const [oppKeyword, setOppKeyword] = useState("");
  const [oppIndustry, setOppIndustry] = useState("");
  const [oppRegion, setOppRegion] = useState("");
  const [oppStage, setOppStage] = useState("");
  const [expandedOpp, setExpandedOpp] = useState<string | null>(null);

  async function loadData() {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/agent/demand-profiles`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) { setError(e instanceof Error ? e.message : "需求画像加载失败，请稍后重试"); } finally { setLoading(false); }
  }

  useEffect(() => { loadData(); }, []);

  async function deleteProfile(id: string) {
    if (!confirm("确定删除该需求画像？此操作不可恢复。")) return;
    try {
      const res = await fetch(`${apiBaseUrl}/agent/demand-profiles/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadData();
    } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
  }

  async function loadReport() {
    setReportLoading(true); setReportError(null);
    try {
      const p = new URLSearchParams();
      if (filterDays) p.set("days", String(filterDays));
      if (filterIndustry) p.set("industry", filterIndustry);
      if (filterRegion) p.set("region", filterRegion);
      if (filterCapability) p.set("capability", filterCapability);
      const res = await fetch(`${apiBaseUrl}/agent/report?${p}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setReport(await res.json());
    } catch (e) { setReportError(e instanceof Error ? e.message : "报表加载失败"); } finally { setReportLoading(false); }
  }
  useEffect(() => { if (subTab === "report") loadReport(); }, [subTab, filterDays, filterIndustry, filterRegion, filterCapability]);

  async function loadOpps() {
    setOppLoading(true); setOppError(null);
    try {
      const p = new URLSearchParams();
      if (oppKeyword) p.set("keyword", oppKeyword);
      if (oppIndustry) p.set("industry", oppIndustry);
      if (oppRegion) p.set("region", oppRegion);
      if (oppStage) p.set("stage", oppStage);
      const r = await fetch(`${apiBaseUrl}/agent/opportunities?${p}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setOpps(await r.json());
    } catch (e) { setOppError(e instanceof Error ? e.message : "加载失败"); } finally { setOppLoading(false); }
  }
  useEffect(() => { if (subTab === "opportunities") loadOpps(); }, [subTab, oppKeyword, oppIndustry, oppRegion, oppStage]);

  if (loading) return <main className="page"><p>加载中...</p></main>;

  return (
    <main className="page">
      <p className="eyebrow">{subTab === "profiles" ? "Demand Profiles" : subTab === "report" ? "Operations Report" : "Project Opportunities"}</p>
      <h1>{subTab === "profiles" ? "需求画像" : subTab === "report" ? "运营报表" : "项目机会库"}</h1>
      <p className="lead">{subTab === "profiles" ? "基于历史项目需求和智能匹配记录，分析需求趋势、能力热度与伙伴供给缺口。" : subTab === "report" ? "洞察一线项目需求趋势，识别伙伴能力供给缺口。" : "沉淀和管理 AI 从项目需求中抽取出的结构化项目信息。"}</p>
      {error && <p className="error-text">{error}</p>}

      {subTab === "profiles" && !error && data && data.profiles.length === 0 && (
        <section className="card"><p className="placeholder-text" style={{ marginTop: "12px" }}>暂无需求画像，请先在 Agent 工作台完成一次智能匹配。</p></section>
      )}

      {subTab === "profiles" && !error && data && data.profiles.length > 0 && (
        <>
          {data.profiles.length < 5 && (
            <div style={{ padding: "10px 16px", background: "#fffbeb", borderRadius: "8px", border: "1px solid #fde68a", marginBottom: "16px", fontSize: "13px", color: "#92400e" }}>当前样本量较少（{data.profiles.length} 条），数据仅供参考。</div>
          )}
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
              {data.profiles.slice((page - 1) * pageSize, page * pageSize).map((p) => {
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
                        <button onClick={() => setExpandedId(isExpanded ? null : p.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>{isExpanded ? "收起" : "展开"}</button> <button onClick={() => deleteProfile(p.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px", color: "var(--danger)", borderColor: "#fecaca" }}>删除</button>
                      </div>
                    </div>
                    {isExpanded && (
                      <div style={{ marginTop: "16px", paddingTop: "16px", borderTop: "1px solid var(--line)" }}>
                        <div style={{ padding: "14px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)", marginBottom: "12px" }}>
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>原始需求</div>
                          <div style={{ fontSize: "14px", lineHeight: 1.7 }}>{p.requirementText}</div>
                        </div>
                        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                          <div style={{ flex: "1 1 150px", padding: "12px 14px", background: "#fff1f2", borderRadius: "8px", border: "1px solid #ffd0d4" }}>
                            <div style={{ fontSize: "12px", color: "var(--brand-dark)", fontWeight: 600, marginBottom: "6px" }}>行业标签</div>
                            <TagsDisplay val={p.industryTags} />
                          </div>
                          <div style={{ flex: "1 1 150px", padding: "12px 14px", background: "#f0fdf4", borderRadius: "8px", border: "1px solid #bbf7d0" }}>
                            <div style={{ fontSize: "12px", color: "var(--success)", fontWeight: 600, marginBottom: "6px" }}>能力标签</div>
                            <TagsDisplay val={p.capabilityTags} />
                          </div>
                          <div style={{ flex: "1 1 150px", padding: "12px 14px", background: "#f0f5ff", borderRadius: "8px", border: "1px solid #d6e4ff" }}>
                            <div style={{ fontSize: "12px", color: "#1a4fa0", fontWeight: 600, marginBottom: "6px" }}>区域标签</div>
                            <TagsDisplay val={p.regionTags} />
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "12px" }}>
                          <div style={{ flex: "1 1 150px", padding: "12px 14px", background: "#fafafa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                            <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>交付类型</div>
                            <TagsDisplay val={p.deliveryTypeTags} />
                          </div>
                          <div style={{ flex: "1 1 120px", padding: "12px 14px", background: "#fafafa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                            <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>复杂度</div>
                            <span style={{ fontSize: "13px", fontWeight: 500 }}>{p.complexityLevel || "中"}</span>
                          </div>
                          <div style={{ flex: "1 1 120px", padding: "12px 14px", background: "#fafafa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                            <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>紧急度</div>
                            <span style={{ fontSize: "13px", fontWeight: 500 }}>{p.urgencyLevel || "中"}</span>
                          </div>
                          <div style={{ flex: "1 1 180px", padding: "12px 14px", background: "#fafafa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                            <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>推荐伙伴</div>
                            <span style={{ fontSize: "13px", fontWeight: 500 }}>{p.topPartnerNames || "无"}</span>
                          </div>
                        </div>
                        <div style={{ marginTop: "12px", padding: "14px 16px", background: "#fef2f2", borderRadius: "8px", border: "1px solid #fecaca" }}>
                          <div style={{ fontSize: "12px", color: "var(--danger)", fontWeight: 600, marginBottom: "6px" }}>缺口分析</div>
                          <div style={{ fontSize: "14px", lineHeight: 1.6, color: "#991b1b" }}>{p.gapAnalysis || "暂无分析"}</div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          {data.profiles.length > pageSize && (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "12px", flexWrap: "wrap", gap: "8px" }}>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <span style={{ fontSize: "13px", color: "var(--muted)" }}>每页</span>
                <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ padding: "4px 8px", border: "1px solid var(--line)", borderRadius: "4px", fontSize: "13px" }}>
                  <option value={10}>10</option><option value={20}>20</option><option value={50}>50</option>
                </select>
                <span style={{ fontSize: "13px", color: "var(--muted)" }}>条 | 共 {data.profiles.length} 条</span>
              </div>
              <div style={{ display: "flex", gap: "6px" }}>
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 10px", opacity: page === 1 ? 0.5 : 1 }}>上一页</button>
                <span style={{ fontSize: "13px", lineHeight: "28px", padding: "0 8px" }}>第 {page} / {Math.ceil(data.profiles.length / pageSize)} 页</span>
                <button onClick={() => setPage(p => Math.min(Math.ceil(data.profiles.length / pageSize), p + 1))} disabled={page >= Math.ceil(data.profiles.length / pageSize)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 10px", opacity: page >= Math.ceil(data.profiles.length / pageSize) ? 0.5 : 1 }}>下一页</button>
              </div>
            </div>
          )}
          </section>

          {/* 供需缺口分析 */}
          <section className="card">
            <h2>供需缺口分析</h2>
            {data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").length === 0 ? (
              <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无供给缺口需求。</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "12px" }}>
                {data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").slice((gapPage - 1) * gapPageSize, gapPage * gapPageSize).map((p) => {
                  const badge = supplyBadge(p.supplyStatus);
                  return (
                    <div key={p.id} style={{ padding: "12px 16px", background: badge.bg, borderRadius: "8px", border: `1px solid ${badge.border}` }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                        <span style={{ fontSize: "14px", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{p.requirementText}</span>
                        <span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: "white", color: badge.color, border: `1px solid ${badge.border}`, flexShrink: 0, marginLeft: "8px" }}>{badge.label}</span> <button onClick={() => deleteProfile(p.id)} className="secondary-btn" style={{ fontSize: "11px", padding: "2px 8px", color: "var(--danger)", borderColor: "#fecaca", flexShrink: 0 }}>删除</button>
                      </div>
                      <div style={{ fontSize: "13px", color: "#666", lineHeight: 1.6 }}>{p.gapAnalysis || "暂无分析"}</div>
                      {p.supplyStatus === "gap" && <div style={{ fontSize: "12px", color: "var(--danger)", marginTop: "4px" }}>建议：补充相关行业案例和交付资源</div>}
                    </div>
                  );
                })}
              </div>
            )}
            {data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").length > gapPageSize && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "12px", flexWrap: "wrap", gap: "8px" }}>
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <span style={{ fontSize: "13px", color: "var(--muted)" }}>每页</span>
                  <select value={gapPageSize} onChange={(e) => { setGapPageSize(Number(e.target.value)); setGapPage(1); }} style={{ padding: "4px 8px", border: "1px solid var(--line)", borderRadius: "4px", fontSize: "13px" }}>
                    <option value={10}>10</option><option value={20}>20</option><option value={50}>50</option>
                  </select>
                  <span style={{ fontSize: "13px", color: "var(--muted)" }}>条 | 共 {data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").length} 条</span>
                </div>
                <div style={{ display: "flex", gap: "6px" }}>
                  <button onClick={() => setGapPage(p => Math.max(1, p - 1))} disabled={gapPage === 1} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 10px", opacity: gapPage === 1 ? 0.5 : 1 }}>上一页</button>
                  <span style={{ fontSize: "13px", lineHeight: "28px", padding: "0 8px" }}>第 {gapPage} / {Math.ceil(data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").length / gapPageSize)} 页</span>
                  <button onClick={() => setGapPage(p => Math.min(Math.ceil(data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").length / gapPageSize), p + 1))} disabled={gapPage >= Math.ceil(data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").length / gapPageSize)} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 10px", opacity: gapPage >= Math.ceil(data.profiles.filter(p => p.supplyStatus === "gap" || p.supplyStatus === "partial").length / gapPageSize) ? 0.5 : 1 }}>下一页</button>
                </div>
              </div>
            )}
          </section>
        </>
      )}

      {subTab === "report" && (
        <ReportTab report={report} loading={reportLoading} error={reportError} filterDays={filterDays} setFilterDays={setFilterDays} filterIndustry={filterIndustry} setFilterIndustry={setFilterIndustry} filterRegion={filterRegion} setFilterRegion={setFilterRegion} filterCapability={filterCapability} setFilterCapability={setFilterCapability} />
      )}

      {subTab === "opportunities" && (
        <section className="card">
          <h2 className="section-title">项目机会库</h2>
          <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
            <input type="text" placeholder="搜索项目名称/客户..." value={oppKeyword} onChange={(e) => setOppKeyword(e.target.value)} style={{ flex: "1 1 180px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
            <input type="text" placeholder="行业" value={oppIndustry} onChange={(e) => setOppIndustry(e.target.value)} style={{ width: "100px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
            <input type="text" placeholder="区域" value={oppRegion} onChange={(e) => setOppRegion(e.target.value)} style={{ width: "100px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
            <input type="text" placeholder="阶段" value={oppStage} onChange={(e) => setOppStage(e.target.value)} style={{ width: "100px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
          </div>
          {oppError && <p className="error-text">{oppError}</p>}
          {oppLoading ? <p style={{ marginTop: "12px" }}>加载中...</p> : opps.length === 0 ? <div style={{ textAlign: "center", padding: "40px 20px" }}><p style={{ fontSize: "15px", color: "var(--muted)", marginBottom: "16px" }}>暂无项目机会。</p><p style={{ fontSize: "13px", color: "var(--muted)", marginBottom: "20px" }}>项目机会信息由 Agent 工作台智能匹配后自动抽取生成。</p><a href="/" className="btn-primary-lg" style={{ display: "inline-block", fontSize: "14px", padding: "10px 28px", textDecoration: "none" }}>前往智能匹配</a></div> : (
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "12px" }}>
              <thead><tr style={{ borderBottom: "1px solid var(--line)" }}>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>项目名称</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>客户</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>行业</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>区域</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>阶段</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>完整度</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>供给状态</th>
                <th style={{ textAlign: "left", padding: "8px", fontSize: "14px", whiteSpace: "nowrap" }}>操作</th>
              </tr></thead>
              <tbody>
                {opps.map((o) => {
                  const isExp = expandedOpp === o.id;
                  const badge = o.supplyStatus === "gap" ? { l: "明显缺口", c: "var(--danger)", bg: "#fef2f2", bd: "#fecaca" } : o.supplyStatus === "partial" ? { l: "部分满足", c: "#e8a317", bg: "#fffbeb", bd: "#fde68a" } : { l: "基本满足", c: "var(--success)", bg: "#f0fdf4", bd: "#bbf7d0" };
                  return (
                    <tr key={o.id} style={{ borderBottom: "1px solid var(--line)" }}>
                      <td style={{ padding: "10px 8px", fontSize: "14px", fontWeight: 600 }}>{o.projectName || "未识别"}</td>
                      <td style={{ padding: "10px 8px", fontSize: "13px" }}>{o.customerName || "未识别"}</td>
                      <td style={{ padding: "10px 8px", fontSize: "13px" }}>{o.industry || "-"}</td>
                      <td style={{ padding: "10px 8px", fontSize: "13px" }}>{o.region || "-"}</td>
                      <td style={{ padding: "10px 8px", fontSize: "13px" }}>{o.projectStage || "-"}</td>
                      <td style={{ padding: "10px 8px", fontSize: "14px", fontWeight: 700, color: o.completenessScore >= 80 ? "var(--success)" : o.completenessScore >= 50 ? "#e8a317" : "var(--danger)" }}>{o.completenessScore}%</td>
                      <td style={{ padding: "10px 8px" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: badge.bg, color: badge.c, border: `1px solid ${badge.bd}`, whiteSpace: "nowrap" }}>{badge.l}</span></td>
                      <td style={{ padding: "10px 8px", whiteSpace: "nowrap" }}><button onClick={() => setExpandedOpp(isExp ? null : o.id)} className="secondary-btn" style={{ fontSize: "11px", padding: "3px 8px" }}>{isExp ? "收起" : "详情"}</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}
    </main>
  );
}

function ReportTab({ report, loading, error, filterDays, setFilterDays, filterIndustry, setFilterIndustry, filterRegion, setFilterRegion, filterCapability, setFilterCapability }: any) {
  if (loading) return <p>加载中...</p>;
  if (error) return <p className="error-text">{error}</p>;
  if (!report) return <p className="placeholder-text">暂无数据。</p>;
  const max = (arr: any[]) => arr.length > 0 ? arr[0].count : 1;
  return (
    <>
      <section className="card"><h2>筛选条件</h2>
        <div style={{ display: "flex", gap: "12px", marginTop: "12px", flexWrap: "wrap" }}>
          <select value={filterDays} onChange={(e: any) => setFilterDays(parseInt(e.target.value))} style={{ padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }}><option value={0}>全部时间</option><option value={7}>近7天</option><option value={30}>近30天</option><option value={90}>近90天</option></select>
          <input type="text" placeholder="行业" value={filterIndustry} onChange={(e: any) => setFilterIndustry(e.target.value)} style={{ flex: "1 1 120px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
          <input type="text" placeholder="区域" value={filterRegion} onChange={(e: any) => setFilterRegion(e.target.value)} style={{ flex: "1 1 120px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
          <input type="text" placeholder="能力标签" value={filterCapability} onChange={(e: any) => setFilterCapability(e.target.value)} style={{ flex: "1 1 120px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
        </div>
      </section>
      <section className="card"><h2>运营总览</h2><div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "16px" }}>
        {[{v:report.overview.totalDemands,l:"累计需求"},{v:report.overview.thisMonthDemands,l:"本月新增"},{v:report.overview.totalPartners,l:"伙伴总数"},{v:report.overview.partnersWithProfile,l:"已生成画像"},{v:report.overview.activePartners,l:"活跃伙伴"},{v:report.overview.noPartnerDemands,l:"无合适伙伴"},{v:report.overview.partialDemands,l:"部分满足"},{v:report.overview.pendingSuggestions,l:"待采纳建议"}].map((m,i) => (
          <div key={i} style={{ flex: "1 1 120px", padding: "16px", background: "#f8f9fa", borderRadius: "8px", textAlign: "center" }}><div style={{ fontSize: "24px", fontWeight: 700, color: "var(--brand)" }}>{m.v}</div><div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px" }}>{m.l}</div></div>
        ))}
      </div></section>
      <section className="card"><h2>需求分布 TOP 10</h2><div style={{ display: "flex", gap: "24px", flexWrap: "wrap", marginTop: "16px" }}>
        {[{t:"能力需求",d:report.capabilityDist},{t:"行业需求",d:report.industryDist},{t:"区域需求",d:report.regionDist},{t:"交付类型",d:report.deliveryTypeDist}].map((g,i) => (
          <div key={i} style={{ flex: "1 1 200px" }}><h3 style={{ fontSize: "14px", marginBottom: "10px" }}>{g.t}</h3>
            {g.d.length === 0 ? <p className="placeholder-text">暂无数据</p> : g.d.map((item: any, j: number) => (
              <div key={j} style={{ marginBottom: "8px" }}><div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "3px" }}><span>{item.label}</span><span style={{ color: "var(--muted)" }}>{item.count}</span></div><div style={{ height: "6px", background: "var(--line)", borderRadius: "3px", overflow: "hidden" }}><div style={{ height: "100%", width: `${(item.count / max(g.d)) * 100}%`, background: "var(--brand)", borderRadius: "3px" }} /></div></div>
            ))}
          </div>
        ))}
      </div></section>
      <section className="card"><h2>供需缺口分析</h2>
        {report.supplyGaps.length === 0 ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无数据。</p> : (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "12px" }}><thead><tr style={{ borderBottom: "1px solid var(--line)" }}><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>能力</th><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>需求次数</th><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>可推荐伙伴</th><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>供给状态</th><th style={{ textAlign: "left", padding: "8px", fontSize: "14px" }}>缺口说明</th></tr></thead><tbody>
            {report.supplyGaps.map((g: any, i: number) => { const b = g.supplyStatus === "gap" ? { l: "明显缺口", c: "var(--danger)", bg: "#fef2f2", bd: "#fecaca" } : g.supplyStatus === "partial" ? { l: "部分满足", c: "#e8a317", bg: "#fffbeb", bd: "#fde68a" } : { l: "基本满足", c: "var(--success)", bg: "#f0fdf4", bd: "#bbf7d0" }; return (
              <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}><td style={{ padding: "10px 8px", fontSize: "14px", fontWeight: 600, whiteSpace: "nowrap" }}>{g.capability}</td><td style={{ padding: "10px 8px", fontSize: "13px" }}>{g.demandCount}</td><td style={{ padding: "10px 8px", fontSize: "13px" }}>{g.partnerCount}</td><td style={{ padding: "10px 8px" }}><span style={{ padding: "3px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: b.bg, color: b.c, border: `1px solid ${b.bd}`, whiteSpace: "nowrap" }}>{b.l}</span></td><td style={{ padding: "10px 8px", fontSize: "13px", color: "var(--muted)" }}>{g.gapNote}</td></tr>
            ); })}
          </tbody></table>
        )}
      </section>
      <section className="card"><h2>伙伴活跃度</h2><div style={{ marginTop: "12px" }}>
        <p style={{ fontSize: "14px" }}>活跃伙伴：<strong>{report.activePartnerCount}</strong> / {report.overview.totalPartners}（{report.activePartnerRatio}%）</p>
        <div style={{ display: "flex", gap: "24px", flexWrap: "wrap", marginTop: "16px" }}>
          <div style={{ flex: "1 1 300px" }}><h3 style={{ fontSize: "14px", marginBottom: "8px" }}>被推荐次数 TOP 10</h3>{report.topRecommendedPartners.length === 0 ? <p className="placeholder-text">暂无数据</p> : report.topRecommendedPartners.map((p: any, i: number) => (<div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--line)" }}><span style={{ fontSize: "13px" }}>{i+1}. {p.partnerName}</span><span style={{ fontSize: "13px", color: "var(--brand)", fontWeight: 600 }}>{p.recommendCount}次</span></div>))}</div>
          <div style={{ flex: "1 1 300px" }}><h3 style={{ fontSize: "14px", marginBottom: "8px" }}>长期未更新伙伴</h3>{report.inactivePartners.length === 0 ? <p className="placeholder-text">暂无数据</p> : report.inactivePartners.map((p: any, i: number) => (<div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--line)" }}><span style={{ fontSize: "13px" }}>{p.partnerName}</span><span style={{ fontSize: "12px", color: "var(--muted)" }}>{p.lastUpdated}</span></div>))}</div>
        </div>
      </div></section>
      <section className="card"><h2>标签运营</h2><div style={{ display: "flex", gap: "24px", flexWrap: "wrap", marginTop: "16px" }}>
        <div style={{ flex: "1 1 200px" }}><h3 style={{ fontSize: "14px", marginBottom: "8px" }}>高频正式能力标签</h3>{report.topFormalTags.length === 0 ? <p className="placeholder-text">暂无数据</p> : report.topFormalTags.map((t: any, i: number) => (<div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--line)" }}><span style={{ fontSize: "13px" }}>{t.label}</span><span style={{ fontSize: "13px", color: "var(--brand)", fontWeight: 600 }}>{t.count}</span></div>))}</div>
        <div style={{ flex: "1 1 200px" }}><div style={{ padding: "16px", background: "#fffbeb", borderRadius: "8px", border: "1px solid #fde68a", marginBottom: "8px" }}><div style={{ fontSize: "24px", fontWeight: 700, color: "#e8a317" }}>{report.uncoveredClues}</div><div style={{ fontSize: "12px", color: "var(--muted)" }}>未覆盖能力线索</div></div><div style={{ padding: "16px", background: "#fffbeb", borderRadius: "8px", border: "1px solid #fde68a" }}><div style={{ fontSize: "24px", fontWeight: 700, color: "#e8a317" }}>{report.pendingSuggestions}</div><div style={{ fontSize: "12px", color: "var(--muted)" }}>待采纳AI建议</div></div></div>
      </div></section>
    </>
  );
}