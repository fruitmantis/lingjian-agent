"use client";
import {useAgent} from "@/components/agent-settings";
import { copyText } from "../lib/copy-text";
import {failureMessage} from "@/components/task-failure";

import Link from "next/link";
import { DevelopmentEntry } from "@/components/enablement-workspace";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, useEffect, useLayoutEffect, useRef, useCallback, type RefObject } from "react";
import { HOME_SCENES, type HomeScene, type HomeTaskMode } from "@/lib/scenes";
import { apiFetch } from "@/components/auth-provider";
import { NEW_TASK, taskLabels, useTaskNavigation } from "@/components/task-navigation";
import { UiIcon, type IconName } from "@/components/ui-icons";

const homeSceneIcons: Record<string, IconName> = {
  "home-ai-project": "users",
  "home-industry": "building",
  "home-capability": "puzzle",
  "home-development": "trend",
  "home-gap": "search",
  "home-project-readiness": "toolbox",
};

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

function getRecommendLevel(score: string): { label: string; color: string; bg: string } {
  const num = parseInt(score) || 0;
  if (num >= 80) return { label: "强推荐", color: "var(--brand-dark)", bg: "var(--brand-soft)" };
  if (num >= 50) return { label: "可考虑", color: "#e8a317", bg: "#fffbeb" };
  if (num >= 20) return { label: "备选", color: "var(--muted)", bg: "var(--bg-hover)" };
  return { label: "不推荐", color: "var(--danger)", bg: "#fef2f2" };
}

function parseTags(val: string): string[] {
  if (!val) return [];
  return val.split(/[,，]/).map(t => t.trim()).filter(Boolean);
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
        <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: bg, color, border: `1px solid ${border}`, fontWeight: 400 }}>{tag}</span>
      ))}
    </div>
  );
}

