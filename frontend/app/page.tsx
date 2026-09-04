"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, useEffect, useRef } from "react";
import { ENABLED_SCENES } from "@/lib/scenes";
import { apiFetch } from "@/components/auth-provider";

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

const LOADING_STAGES = [
  "需求解析：正在分析项目需求的行业、区域与能力诉求……",
  "伙伴画像匹配：正在从伙伴库中检索匹配的交付能力……",
  "候选筛选：正在评估候选伙伴的案例与交付物证据……",
  "推荐理由生成：正在生成推荐短名单与风险提示……",
];

const TASK_STATUS_LABELS: Record<string, string> = {
  matching: "匹配中", enriching: "处理中", ready: "已完成", partial: "部分完成", failed: "失败",
};

function getRecommendLevel(score: string): { label: string; color: string; bg: string } {
  const num = parseInt(score) || 0;
  if (num >= 80) return { label: "强推荐", color: "var(--brand-dark)", bg: "var(--brand-soft)" };
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
    `【匹配能力】${r.matchedCapabilities || "无"}`,
    `【匹配行业】${r.matchedIndustries || "无"}`,
    `【匹配区域】${r.matchedRegions || "无"}`,
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
  const searchParams = useSearchParams();
  const [requirement, setRequirement] = useState("");
  const [submittedRequirement, setSubmittedRequirement] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [copiedRank, setCopiedRank] = useState<number | null>(null);
  const [matchRecords, setMatchRecords] = useState<{ id: string; requirement: string; topPartner: string; partnerCount: number; createdAt: string; taskStatus: string }[]>([]);
  const [viewingHistory, setViewingHistory] = useState(false);
  const [expandedRecordId, setExpandedRecordId] = useState<string | null>(null);
  const [historyDetail, setHistoryDetail] = useState<{ requirement: string; recommendations: Recommendation[] } | null>(null);
  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const requirementInput = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    loadMatchRecords();
    return () => { if (stageTimer.current) clearInterval(stageTimer.current); };
  }, []);

  useEffect(() => {
    const prompt = searchParams.get("prompt");
    if (prompt) {
      setRequirement(prompt);
      window.setTimeout(() => requirementInput.current?.focus(), 0);
    }
    if (searchParams.get("view") === "history") {
      window.setTimeout(() => document.getElementById("history")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
    }
  }, [searchParams]);

  async function loadMatchRecords() {
    try {
      const res = await apiFetch("/agent/tasks?status=active&page=1&pageSize=5", { cache: "no-store" });
      if (res.ok) {
        const records = await res.json();
        setMatchRecords(records.items || []);
      }
    } catch { /* ignore */ }
  }

  async function handleViewRecord(recordId: string) {
    if (expandedRecordId === recordId) { setExpandedRecordId(null); setHistoryDetail(null); return; }
    setExpandedRecordId(recordId);
    setHistoryDetail(null);
    try {
      const res = await apiFetch(`/agent/tasks/${recordId}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setHistoryDetail({ requirement: data.requirement, recommendations: data.recommendations || [] });
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
      const res = await apiFetch("/agent/match", {
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
      void loadMatchRecords();
    } finally {
      if (stageTimer.current) { clearInterval(stageTimer.current); stageTimer.current = null; }
      setLoading(false);
    }
  }

  async function archiveMatchRecord(recordId: string) {
    if (!confirm("确定归档该任务？归档后可在“我的任务”中恢复。")) return;
    try {
      const res = await apiFetch(`/agent/tasks/${recordId}/archive`, { method: "PATCH" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (expandedRecordId === recordId) { setExpandedRecordId(null); setHistoryDetail(null); }
      loadMatchRecords();
    } catch (e) {
      setError(e instanceof Error ? e.message : "归档失败");
    }
  }

  async function handleMatchDirect(reqText: string) {
    setRequirement(reqText);
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
      const res = await apiFetch("/agent/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requirement: reqText }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setRecommendations(data.recommendations || []);
      setViewingHistory(false);
      loadMatchRecords();
      setSubmittedRequirement(reqText);
      setRequirement("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "匹配失败");
      setRequirement(reqText);
      void loadMatchRecords();
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
  const featuredScenes = ENABLED_SCENES.filter((scene) => [
    "ai-project-partner-recommendation",
    "partner-capability-query",
    "partner-ai-profile",
    "partner-capability-gap-analysis",
    "project-demand-profile",
    "project-opportunity-identification",
  ].includes(scene.id));
  const quickCategories = ["智能匹配", "伙伴洞察", "能力发展", "项目机会", "运营分析"];

  return (
    <main className="page assistant-page">
      <section className="assistant-hero">
        <div className="assistant-orb" aria-hidden="true"><span /></div>
        <p className="assistant-kicker">伙伴能力智能助手</p>
        <h1>灵鉴助手</h1>
        <p className="assistant-subtitle">懂伙伴、懂能力、懂项目，让伙伴能力发展有据可依</p>

        <form onSubmit={handleMatch} className="assistant-composer">
          <label htmlFor="requirement" className="sr-only">输入项目需求</label>
          <textarea
            ref={requirementInput}
            id="requirement"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            required
            rows={4}
            placeholder="请输入项目需求，或告诉我你想找什么伙伴、分析什么能力，也可以从下方场景开始"
          />
          <div className="assistant-composer-footer">
            <span>当前输入使用智能匹配能力 · partner_match</span>
            <button type="submit" disabled={loading} className="assistant-submit">
              <span>{loading ? "分析中" : "开始任务"}</span><span aria-hidden="true">→</span>
            </button>
          </div>
        </form>

        <div className="assistant-examples" aria-label="示例问题">
          <span>试试这样问</span>
          {["帮我找适合制造行业知识库 Agent 项目的伙伴", "XX伙伴有哪些AI能力？", "找有金融AI案例的伙伴", "XX伙伴有哪些能力短板？"].map((example) => (
            <button key={example} type="button" onClick={() => { setRequirement(example); requirementInput.current?.focus(); }}>{example}</button>
          ))}
        </div>
      </section>

      <section className="assistant-section assistant-category-section" aria-labelledby="category-heading">
        <div className="assistant-section-heading">
          <div><p>从能力域开始</p><h2 id="category-heading">场景分类</h2></div>
          <Link href="/scenes">浏览全部场景 <span aria-hidden="true">→</span></Link>
        </div>
        <div className="assistant-category-grid">
          {quickCategories.map((category, index) => (
            <Link key={category} href={`/scenes?category=${encodeURIComponent(category)}`} className="assistant-category-card">
              <span className={`assistant-category-icon tone-${index + 1}`} aria-hidden="true">{["匹", "察", "能", "机", "析"][index]}</span>
              <span><strong>{category}</strong><small>{ENABLED_SCENES.filter((scene) => scene.category === category).length} 个场景</small></span>
              <span className="card-arrow" aria-hidden="true">→</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="assistant-section" aria-labelledby="featured-heading">
        <div className="assistant-section-heading">
          <div><p>基于现有能力为你推荐</p><h2 id="featured-heading">猜你想做</h2></div>
          <Link href="/scenes">进入场景广场 <span aria-hidden="true">→</span></Link>
        </div>
        <div className="featured-scene-grid">
          {featuredScenes.map((scene) => {
            const content = (
              <>
                <div className="featured-scene-heading">
                  <h3>{scene.name}</h3>
                  <span className={`availability-badge ${scene.availability}`}>
                    {scene.availability === "ready" ? "可使用" : scene.availability === "embedded" ? "随匹配生成" : "建设中"}
                  </span>
                </div>
                <p>{scene.description}</p>
                <div className="scene-tag-row">{scene.tags.slice(0, 2).map((tag) => <span key={tag}>{tag}</span>)}</div>
                <div className="featured-scene-action">{scene.actionLabel}<span aria-hidden="true">→</span></div>
              </>
            );
            return scene.actionHref ? <Link className="featured-scene-card" href={scene.actionHref} key={scene.id}>{content}</Link> : <article className="featured-scene-card disabled" key={scene.id}>{content}</article>;
          })}
        </div>
      </section>

      {error && <p className="error-text assistant-error">{error}</p>}

      {/* 本次项目需求卡片 - only show after submit */}
      {!loading && submittedRequirement && !viewingHistory && (
        <section className="card" style={{ borderColor: "var(--brand)", borderWidth: "1px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <h2 style={{ margin: 0 }}>本次项目需求</h2>
            <div style={{ display: "flex", gap: "8px" }}>
              <button onClick={() => { const text = submittedRequirement; copyToClipboard(text); }} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>复制需求</button>
              <button onClick={() => { setRequirement(submittedRequirement); setSubmittedRequirement(""); setRecommendations([]); setHasSearched(false); document.getElementById("requirement")?.focus(); }} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>重新编辑</button>
              <button onClick={() => { const req = submittedRequirement; handleMatchDirect(req); }} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px", color: "var(--brand)", borderColor: "var(--brand)" }}>再次寻源</button>
            </div>
          </div>
          <div style={{ padding: "14px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
            <p style={{ fontSize: "14px", lineHeight: 1.8, margin: 0, whiteSpace: "pre-wrap" }}>{submittedRequirement}</p>
          </div>
        </section>
      )}

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
          {/* Top 3 recommendations */}
          <section className="card">
            <h2>推荐结果详情</h2>
            <p style={{ fontSize: "13px", color: "var(--muted)", marginBottom: "16px" }}>基于本次项目需求，共检索到 {recommendations.length} 个候选伙伴，展示推荐前 {top3.length} 名</p>
            <div style={{ display: "flex", flexDirection: "column", gap: "24px", marginTop: "16px" }}>
              {top3.map((r, i) => {
                const level = getRecommendLevel(r.matchScore);
                const capTags = parseTags(r.matchedCapabilities);
                const indTags = parseTags(r.matchedIndustries);
                const areaTags = parseTags(r.matchedRegions);
                const rank = i + 1;
                return (
                  <div key={i} className="case-item" style={{ position: "relative", padding: "24px", border: i === 0 ? "2px solid var(--brand)" : "1px solid var(--line)", boxShadow: i === 0 ? "0 4px 20px rgb(var(--brand-rgb) / 10%)" : "none" }}>
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
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>匹配能力标签</div>
                          <TagPills tags={capTags} color="var(--brand-dark)" bg="var(--brand-soft)" border="var(--brand-border)" />
                        </div>
                        <div style={{ flex: "1 1 180px" }}>
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>匹配行业经验</div>
                          <TagPills tags={indTags} color="var(--success)" bg="#f0fdf4" border="#bbf7d0" />
                        </div>
                        <div style={{ flex: "1 1 180px" }}>
                          <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>匹配覆盖区域</div>
                          <TagPills tags={areaTags} color="var(--accent-teal)" bg="var(--accent-teal-soft)" border="var(--accent-teal-border)" />
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

      {/* Recent tasks */}
      <section className="card history-card" id="history">
        <div className="history-heading">
          <div><span>任务</span><h2>历史任务</h2></div>
          <small><Link href="/tasks">查看全部</Link></small>
        </div>
        {matchRecords.length === 0 ? (
          <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无匹配记录，请输入项目需求后点击智能匹配。</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "12px" }}>
            {matchRecords.map((r) => (
              <div key={r.id}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "14px", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.requirement}</div>
                    <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px" }}>
                      <span className={`status-badge task-${r.taskStatus}`}>{TASK_STATUS_LABELS[r.taskStatus] || r.taskStatus}</span> · Top1: {r.topPartner} · 推荐伙伴: {r.partnerCount}个 · {r.createdAt.slice(0, 19).replace("T", " ")}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "6px", marginLeft: "12px", flexShrink: 0 }}><button onClick={() => handleViewRecord(r.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "6px 14px" }}>{expandedRecordId === r.id ? "收起" : "快速查看"}</button><Link href={`/tasks/${r.id}`} className="secondary-btn" style={{ fontSize: "12px", padding: "6px 14px" }}>完整详情</Link><button onClick={() => archiveMatchRecord(r.id)} className="secondary-btn" style={{ fontSize: "12px", padding: "6px 14px" }}>归档</button></div>
                </div>
                {expandedRecordId === r.id && historyDetail && (
                  <div style={{ marginTop: "8px", padding: "14px 16px", background: "white", borderRadius: "8px", border: "1px solid var(--line)" }}>
                    <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>原始需求</div>
                    <div style={{ fontSize: "14px", lineHeight: 1.7, marginBottom: "12px" }}>{historyDetail.requirement}</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                      {historyDetail.recommendations.slice(0, 3).map((rec, j) => {
                        const level = getRecommendLevel(rec.matchScore);
                        return (
                          <div key={j} style={{ padding: "10px 14px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                                <span style={{ fontSize: "13px", fontWeight: 600 }}>{j + 1}. {rec.partnerName}</span>
                                <span style={{ padding: "2px 8px", borderRadius: "999px", fontSize: "11px", fontWeight: 600, background: level.bg, color: level.color, border: `1px solid ${level.color}40` }}>{level.label}</span>
                              </div>
                              <span style={{ fontSize: "12px", color: "var(--brand)", fontWeight: 600 }}>匹配度: {rec.matchScore}</span>
                            </div>
                            <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px", lineHeight: 1.5 }}>{rec.recommendationReason || "暂无推荐理由"}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {expandedRecordId === r.id && !historyDetail && (
                  <div style={{ marginTop: "8px", padding: "14px 16px", background: "white", borderRadius: "8px", border: "1px solid var(--line)", textAlign: "center" }}>
                    <span style={{ fontSize: "13px", color: "var(--muted)" }}>加载中...</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

    </main>
  );
}
