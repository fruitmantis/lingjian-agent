"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, useEffect, useRef } from "react";
import { ENABLED_SCENES } from "@/lib/scenes";
import { apiFetch } from "@/components/auth-provider";
import { NEW_TASK, taskLabels, useTaskNavigation } from "@/components/task-navigation";
import { LingjianMark, UiIcon, type IconName } from "@/components/ui-icons";

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

const HOME_CATEGORIES = ["猜你想做", "智能匹配", "伙伴洞察", "能力发展", "项目机会", "运营分析"] as const;
type HomeCategory = (typeof HOME_CATEGORIES)[number];

function sceneIcon(category: string): IconName {
  if (category === "智能匹配") return "spark";
  if (category === "伙伴洞察") return "users";
  if (category === "能力发展") return "chart";
  if (category === "项目机会") return "file";
  return "grid";
}

function sceneTone(category: string): string {
  if (category === "智能匹配") return "match";
  if (category === "伙伴洞察") return "partner";
  if (category === "能力发展") return "capability";
  if (category === "项目机会") return "opportunity";
  return "operations";
}

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
  const router = useRouter();
  const { submit } = useTaskNavigation();
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState("");
  const generation = useRef(0);
  const [requirement, setRequirement] = useState("");
  const [submittedRequirement, setSubmittedRequirement] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [copiedRank, setCopiedRank] = useState<number | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<HomeCategory>("猜你想做");
  const [sceneOffset, setSceneOffset] = useState(0);
  const requirementInput = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const prompt = searchParams.get("prompt");
    if (prompt) {
      setRequirement(prompt);
      window.setTimeout(() => requirementInput.current?.focus(), 0);
    }
    setActiveTaskId(searchParams.get("task"));
    if (searchParams.get("view") === "history") router.replace("/tasks");
  }, [searchParams, router]);

  useEffect(() => {
    const reset = () => {
      generation.current += 1;
      setActiveTaskId(null); setRequirement(""); setSubmittedRequirement("");
      setRecommendations([]); setHasSearched(false); setLoading(false); setError(null); setTaskStatus("");
      requirementInput.current?.focus();
    };
    window.addEventListener(NEW_TASK, reset);
    return () => { generation.current += 1; window.removeEventListener(NEW_TASK, reset); };
  }, []);

  useEffect(() => {
    if (!activeTaskId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      if (document.hidden) { timer = setTimeout(poll, 3000); return; }
      let running = true;
      try {
        const response = await apiFetch(`/agent/tasks/${activeTaskId}`, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]) });
        if (!response.ok) {
          if (response.status === 404) running = false;
          throw new Error(response.status === 404 ? "任务不存在或无权访问。" : "暂未获取最新状态，将自动重试查询。");
        }
        const task = await response.json();
        if (cancelled) return;
        running = task.taskStatus === "matching" || task.taskStatus === "enriching";
        setSubmittedRequirement(task.requirement); setRecommendations(task.recommendations || []);
        setHasSearched(true); setTaskStatus(task.taskStatus); setLoading(running);
        setError(task.taskStatus === "failed" ? "匹配未完成，需求已保存，可进入任务详情重试。" : null);
      } catch (reason) {
        if (!cancelled) { setError(reason instanceof Error ? reason.message : "状态更新暂不可用"); if (!running) setLoading(false); }
      }
      if (!cancelled && running) timer = setTimeout(poll, 3000);
    }
    setLoading(true); setHasSearched(true);
    void poll();
    return () => { cancelled = true; controller.abort(); clearTimeout(timer); };
  }, [activeTaskId]);

  function handleMatch(event: React.FormEvent) {
    event.preventDefault();
    void handleMatchDirect(requirement);
  }

  async function handleMatchDirect(reqText: string) {
    if (!reqText.trim()) return;
    const current = ++generation.current;
    setActiveTaskId(null); setLoading(true); setError(null); setHasSearched(true);
    setRecommendations([]); setCopiedRank(null); setTaskStatus("submitting");
    setSubmittedRequirement(reqText);
    try {
      const id = await submit(reqText);
      if (current !== generation.current) return;
      setRequirement(""); setTaskStatus("matching"); setActiveTaskId(id);
      router.replace(`/?task=${encodeURIComponent(id)}`, { scroll: false });
    } catch (reason) {
      if (current !== generation.current) return;
      setError(reason instanceof Error ? reason.message : "任务提交失败");
      setTaskStatus(""); setLoading(false);
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
  const scenePool = selectedCategory === "猜你想做" ? featuredScenes : ENABLED_SCENES.filter(scene => scene.category === selectedCategory);
  const visibleScenes = scenePool.length <= 4
    ? scenePool
    : Array.from({ length: 4 }, (_, index) => scenePool[(sceneOffset + index) % scenePool.length]);

  return (
    <main className="page assistant-page">
      <section className="assistant-hero">
        <div className="assistant-title"><LingjianMark size={48} /><h1>灵鉴助手</h1></div>
        <p className="assistant-subtitle">懂伙伴、懂能力、懂项目，智能匹配好伙伴</p>

        <form onSubmit={handleMatch} className="assistant-composer">
          <label htmlFor="requirement" className="sr-only">输入项目需求</label>
          <textarea
            ref={requirementInput}
            id="requirement"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            required
            rows={4}
            maxLength={2000}
            placeholder="输入项目需求，或告诉我您想完成什么…"
          />
          <div className="assistant-composer-footer">
            <span className="assistant-counter">{requirement.length}/2000</span>
            <button type="submit" disabled={loading || !requirement.trim()} className="assistant-submit" aria-label={loading ? "分析中" : "开始任务"}>
              {loading ? <span className="assistant-loading-dot" /> : <UiIcon name="send" size={20} />}
            </button>
          </div>
        </form>
      </section>

      <section className="assistant-section" aria-labelledby="featured-heading">
        <h2 className="sr-only" id="featured-heading">猜你想做</h2>
        <div className="assistant-category-row">
          <div className="assistant-category-tabs" role="tablist" aria-label="推荐场景分类">
            {HOME_CATEGORIES.map(item => <button key={item} type="button" role="tab" aria-selected={selectedCategory === item} className={selectedCategory === item ? "active" : ""} onClick={() => { setSelectedCategory(item); setSceneOffset(0); }}>{item}</button>)}
          </div>
          <button type="button" className="assistant-refresh" onClick={() => setSceneOffset(current => scenePool.length ? (current + 4) % scenePool.length : 0)}><UiIcon name="refresh" size={16} /><span>换一批</span></button>
        </div>
        <div className="featured-scene-grid">
          {visibleScenes.map((scene) => {
            const content = (
              <>
                <div className="featured-scene-heading">
                  <span className={`scene-line-icon scene-tone-${sceneTone(scene.category)}`}><UiIcon name={sceneIcon(scene.category)} size={20} /></span>
                  <h3>{scene.name}</h3>
                </div>
                <p>{scene.description}</p>
                <ul className="featured-scene-queries">{scene.exampleQueries.slice(0, 2).map(query => <li key={query}>{query}</li>)}</ul>
                <div className="featured-scene-action">{scene.actionLabel}<UiIcon name="send" size={15} /></div>
              </>
            );
            return scene.actionHref ? <Link className="featured-scene-card" href={scene.actionHref} key={scene.id}>{content}</Link> : <article className="featured-scene-card disabled" key={scene.id}>{content}</article>;
          })}
        </div>
      </section>

      {error && <p className="error-text assistant-error">{error}</p>}

      {/* 本次项目需求卡片 - only show after submit */}
      {!loading && submittedRequirement && (
        <section className="card" style={{ borderColor: "var(--brand)", borderWidth: "1px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <h2 style={{ margin: 0 }}>本次项目需求</h2>
            <div style={{ display: "flex", gap: "8px" }}>
              <button onClick={() => { const text = submittedRequirement; copyToClipboard(text); }} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>复制需求</button>
              <button onClick={() => { setActiveTaskId(null); router.replace("/", { scroll: false }); setRequirement(submittedRequirement); setSubmittedRequirement(""); setRecommendations([]); setHasSearched(false); document.getElementById("requirement")?.focus(); }} className="secondary-btn" style={{ fontSize: "12px", padding: "4px 12px" }}>重新编辑</button>
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
          <h2>{taskLabels[taskStatus] || "正在更新任务状态"}</h2>
          <p role="status" style={{ marginTop: "16px", lineHeight: 1.8 }}>{taskStatus === "submitting" ? "正在保存项目需求…" : "任务会自动更新，您可以切换页面或开启新任务。"}{activeTaskId && <> <Link href={`/tasks/${activeTaskId}`}>查看任务详情</Link></>}</p>
        </section>
      )}

      {!loading && activeTaskId && <p className="current-task-summary"><span className={`status-badge task-${taskStatus}`}>{taskLabels[taskStatus] || "状态待确认"}</span> <Link href={`/tasks/${activeTaskId}`}>查看任务详情</Link>{taskStatus === "partial" && " · 匹配结果已保存，后续处理可在详情页重试。"}</p>}

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

    </main>
  );
}