function ProjectMatchTask({active,requirement,setRequirement,inputRef,onBusyChange}:{
  active:boolean;requirement:string;setRequirement:(value:string)=>void;
  inputRef:RefObject<HTMLTextAreaElement|null>;onBusyChange:(busy:boolean)=>void;
}) {
  const agent=useAgent("partner_match");
  const searchParams = useSearchParams();
  const router = useRouter();
  const { submit, openCreatedTask, pending } = useTaskNavigation();
  const sameDraftPending = pending.some(task => task.requirement === requirement);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState("");
  const generation = useRef(0);
  const [submittedRequirement, setSubmittedRequirement] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [copiedRank, setCopiedRank] = useState<number | null>(null);
  const requirementInput = inputRef;
  const lastPrompt = useRef<string | null>(null);
  const submitting = useRef(false);
  useEffect(() => { onBusyChange(loading); }, [loading, onBusyChange]);

  useEffect(() => {
    if (searchParams.get("mode") === "development") {
      // The shared task provider retains pending work; a late match response
      // must not navigate away from the explicitly selected development mode.
      generation.current += 1; submitting.current = false;
      setActiveTaskId(null); setLoading(false); setTaskStatus("");
      setHasSearched(false); setSubmittedRequirement(""); setRecommendations([]); setError(null);
      return;
    }
    const prompt = searchParams.get("prompt");
    if (!prompt) lastPrompt.current = null;
    if (prompt && prompt !== lastPrompt.current) {
      lastPrompt.current = prompt;
      setRequirement(prompt);
      window.setTimeout(() => requirementInput.current?.focus(), 0);
    }
    setActiveTaskId(searchParams.get("task"));
    if (searchParams.get("view") === "history") router.replace("/tasks");
  }, [searchParams, router, setRequirement, requirementInput]);

  useEffect(() => {
    const reset = () => {
      generation.current += 1; submitting.current = false;
      setActiveTaskId(null); setRequirement(""); setSubmittedRequirement("");
      setRecommendations([]); setHasSearched(false); setLoading(false); setError(null); setTaskStatus("");
      requirementInput.current?.focus();
    };
    window.addEventListener(NEW_TASK, reset);
    return () => { generation.current += 1; window.removeEventListener(NEW_TASK, reset); };
  }, [setRequirement, requirementInput]);

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
          throw new Error(response.status === 404 ? "任务不存在或无权访问。" : "暂未确认结果，请刷新查看。");
        }
        const task = await response.json();
        if (cancelled) return;
        running = task.taskStatus === "matching" || task.taskStatus === "enriching";
        setSubmittedRequirement(task.requirement); setRecommendations(task.recommendations || []);
        setHasSearched(true); setTaskStatus(task.taskStatus); setLoading(running);
        setError(task.taskStatus === "failed" ? failureMessage(task.failureDetails) : null);
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
    if (submitting.current || loading || pending.some(task => task.requirement === reqText) || !reqText.trim()) return;
    submitting.current = true;
    const current = ++generation.current;
    setActiveTaskId(null); setLoading(true); setError(null); setHasSearched(true);
    setRecommendations([]); setCopiedRank(null); setTaskStatus("submitting");
    setSubmittedRequirement(reqText);
    try {
      const id = await submit(reqText);
      if (current !== generation.current) return;
      openCreatedTask(id, reqText, requirementInput.current?.closest("form") || null);
    } catch (reason) {
      if (current !== generation.current) return;
      setError(reason instanceof Error ? reason.message : "任务提交失败");
      setTaskStatus(""); setLoading(false);
    } finally {
      if (current === generation.current) submitting.current = false;
    }
  }

  async function handleCopy(rank: number, r: Recommendation) {
    const text = buildCopyText(submittedRequirement || requirement, r, rank);
    if (!await copyText(text)) { setError("复制失败，请选中内容按 Ctrl+C 手动复制。"); return; }
    setCopiedRank(rank);
    setTimeout(() => setCopiedRank(null), 2000);
  }

  const top3 = recommendations.slice(0, 3);

  return (
    <div hidden={!active} role="tabpanel" id="match-panel" aria-labelledby="match-tab">
      <section className="assistant-hero">
        <p className="assistant-subtitle">{agent.description}</p>{!agent.enabled&&<p className="notice-neutral" role="status">该智能体已停用，历史任务仍可查看。</p>}

        <form onSubmit={handleMatch} className="assistant-composer" data-task-composer>
          <label htmlFor="requirement" className="sr-only">输入项目需求</label>
          <textarea
            ref={requirementInput}
            id="requirement"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            required
            readOnly={loading}
            rows={4}
            maxLength={2000}
            placeholder="例如：寻找有金融行业数据库迁移经验、能够完成实施交付的伙伴…"
          />
          <div className="assistant-composer-footer">
            <span className="assistant-counter">{requirement.length}/2000</span>
            <button type="submit" disabled={!agent.enabled || loading || sameDraftPending || !requirement.trim()} className="assistant-submit" aria-label={loading ? (taskStatus === "submitting" ? "提交中" : "分析中") : "开始"}>
              {loading ? <span className="assistant-loading-dot" /> : <UiIcon name="send" size={18} />}<span>{loading ? (taskStatus === "submitting" ? "提交中" : "分析中") : "开始"}</span>
            </button>
          </div>
        </form>
      </section>

      {error && <p className="error-text assistant-error">{error}</p>}

      {/* 本次项目需求卡片 - only show after submit */}
      {!loading && !error && submittedRequirement && (
        <section className="card">
          <div className="ui-surface-heading">
            <h2 style={{ margin: 0 }}>本次项目需求</h2>
            <div className="ui-control-row">
              <button onClick={() => { const text = submittedRequirement; void copyText(text).then(ok => { if (!ok) setError("复制失败，请选中需求内容按 Ctrl+C 手动复制。"); }); }} className="secondary-btn" >复制需求</button>
              <button onClick={() => { setActiveTaskId(null); router.replace("/", { scroll: false }); setRequirement(submittedRequirement); setSubmittedRequirement(""); setRecommendations([]); setHasSearched(false); document.getElementById("requirement")?.focus(); }} className="secondary-btn" >重新编辑</button>
              <button onClick={() => { const req = submittedRequirement; handleMatchDirect(req); }} className="secondary-btn" style={{ color: "var(--brand)" }}>再次寻源</button>
            </div>
          </div>
          <div className="ui-inset">
            <p className="ui-reading-text" style={{ margin: 0, whiteSpace: "pre-wrap" }}>{submittedRequirement}</p>
          </div>
        </section>
      )}

      {/* Loading state */}
      {loading && taskStatus !== "submitting" && (
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
                  <div key={i} className="case-item ui-match-result">
                    <div style={{ marginTop: "12px" }}>
                      {/* Header: name + level + score + copy */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                          <span className="ui-match-rank">{rank}</span><h3 style={{ margin: 0 }}><a href={`/partners/${r.partnerId}`}>{r.partnerName}</a></h3>
                          <span style={{
                            padding: "3px 8px", borderRadius: "6px", fontSize: "13px", fontWeight: 400,
                            background: level.bg, color: level.color, border: `1px solid ${level.color}40`,
                          }}>{level.label}</span>
                        </div>
                        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                          <span className="score-tag">匹配度: {r.matchScore}</span>
                          <button onClick={() => void handleCopy(rank, r)} className="secondary-btn" >
                            {copiedRank === rank ? "已复制 ✓" : "复制推荐说明"}
                          </button>
                        </div>
                      </div>

                      {activeTaskId && <div className="enablement-actions"><Link className="secondary-btn" href={`/?mode=development&partner_id=${encodeURIComponent(r.partnerId)}&task_id=${encodeURIComponent(activeTaskId)}`}>针对该伙伴制定发展建议</Link></div>}

                      {/* Recommendation reason */}
                      <div className="ui-match-reason">
                        <div className="ui-field-caption">推荐理由</div>
                        <div className="ui-reading-text">{r.recommendationReason || "暂无推荐理由"}</div>
                      </div>

                      {/* Matched tags */}
                      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "12px" }}>
                        <div style={{ flex: "1 1 180px" }}>
                          <div className="ui-field-caption">匹配能力标签</div>
                          <TagPills tags={capTags} color="var(--brand-dark)" bg="var(--brand-soft)" border="var(--brand-border)" />
                        </div>
                        <div style={{ flex: "1 1 180px" }}>
                          <div className="ui-field-caption">匹配行业经验</div>
                          <TagPills tags={indTags} color="var(--success)" bg="#f0fdf4" border="#bbf7d0" />
                        </div>
                        <div style={{ flex: "1 1 180px" }}>
                          <div className="ui-field-caption">匹配覆盖区域</div>
                          <TagPills tags={areaTags} color="var(--accent-teal)" bg="var(--accent-teal-soft)" border="var(--accent-teal-border)" />
                        </div>
                      </div>

                      {/* Evidence */}
                      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "12px" }}>
                        <div className="ui-match-evidence">
                          <div className="ui-field-caption">支撑案例</div>
                          <div className="ui-reading-text">{r.evidenceCases || "暂无支撑案例"}</div>
                        </div>
                        <div className="ui-match-evidence">
                          <div className="ui-field-caption">支撑交付物</div>
                          <div className="ui-reading-text">{r.evidenceDeliverables || "暂无交付物证据"}</div>
                        </div>
                      </div>

                      {/* Risk notes */}
                      <div className="ui-risk-note">
                        <div >风险/缺口提示</div>
                        <div >{r.riskNotes || "暂无风险提示"}</div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}



    </div>
  );
}

