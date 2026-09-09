"use client";

import {INDUSTRIES, REGION_TYPES, standardValues} from "./business-taxonomy";
import styles from "./opportunity-ui.module.css";
export {styles as opportunityStyles};

type OpportunityField = "customerName" | "projectName" | "industry" | "region" | "projectStage" | "businessNeeds" | "technicalNeeds" | "deliveryNeeds" | "qualificationRequirements" | "caseRequirements" | "onsiteRequirement" | "timelineRequirement" | "cloudPlatformPreference" | "matchedCapabilityTags" | "unmatchedCapabilitySignals" | "recommendedPartnerNames" | "missingFields" | "followUpQuestions";
export type Opportunity = Record<OpportunityField, string | null> & {
  id: string; matchRecordId: string | null; requirementText: string;
  supplyStatus: string | null; completenessScore: number;
  classification_pending?: Record<string, string[]>;
};

export function OpportunityFilter({kind, value, onChange}: {kind: "industry" | "region"; value: string; onChange: (value: string) => void}) {
  const label = kind === "industry" ? "行业" : "区域";
  const selected = standardValues(value, kind);
  const groups = kind === "industry" ? [{name: "行业", values: INDUSTRIES}] : [{name: "国内", values: REGION_TYPES.domestic}, {name: "海外", values: REGION_TYPES.overseas}];
  return <div className={styles.field}><span>{label}</span>
    <details className={styles.filter} onKeyDown={event => {if (event.key === "Escape") {event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus();}}} onBlur={event => {if (!event.currentTarget.contains(event.relatedTarget as Node)) event.currentTarget.open = false;}}>
      <summary aria-label={`${label}筛选`}><span>{selected.length ? `已选 ${selected.length} 项` : `全部${label}`}</span><span aria-hidden="true">⌄</span></summary>
      <div className={styles.popover} role="group" aria-label={`${label}选项`}>
        <div className={styles.filterHeader}><span>可多选</span><button type="button" className="text-btn" onClick={() => onChange("")}>清除</button></div>
        {groups.map(group => <fieldset key={group.name}><legend>{group.name}</legend>{group.values.map(item => <label key={item}><input type="checkbox" checked={selected.includes(item)} onChange={event => onChange((event.target.checked ? [...selected, item] : selected.filter(value => value !== item)).join(","))}/>{item}</label>)}</fieldset>)}
      </div>
    </details>
  </div>;
}

function text(value: string | null | undefined) {return value?.trim() || "未知";}
function questions(value: string | null) {
  if (!value) return [];
  try {const parsed: unknown = JSON.parse(value); if (Array.isArray(parsed)) return parsed.filter((item): item is string => typeof item === "string" && !!item.trim());} catch {}
  return [value];
}
export function OpportunityDetails({opportunity: o}: {opportunity: Opportunity}) {
  const fields: [OpportunityField, string][] = [
    ["businessNeeds", "业务需求"], ["technicalNeeds", "技术需求"], ["deliveryNeeds", "交付需求"],
    ["qualificationRequirements", "资质要求"], ["caseRequirements", "案例要求"], ["onsiteRequirement", "驻场要求"],
    ["timelineRequirement", "时间要求"], ["cloudPlatformPreference", "云平台偏好"],
    ["matchedCapabilityTags", "匹配能力"], ["unmatchedCapabilitySignals", "能力缺口"], ["recommendedPartnerNames", "推荐伙伴"],
  ];
  const followups = questions(o.followUpQuestions);
  return <section className={styles.detail} id={`opportunity-${o.id}`} aria-label="项目详情">
    <header><h3>{text(o.projectName)}</h3>{o.matchRecordId && <a href={`/tasks/${encodeURIComponent(o.matchRecordId)}`}>查看原始匹配任务 →</a>}</header>
    <div className={styles.requirement}><h4>原始项目需求</h4><p>{text(o.requirementText)}</p></div>
    <dl className={styles.detailGrid}>{fields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{text(o[key])}</dd></div>)}</dl>
    {followups.length > 0 && <div className={styles.questions}><h4>待补充信息</h4><ul>{followups.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
  </section>;
}
