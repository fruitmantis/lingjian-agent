"use client";
import {ClassificationFields, ClassificationNotice} from "@/components/business-taxonomy";


import Link from "next/link";
import {DevelopmentPlanDetail} from "../../../components/development-assistant";
import { FormEvent, use, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "../../../components/auth-provider";

import { tasksChanged } from "../../../components/task-navigation";

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
  task_type: string;
  id: string; requirement: string; recommendations: Recommendation[]; createdAt: string;
  createdBy: string | null; archivedAt: string | null; demandProfile: Record<string, string | number | null> | null;
  opportunity: Opportunity | null; taskStatus: "matching" | "enriching" | "ready" | "partial" | "failed";
  lastErrorStage: string | null;
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
  if (!value?.trim()) return "暂无待补充问题";
  try {
    const questions: unknown = JSON.parse(value);
    if (Array.isArray(questions)) {
      return questions.filter((question): question is string => typeof question === "string" && Boolean(question.trim()))
        .map(question => question.trim()).join("；") || "暂无待补充问题";
    }
    return "待补充问题暂无法展示";
  } catch {
    return value.trim().startsWith("[") || value.trim().startsWith("{") || value.trim().startsWith("```")
      ? "待补充问题暂无法展示" : value;
  }
}

export default function TaskDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const returnHref = searchParams.get("from") === "admin" ? "/admin/tasks" : "/tasks";
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
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "任务加载失败");
      const data = await response.json() as TaskDetail;
      if (version !== loadVersion.current) return;
      setTask(data);
      if (data.opportunity && (!quiet || formOpportunityId.current !== data.opportunity.id)) setForm(Object.fromEntries(editableFields.map(field => [field.key, data.opportunity?.[field.key] == null ? "" : String(data.opportunity[field.key])])));
      formOpportunityId.current = data.opportunity?.id || null;
    } catch (reason) { if (version === loadVersion.current) setError(quiet ? "状态更新暂不可用，将自动重试查询。" : reason instanceof Error ? reason.message : "任务加载失败"); } finally { if (version === loadVersion.current) setLoading(false); }
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
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "重试失败");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重试失败");
    } finally {
      setRetrying(false); tasksChanged();
    }
  }

  if (task?.task_type === "development_plan") return <DevelopmentPlanDetail key={id} id={id}/>;
  if (loading) return <main className="page"><p>任务加载中...</p></main>;
  if (!task) return <main className="page"><div className="card empty-state"><h1>无法查看任务</h1><p className="error-text">{error || "任务不存在"}</p><div className="table-actions"><button className="secondary-btn" onClick={() => void load()}>重试</button><Link href={returnHref} className="btn-primary-lg">返回任务列表</Link></div></div></main>;

  return (
    <main className="page">
      <div className="page-heading-row"><div><h1>任务详情</h1><span className="enablement-badge">{task.task_type === "development_plan" ? "能力发展" : "项目找伙伴"}</span><p className="lead">创建于 {new Date(task.createdAt).toLocaleString("zh-CN")} · 创建人 {task.createdBy || "历史数据"}</p></div><Link href={returnHref} className="secondary-btn">返回任务列表</Link></div>
      {error && <div className="inline-error-actions"><p className="error-text">{error}</p><button className="secondary-btn" onClick={() => void load()}>重新加载</button></div>}
      {(task.task_type || "partner_match") === "partner_match" ? <>
      {task.taskStatus !== "ready" && <div className={`${task.taskStatus === "failed" ? "notice-error" : "notice-warning"} task-status-notice`}><strong>{taskStatusText[task.taskStatus]}</strong>{task.lastErrorStage && <span>未完成环节：{errorStageText(task.lastErrorStage)}</span>}{(task.taskStatus === "partial" || task.taskStatus === "failed") && <button onClick={() => void retryTask()} disabled={retrying}>{retrying ? "重试中..." : "重试任务"}</button>}</div>}
      <section className="card"><h2>项目需求</h2><p className="requirement-block">{task.requirement}</p></section>
      <section className="card"><h2>推荐伙伴</h2>{task.recommendations.length === 0 ? <p className="placeholder-text">暂未生成推荐结果。</p> : <div className="recommendation-stack">{task.recommendations.map((item, index) => (
        <article className="recommendation-item" key={item.partnerId}>
          <div className="recommendation-title"><span className="rank-badge">{index + 1}</span><div><h3>{item.partnerName}</h3><span>匹配分 {item.matchScore}</span></div><Link href={`/partners/${item.partnerId}`} className="secondary-btn">查看伙伴</Link></div>
          <div className="evidence-grid"><div><strong>匹配能力</strong><p>{text(item.matchedCapabilities)}</p></div><div><strong>行业经验</strong><p>{text(item.matchedIndustries)}</p></div><div><strong>覆盖区域</strong><p>{text(item.matchedRegions)}</p></div><div><strong>推荐理由</strong><p>{text(item.recommendationReason)}</p></div><div><strong>支撑案例</strong><p>{text(item.evidenceCases)}</p></div><div><strong>支撑交付物</strong><p>{text(item.evidenceDeliverables)}</p></div></div>
          <div className="risk-note"><strong>风险或缺口</strong><p>{text(item.riskNotes)}</p></div>
          <div className="enablement-actions"><Link className="secondary-btn" href={`/?mode=development&partner_id=${encodeURIComponent(item.partnerId)}&task_id=${encodeURIComponent(task.id)}`}>针对该伙伴制定发展建议</Link></div>
        </article>
      ))}</div>}</section>
      {task.demandProfile && <section className="card"><h2>需求画像</h2><div className="detail-grid">{Object.entries({
        "行业标签": task.demandProfile.industryTags, "能力标签": task.demandProfile.capabilityTags,
        "交付类型": task.demandProfile.deliveryTypeTags, "项目区域": task.demandProfile.regionTags,
        "复杂度": task.demandProfile.complexityLevel, "紧急程度": task.demandProfile.urgencyLevel,
        "项目关键词": task.demandProfile.projectKeywords, "供给状态": supplyText(task.demandProfile.supplyStatus),
        "缺口分析": task.demandProfile.gapAnalysis,
      }).map(([label, value]) => <div key={label}><span>{label}</span><strong>{text(value)}</strong></div>)}</div></section>}
      {task.opportunity && <section className="card"><div className="section-heading-row"><div><h2>项目机会</h2><p>可补充业务字段，AI 抽取字段保持只读。</p></div><span className="score-chip">完整度 {task.opportunity.completenessScore}%</span></div>
        <ClassificationNotice pending={task.opportunity.classification_pending}/><form onSubmit={saveOpportunity} className="form-grid">{editableFields.filter(field=>!["industry","region"].includes(field.key)).map(field => <div className={`form-row ${field.multiline ? "form-span-two" : ""}`} key={field.key}><label>{field.label}</label>{field.multiline ? <textarea rows={3} value={form[field.key] || ""} onChange={event => setForm(current => ({ ...current, [field.key]: event.target.value }))} /> : <input value={form[field.key] || ""} onChange={event => setForm(current => ({ ...current, [field.key]: event.target.value }))} />}</div>)}<ClassificationFields industries={form.industry||""} regions={form.region||""} onIndustries={industry=>setForm(current=>({...current,industry}))} onRegions={region=>setForm(current=>({...current,region}))}/><div className="form-span-two"><button disabled={saving}>{saving ? "保存中..." : "保存项目信息"}</button></div></form>
        <div className="detail-grid readonly-grid">{Object.entries({
          "技术需求": task.opportunity.technicalNeeds, "交付要求": task.opportunity.deliveryNeeds,
          "资质要求": task.opportunity.qualificationRequirements, "案例要求": task.opportunity.caseRequirements,
          "驻场要求": task.opportunity.onsiteRequirement, "时间要求": task.opportunity.timelineRequirement,
          "云平台偏好": task.opportunity.cloudPlatformPreference, "能力标签": task.opportunity.matchedCapabilityTags,
          "推荐伙伴": task.opportunity.recommendedPartnerNames, "供给状态": supplyText(task.opportunity.supplyStatus),
          "待补充问题": questionsText(task.opportunity.followUpQuestions),
        }).map(([label, value]) => <div key={label}><span>{label}</span><strong>{text(value)}</strong></div>)}</div>
      </section>}
      </> : <section className="card"><p>此类型任务的业务详情尚未开放。</p></section>}
    </main>
  );
}