export default function HomePage() {
  const matchAgent=useAgent("partner_match"),developmentAgent=useAgent("partner_development");
  const search=useSearchParams();
  const development=search.get("mode")==="development";
  const [drafts,setDrafts]=useState({match:"",development:""});
  const [busy,setBusy]=useState({match:false,development:false});
  const [focusRequest,setFocusRequest]=useState<{mode:HomeTaskMode;sequence:number}|null>(null);
  const matchInput=useRef<HTMLTextAreaElement>(null),developmentInput=useRef<HTMLTextAreaElement>(null);
  const changeMatch=useCallback((value:string)=>setDrafts(current=>({...current,match:value})),[]);
  const changeDevelopment=useCallback((value:string)=>setDrafts(current=>({...current,development:value})),[]);
  const matchBusy=useCallback((value:boolean)=>setBusy(current=>current.match===value?current:{...current,match:value}),[]);
  const developmentBusy=useCallback((value:boolean)=>setBusy(current=>current.development===value?current:{...current,development:value}),[]);
  useEffect(()=>{
    const reset=()=>{setDrafts({match:"",development:""});setFocusRequest(null);};
    window.addEventListener(NEW_TASK,reset);
    return()=>window.removeEventListener(NEW_TASK,reset);
  },[]);
  function selectMode(mode:HomeTaskMode) {
    const next=new URLSearchParams(search);
    if(mode==="development")next.set("mode","development");else next.delete("mode");
    next.delete("scene");next.delete("prompt");
    // Native history updates the existing page and retains authorized source context.
    window.history.replaceState(null,"",`/${next.size?`?${next}`:""}`);
  }
  function useScene(scene:HomeScene) {
    if(busy.match||busy.development)return;
    const current=drafts[scene.mode];
    const unchangedTemplate=HOME_SCENES.some(item=>item.mode===scene.mode&&item.prompt===current);
    if(current.trim()&&!unchangedTemplate&&!window.confirm("已有未提交内容，要替换成这个场景模板吗？"))return;
    setDrafts(value=>({...value,[scene.mode]:scene.prompt}));
    selectMode(scene.mode);
    setFocusRequest(value=>({mode:scene.mode,sequence:(value?.sequence||0)+1}));
  }
  useLayoutEffect(()=>{
    if(!focusRequest||(focusRequest.mode==="development")!==development)return;
    const input=focusRequest.mode==="development"?developmentInput.current:matchInput.current;
    if(!input)return;
    input.focus();
    const start=input.value.indexOf("【"),end=input.value.indexOf("】",start);
    if(start>=0&&end>start)input.setSelectionRange(start,end+1);
  },[focusRequest,development]);
  const currentDraft=development?drafts.development:drafts.match;
  return <div className={`page assistant-page unified-task-page${development?" development-task-page":""}`}>
    <header className="unified-task-heading"><div className="assistant-title"><h1>开启新任务</h1></div>
      <nav className="enablement-tabs task-mode-tabs" role="tablist" aria-label="任务模式">
        <button type="button" id="match-tab" role="tab" aria-selected={!development} aria-controls="match-panel" onClick={()=>selectMode("match")} className={!development?"active":""}><UiIcon name={matchAgent.icon} size={18}/>{matchAgent.name}</button>
        <button type="button" id="development-tab" role="tab" aria-selected={development} aria-controls="development-panel" onClick={()=>selectMode("development")} className={development?"active":""}><UiIcon name={developmentAgent.icon} size={18}/>{developmentAgent.name}</button>
      </nav>
    </header>
    <ProjectMatchTask active={!development} requirement={drafts.match} setRequirement={changeMatch} inputRef={matchInput} onBusyChange={matchBusy}/>
    {development&&<div role="tabpanel" id="development-panel" aria-labelledby="development-tab"><DevelopmentEntry direction={drafts.development} onDirectionChange={changeDevelopment} inputRef={developmentInput} onBusyChange={developmentBusy}/></div>}
    {!search.get("task")&&<section className="home-scenes" aria-label="需求场景">
      {/【[^】]+】/.test(currentDraft)&&<p className="home-template-hint" role="status">请将【】中的提示替换为实际需求，也可以直接改写。</p>}
      <div className="home-scene-buttons">
        {HOME_SCENES.map(scene=><button type="button" className="home-scene-button" key={scene.id} disabled={busy.match||busy.development} onClick={()=>useScene(scene)}><UiIcon name={homeSceneIcons[scene.id]} size={18} className="home-scene-icon"/><span>{scene.name}</span></button>)}
      </div>
    </section>}
  </div>;
}
