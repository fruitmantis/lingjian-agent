"use client";
import {AgentBadge} from "./agent-settings";
import {TaskRequest,TaskResult,TaskArrivalReadError} from "./task-transition";
import {TaskProgress,type TaskProgressData} from "./task-progress";
import {AdvisorAnswer} from "./advisor-answer";
import {ClassificationFields, ClassificationNotice} from "@/components/business-taxonomy";


import {FailureNotice,type FailureDetail} from "./task-failure";
import Link from "next/link";
import { CardEntry } from "./card-entry";
import {DevelopmentPlanDetail} from "./development-assistant";
import { FormEvent, use, useEffect, useId, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { apiFetch } from "./auth-provider";
import {responseError} from "../lib/api-request";

import { tasksChanged } from "./task-navigation";

type Recommendation = {
  partnerId: string; partnerName: string; matchScore: string; matchedCapabilities: string;
  matchedIndustries: string; matchedRegions: string; recommendationReason: string;
  evidenceCases: string; evidenceDeliverables: string; riskNotes: string;
};
type Opportunity = { classification_pending?:Record<string,string[]>;
  id: string; customerName: string; projectName: string; industry: string; region: string;
  projectStage: string; businessNeeds: string; technicalNeeds: string; deliveryNeeds: string;
  qualificationRequirements: string; caseRequirements: string; onsiteRequirement: string;
  timelineRequirement: string; cloudPlatformPreference: string; matchedCapabilityTags: string;
  unmatchedCapabilitySignals: string; recommendedPartnerNames: string; supplyStatus: string;
  completenessScore: number; missingFields: string; followUpQuestions: string; updatedAt: string;
};
type TaskDetail = {
  progress?:TaskProgressData|null; understanding?:Record<string,unknown>|null; scopeMessage?:string|null;
  answer?: string;
  task_type: string;
  id: string; requirement: string; recommendations: Recommendation[]; createdAt: string;
  createdBy: string | null; archivedAt: string | null; demandProfile: Record<string, string | number | null> | null;
  opportunity: Opportunity | null; taskStatus: "matching" | "enriching" | "ready" | "partial" | "failed";
  lastErrorStage: string | null; failureDetails?: FailureDetail[];
};

const taskStatusText = {
  matching: "正在匹配伙伴，状态会自动更新。",
  enriching: "伙伴匹配已完成，正在生成需求画像和项目机会。",
  ready: "任务已完成。",
  partial: "伙伴匹配已保存，但需求画像或项目机会尚未完整生成。",
  failed: "伙伴匹配未完成，需求已保留，可重新执行。",
};
const errorStageLabels: Record<string, string> = {
  partner_match: "伙伴匹配", partner_data: "伙伴数据读取", demand_profile: "需求画像",
  project_opportunity: "项目机会", recommendation_data: "推荐结果", persistence: "结果保存", interrupted: "异常中断",
};

function errorStageText(value: string): string {
  return value.split(",").map(stage => errorStageLabels[stage] || "后续处理").join("、");
}

const editableFields: { key: keyof Opportunity; label: string; multiline?: boolean }[] = [
  { key: "customerName", label: "客户名称" }, { key: "projectName", label: "项目名称" },
  { key: "industry", label: "所属行业" }, { key: "region", label: "项目区域" },
  { key: "projectStage", label: "项目阶段" }, { key: "businessNeeds", label: "业务需求", multiline: true },
];

function text(value: unknown): string { return value == null || value === "" ? "未识别" : String(value); }

function supplyText(value: unknown): string {
  const labels: Record<string, string> = { sufficient: "供给充足", partial: "部分满足", gap: "明显缺口" };
  return typeof value === "string" ? labels[value] || "未识别" : "未识别";
}

function questionsText(value: string): string {
  if (!value?.trim()) return "";
  try {
    const questions: unknown = JSON.parse(value);
    if (Array.isArray(questions)) {
      return questions.filter((question): question is string => typeof question === "string" && Boolean(question.trim()))
        .map(question => question.trim()).join("；") || "";
    }
    return "待补充问题暂无法展示";
  } catch {
    return value.trim().startsWith("[") || value.trim().startsWith("{") || value.trim().startsWith("```")
      ? "待补充问题暂无法展示" : value;
  }
}

export default function TaskDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <TaskDetail key={id} id={id}/>;
}

