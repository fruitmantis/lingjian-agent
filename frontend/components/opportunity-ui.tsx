"use client";

import {INDUSTRIES, REGION_TYPES, standardValues} from "./business-taxonomy";
import {useEffect, useId, useRef, useState} from "react";
import styles from "./opportunity-ui.module.css";
export {styles as opportunityStyles};

type OpportunityField = "customerName" | "projectName" | "industry" | "region" | "projectStage" | "businessNeeds" | "technicalNeeds" | "deliveryNeeds" | "qualificationRequirements" | "caseRequirements" | "onsiteRequirement" | "timelineRequirement" | "cloudPlatformPreference" | "matchedCapabilityTags" | "unmatchedCapabilitySignals" | "recommendedPartnerNames" | "missingFields" | "followUpQuestions";
export type Opportunity = Record<OpportunityField, string | null> & {
  id: string; matchRecordId: string | null; requirementText: string;
  supplyStatus: string | null; completenessScore: number;
  classification_pending?: Record<string, string[]>;
};

export function OpportunityFilter({kind, value, onChange, compact = false}: {kind: "industry" | "region"; value: string; onChange: (value: string) => void; compact?: boolean}) {
  const label = kind === "industry" ? "行业" : "区域";
  const selected = standardValues(value, kind);
  const groups = kind === "industry" ? [{name: "行业", values: INDUSTRIES}] : [{name: "国内", values: REGION_TYPES.domestic}, {name: "海外", values: REGION_TYPES.overseas}];
  return <MultiSelectFilter label={label} selected={selected} groups={groups} onChange={values => onChange(values.join(","))} compact={compact}/>;
}

export function MultiSelectFilter({label, selected, groups, onChange, searchable = false, compact = false}: {
  label: string; selected: string[]; groups: {name: string; values: string[]}[];
  onChange: (values: string[]) => void; searchable?: boolean; compact?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionsId = useId();
  useEffect(() => {
    if (!open) return;
    const dismissOutside = (event: Event) => {
      if (!filterRef.current?.contains(event.target as Node)) setOpen(false);
    };
    // A label click briefly blurs the trigger before focusing its checkbox.
    // Close on an actual outside interaction, not that intermediate blur.
    document.addEventListener("pointerdown", dismissOutside, true);
    document.addEventListener("focusin", dismissOutside, true);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside, true);
      document.removeEventListener("focusin", dismissOutside, true);
    };
  }, [open]);
  const visibleGroups = groups.map(group => ({...group, values: group.values.filter(item => item.toLowerCase().includes(query.trim().toLowerCase()))}));
  // Keep the popup outside a native details/summary subtree: changing its checked
  // descendants can crash Edge 154 with Windows native accessibility enabled.
  return <div className={`${styles.field} ${compact ? styles.compactFilter : ""}`}>{!compact && <span>{label}</span>}
    <div ref={filterRef} className={styles.filter} data-filter-popover="" onKeyDown={event => {if (event.key === "Escape") {setOpen(false); triggerRef.current?.focus();}}}>
      <button type="button" ref={triggerRef} className={styles.filterTrigger} aria-label={`${label}筛选`} aria-expanded={open} aria-controls={optionsId} onClick={() => setOpen(value => !value)}>
        {compact ? <span className={styles.triggerLabel}>{label}{selected.length > 0 && <span className={styles.selectionCount} aria-label={`已选 ${selected.length} 项`}>{selected.length}</span>}</span> : <span>{selected.length ? `已选 ${selected.length} 项` : `全部${label}`}</span>}
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg>
      </button>
      {open && <div id={optionsId} className={styles.popover} role="group" aria-label={`${label}选项`}>
        <div className={styles.filterHeader}><span>可多选</span><button type="button" className={compact ? styles.filterClear : "text-btn"} onClick={() => onChange([])}>清除</button></div>
        {searchable && <input className={styles.filterSearch} aria-label={`搜索${label}选项`} placeholder={`搜索${label}`} value={query} onChange={event => setQuery(event.target.value)}/>}
        <div className={compact ? styles.filterOptions : undefined}>
          {visibleGroups.filter(group => group.values.length).map(group => <fieldset key={group.name}><legend className={compact && groups.length === 1 ? "sr-only" : undefined}>{group.name}</legend>{group.values.map(item => <label key={item}><input type="checkbox" checked={selected.includes(item)} onChange={event => onChange(event.target.checked ? [...selected, item] : selected.filter(value => value !== item))}/>{item}</label>)}</fieldset>)}
          {!visibleGroups.some(group => group.values.length) && <p className="muted">{query.trim() ? "没有匹配的选项" : "暂无可选标签"}</p>}
        </div>
      </div>}
    </div>
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