function TaskDetail({id}:{id:string}) {
  const opportunityFieldPrefix = useId() + "-opportunity-";
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const returnHref = pathname.startsWith("/admin") ? "/admin/tasks" : "/tasks";
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadVersion = useRef(0);
  const pollBusy = useRef(false);
  const formOpportunityId = useRef<string | null>(null);

  async function load(quiet = false) {
    const version = ++loadVersion.current;
    if (!quiet) setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(`/agent/tasks/${id}`, { cache: "no-store" });
      if (!response.ok) throw await responseError(response);
      const data = await response.json() as TaskDetail;
      if (version !== loadVersion.current) return;
      setTask(data);
      if (data.opportunity && (!quiet || formOpportunityId.current !== data.opportunity.id)) setForm(Object.fromEntries(editableFields.map(field => [field.key, data.opportunity?.[field.key] == null ? "" : String(data.opportunity[field.key])])));
      formOpportunityId.current = data.opportunity?.id || null;
    } catch (reason) { if (version === loadVersion.current) setError(quiet ? "暂未确认结果，请刷新查看。" : reason instanceof Error ? reason.message : "任务加载失败"); } finally { if (version === loadVersion.current) setLoading(false); }
  }

  useEffect(() => {
    setTask(null); formOpportunityId.current = null;
    void load();
    return () => { loadVersion.current += 1; };
  }, [id]);

  useEffect(() => {
    if (!task || (!retrying && !["matching", "enriching"].includes(task.taskStatus))) return;
    const timer = window.setInterval(async () => {
      if (document.hidden || pollBusy.current) return;
      pollBusy.current = true;
      try { await load(true); } finally { pollBusy.current = false; }
    }, 3000);
    return () => clearInterval(timer);
  }, [id, task?.taskStatus, retrying]);

  async function saveOpportunity(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(null);
    try {
      const response = await apiFetch(`/agent/tasks/${id}/opportunity`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "保存失败");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function retryTask() {
    if (!confirm("将重新执行该任务未完成的处理步骤，确定继续？")) return;
    setRetrying(true); setError(null);
    try {
      const response = await apiFetch(`/agent/tasks/${id}/retry`, { method: "POST" });
      if (!response.ok) throw await responseError(response);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重试失败");
    } finally {
      setRetrying(false); tasksChanged();
    }
  }

  if (task?.task_type === "development_plan") return <DevelopmentPlanDetail key={id} id={id}/>;
  if (loading) return <main className="page"><p>任务加载中...</p></main>;
  if (!task) return <main className="page match-detail"><TaskArrivalReadError id={id}/><div className="card empty-state"><h1>无法查看任务</h1><p className="error-text">{error || "任务不存在"}</p><div className="table-actions"><button className="secondary-btn" onClick={() => void load()}>重试</button><Link href={returnHref} className="btn-primary-lg">返回任务列表</Link></div></div></main>;

  return (
    <main className="page match-detail">
      <div className="page-heading-row"><div><h1>任务详情</h1><AgentBadge id={task.task_type === "development_plan" ? "partner_development" : "partner_match"}/><p className="lead">创建于 {new Date(task.createdAt).toLocaleString("zh-CN")} · 创建人 {task.createdBy || "历史数据"}</p></div><Link href={returnHref} className="secondary-btn">返回任务列表</Link></div>
      {error && <div className="inline-error-actions"><p className="error-text">{error}</p><button className="secondary-btn" onClick={() => void load()}>重新加载</button></div>}
      {(task.task_type || "partner_match") === "partner_match" ? <>
      {(task.taskStatus === "partial" || task.taskStatus === "failed") ? <FailureNotice details={task.failureDetails} stages={task.lastErrorStage} partial={task.recommendations.length>0} title={task.recommendations.length>0?"部分完成 · 伙伴推荐可用":"本次匹配未完成"} impact={task.recommendations.length>0?"已保存的伙伴推荐可继续查看。重试将补充未完成的步骤。":"项目需求已保留，可重新执行。"}><button onClick={()=>void retryTask()} disabled={retrying||!!task.archivedAt}>{retrying?"重试中…":"重试"}</button></FailureNotice> : task.taskStatus!=="ready" && <div className="notice-warning task-status-notice"><strong>{taskStatusText[task.taskStatus]}</strong></div>}
      <TaskRequest id={id}>{task.requirement}</TaskRequest>
      <TaskProgress value={task.progress} taskId={id}/>
      {task.scopeMessage&&<TaskResult id={id} className="card task-answer" testId="scope-result"><p>{task.scopeMessage}</p></TaskResult>}
      {task.understanding&&<TaskResult id={id} className="card" testId="task-understanding"><h2>需求理解</h2><div className="detail-grid">{Object.entries({"业务需求":task.understanding.businessNeeds,"技术需求":task.understanding.technicalNeeds,"交付要求":task.understanding.deliveryNeeds,"行业":task.understanding.industry,"区域":task.understanding.region,"时间要求":task.understanding.timelineRequirement}).filter(([,value])=>value&&value!=="未知").map(([label,value])=><div key={label as string}><span>{label as string}</span><strong>{String(value)}</strong></div>)}</div></TaskResult>}
      {task.answer&&<TaskResult id={id} className="card task-answer"><AdvisorAnswer text={task.answer}/></TaskResult>}
      {!task.scopeMessage&&<TaskResult id={id} className="card"><h2>推荐伙伴</h2>{task.recommendations.length === 0 ? <p className="placeholder-text">{task.taskStatus==="ready"||task.taskStatus==="partial"?"本次暂无正式推荐，请参考上方分析说明。":"暂未生成推荐结果。"}</p> : <div className="recommendation-stack">{task.recommendations.map((item, index) => (
        <TaskResult as="article" id={id} className="recommendation-item" key={item.partnerId}>
          <div className="recommendation-title"><span className="rank-badge">{index + 1}</span><div><h3>{item.partnerName}</h3><span>匹配分 {item.matchScore}</span></div><CardEntry href={`/partners/${item.partnerId}`}>查看伙伴</CardEntry></div>
          <div className="evidence-grid">{Object.entries({"匹配能力":item.matchedCapabilities,"行业经验":item.matchedIndustries,"覆盖区域":item.matchedRegions,"推荐理由":item.recommendationReason,"支撑案例":item.evidenceCases,"支撑交付物":item.evidenceDeliverables}).filter(([,value])=>value&&!["未核实","未提供可核实的支撑案例","未提供可核实的支撑交付物"].includes(value)).map(([label,value])=><div key={label}><strong>{label}</strong><p>{value}</p></div>)}</div>
          {item.riskNotes&&<div className="risk-note"><strong>沟通重点</strong><p>{item.riskNotes}</p></div>}
          <div className="enablement-actions"><Link className="secondary-btn" href={`/?mode=development&partner_id=${encodeURIComponent(item.partnerId)}&task_id=${encodeURIComponent(task.id)}`}>针对该伙伴制定发展建议</Link></div>
        </TaskResult>
      ))}</div>}</TaskResult>}
      {task.demandProfile && <TaskResult id={id} className="card"><h2>需求画像</h2><div className="detail-grid">{Object.entries({
        "行业标签": task.demandProfile.industryTags, "能力标签": task.demandProfile.capabilityTags,
        "交付类型": task.demandProfile.deliveryTypeTags, "项目区域": task.demandProfile.regionTags,
        "复杂度": task.demandProfile.complexityLevel, "紧急程度": task.demandProfile.urgencyLevel,
        "项目关键词": task.demandProfile.projectKeywords, "供给状态": supplyText(task.demandProfile.supplyStatus),
      }).map(([label, value]) => <div key={label}><span>{label}</span><strong>{text(value)}</strong></div>)}</div></TaskResult>}
      {task.opportunity && <TaskResult id={id} className="card"><div className="section-heading-row"><div><h2>项目机会</h2><p>可补充业务字段，AI 抽取字段保持只读。</p></div><span className="score-chip">完整度 {task.opportunity.completenessScore}%</span></div>
        <ClassificationNotice pending={task.opportunity.classification_pending}/><form onSubmit={saveOpportunity} className="form-grid">{editableFields.filter(field=>!["industry","region"].includes(field.key)).map(field => <div className={`form-row ${field.multiline ? "form-span-two" : ""}`} key={field.key}><label htmlFor={opportunityFieldPrefix + field.key}>{field.label}</label>{field.multiline ? <textarea id={opportunityFieldPrefix + field.key} rows={3} value={form[field.key] || ""} onChange={event => setForm(current => ({ ...current, [field.key]: event.target.value }))} /> : <input id={opportunityFieldPrefix + field.key} value={form[field.key] || ""} onChange={event => setForm(current => ({ ...current, [field.key]: event.target.value }))} />}</div>)}<ClassificationFields industries={form.industry||""} regions={form.region||""} onIndustries={industry=>setForm(current=>({...current,industry}))} onRegions={region=>setForm(current=>({...current,region}))}/><div className="form-span-two"><button disabled={saving}>{saving ? "保存中..." : "保存项目信息"}</button></div></form>
        <div className="detail-grid readonly-grid">{Object.entries({
          "技术需求": task.opportunity.technicalNeeds, "交付要求": task.opportunity.deliveryNeeds,
          "资质要求": task.opportunity.qualificationRequirements, "案例要求": task.opportunity.caseRequirements,
          "驻场要求": task.opportunity.onsiteRequirement, "时间要求": task.opportunity.timelineRequirement,
          "云平台偏好": task.opportunity.cloudPlatformPreference, "能力标签": task.opportunity.matchedCapabilityTags,
          "推荐伙伴": task.opportunity.recommendedPartnerNames, "供给状态": supplyText(task.opportunity.supplyStatus),
          "待补充问题": questionsText(task.opportunity.followUpQuestions),
        }).filter(([label,value])=>label!=="待补充问题"||!!value).map(([label, value]) => <div key={label}><span>{label}</span><strong>{text(value)}</strong></div>)}</div>
      </TaskResult>}
      </> : <section className="card"><p>此类型任务的业务详情尚未开放。</p></section>}
    </main>
  );
}
