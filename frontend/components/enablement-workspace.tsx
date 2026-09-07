"use client";

import Link from "next/link";
import {DevelopmentRequestForm} from "./development-assistant";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "./auth-provider";

type Resource = {
  source_type: string; source_id: string; source_version: number; title: string; summary: string;
  target_capability?: string; audience?: string; product_direction?: string; difficulty?: string;
  language?: string; site?: string; prerequisites?: string; duration_minutes?: number | null;
  cost?: string; account_requirement?: string; environment_requirement?: string; source_platform: string;
  source_url: string; capabilities: {id: string; name: string}[]; status: string; availability: string;
  review: { reviewer_name: string; reviewed_at: string; link_status: string; content_checked: number; authorization_checked: number } | null;
  contributor_name?: string; contributor_id?: string; contributor_role?: string; methods?: string;
};
type Context = { partner: { id: string; name: string; intro: string | null; capabilities: string | null; industries: string | null; service_areas: string | null; ai_profile: string | null } | null;
  evidence: {source_type: string; source_id: string; title: string}[];
  project: {task_id: string; requirement: string; risk_notes: string; risk_status: string} | null; shared_case: Resource | null; };
const typeLabels: Record<string,string> = {course:"课程",lab:"实验",case:"案例"};
const values: Record<string,string> = {unknown:"未知",beginner:"入门",intermediate:"进阶",advanced:"高级",free:"免费",paid:"付费"};
const display = (value?: string | number | null) => value === null || value === undefined || value === "" ? "未知" : values[String(value)] || String(value);
const resourcePath = (r: Resource) => `/resources/${r.source_type}/${encodeURIComponent(r.source_id)}?source_version=${r.source_version}`;

/** Reauthorize on focus and periodically. Never retain another URL's data or failed reads. */
function useAuthorizedData<T>(url: string | null) {
  const [state,setState] = useState<{url:string|null;data:T|null;error:string}>({url:null,data:null,error:""});
  const [revision,setRevision] = useState(0);
  useEffect(() => {
    if (!url) return;
    let active=true; let busy=false;
    const controller=new AbortController();
    async function load() {
      if (busy) return; busy=true;
      try {
        const response=await apiFetch(url!,{cache:"no-store",signal:controller.signal});
        if(!response.ok) throw new Error(response.status===404 ? "内容不存在、授权已变化或当前不可用，请重新选择。" : "暂时无法读取内容，请稍后重试。");
        const data=await response.json() as T;
        if(active) setState({url,data,error:""});
      } catch(error) { if(active) setState({url,data:null,error:error instanceof Error ? error.message : "读取失败"}); }
      finally {busy=false;}
    }
    void load();
    const focus=()=>{if(!document.hidden) void load();};
    const timer=setInterval(focus,15000);
    window.addEventListener("focus",focus);document.addEventListener("visibilitychange",focus);
    return ()=>{active=false;controller.abort();clearInterval(timer);window.removeEventListener("focus",focus);document.removeEventListener("visibilitychange",focus);};
  },[url,revision]);
  return {data:state.url===url ? state.data : null,error:state.url===url ? state.error : "",clear:()=>{setState({url,data:null,error:"内容已不可用，请重新选择或刷新。"});setRevision(v=>v+1);},retry:()=>setRevision(v=>v+1)};
}

function ReadError({message,retry}:{message:string;retry:()=>void}) {
  return <div className="notice-neutral" role="alert">{message} <button className="secondary-btn" onClick={retry}>重新读取</button></div>;
}

/** Shared new-task mode; all context still comes from the authorized backend API. */
export function DevelopmentEntry() {
  const search=useSearchParams(),router=useRouter();
  const contextParams=new URLSearchParams();
  for(const key of ["partner_id","task_id","case_id","case_version"]) {const value=search.get(key);if(value)contextParams.set(key,value);}
  const context=useAuthorizedData<Context>(`/enablement/context?${contextParams}`);
  const partners=useAuthorizedData<{id:string;name:string}[]>("/partners");
  function selectPartner(id:string){const next=new URLSearchParams(search);next.set("mode","development");if(id)next.set("partner_id",id);else next.delete("partner_id");router.replace(`/?${next}`,{scroll:false});}
  const partner=context.data?.partner,project=context.data?.project,shared=context.data?.shared_case;
  return <div className="development-entry">
    <p className="assistant-subtitle">选择伙伴，说说你希望发展的方向</p>
    <section className="card development-partner"><label className="enablement-field">目标伙伴<select aria-label="选择目标伙伴" value={search.get("partner_id")||""} disabled={!!search.get("task_id")} onChange={e=>selectPartner(e.target.value)}><option value="">请选择伙伴</option>{partners.data?.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>{partners.error&&<ReadError message={partners.error} retry={partners.retry}/>}
    {search.get("task_id")&&<p className="muted">目标伙伴来自所选匹配结果。切换伙伴请返回匹配结果选择。</p>}
    {context.error?<ReadError message={context.error} retry={context.retry}/>:!context.data?<p role="status">正在核验来源上下文…</p>:partner&&<div className="development-profile"><h2>当前伙伴画像摘要</h2><p>{[partner.capabilities,partner.industries,partner.service_areas].filter(Boolean).join(" · ")||"暂无已维护的能力与行业摘要"}</p><p className="profile-preview">{partner.ai_profile||partner.intro||"当前画像依据有限，可继续描述发展方向。"}</p><Link href={`/partners/${encodeURIComponent(partner.id)}`}>查看完整伙伴画像</Link><details><summary>查看获准引用的依据</summary><h3>当前可访问的证据引用</h3>{context.data.evidence.length?<ul>{context.data.evidence.map(e=><li key={e.source_type+e.source_id}>{e.title}</li>)}</ul>:<p className="muted">暂无可引用证据。</p>}<p className="muted">内部资料可见不代表获准发送模型或对伙伴外发。</p></details></div>}
    </section>
    {(project||shared)&&<section className="card development-source" data-testid="source-context"><h2>来源上下文</h2>{project&&<><Link href={`/tasks/${encodeURIComponent(project.task_id)}`}>返回来源项目任务</Link><h3>项目需求</h3><p className="enablement-prose">{project.requirement}</p><h3>原匹配风险 / 缺口</h3><span className="enablement-badge">{project.risk_status}</span><p className="enablement-prose">{project.risk_notes||"原匹配未提供风险信息"}</p><p className="muted">这是原匹配提示，尚未确认能力短板，也未转化为培训需求。</p></>}{shared&&<><Link href={resourcePath(shared)}>{shared.title}</Link><p>{shared.summary}</p><p className="muted">贡献伙伴：{shared.contributor_name} · {shared.contributor_role}</p></>}</section>}
    <DevelopmentRequestForm partnerId={search.get("partner_id")||""} sourceTask={search.get("task_id")} sourceCase={search.get("case_id")} sourceVersion={search.get("case_version")?Number(search.get("case_version")):null}/>
  </div>;
}

const filterFields: [string,string][] = [["audience","岗位 / 适用对象"],["product_direction","产品 / 技术方向"],["difficulty","难度"],["language","语言"],["site","站点"],["cost","费用"],["account_requirement","账号条件"],["environment_requirement","环境条件"],["prerequisites","先修条件"]];
type Filters = {capabilities:{id:string;name:string}[]} & Record<string,unknown>;
export function ResourceCatalog() {
  const search=useSearchParams();const router=useRouter();
  const source=["course","lab","case"].includes(search.get("resource_type")||"") ? search.get("resource_type")! : "course";
  const [query,setQuery]=useState("");const [filters,setFilters]=useState<Record<string,string>>({});const [applied,setApplied]=useState<Record<string,string>>({});const [page,setPage]=useState(1);
  const options=useAuthorizedData<Filters>("/enablement/resource-filters");
  const request=new URLSearchParams({source_type:source,page:String(page),page_size:"12",...applied});
  const result=useAuthorizedData<{items:Resource[];total:number}>(`/enablement/resources?${request}`);
  function tab(type:string){const next=new URLSearchParams(search);next.delete("tab");next.set("resource_type",type);setPage(1);router.replace(`/resources?${next}`,{scroll:false});}
  return <section aria-label="资源中心">
    <div className="enablement-tabs" role="tablist" aria-label="资源类型">{Object.entries(typeLabels).map(([key,label])=><button role="tab" aria-selected={source===key} className={source===key?"active":""} key={key} onClick={()=>tab(key)}>{label}</button>)}</div>
    <form className="card" onSubmit={e=>{e.preventDefault();setApplied({q:query,...filters});setPage(1);}}>
      <div className="enablement-search"><label className="enablement-field">资源名称<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索资源名称" maxLength={200}/></label><button type="submit">搜索资源</button><button type="button" className="secondary-btn" onClick={()=>{setQuery("");setFilters({});setApplied({});setPage(1);}}>重置筛选</button></div>
      <div className="enablement-filter-grid"><label className="enablement-field">能力<select aria-label="能力" value={filters.capability_tag_id||""} onChange={e=>setFilters({...filters,capability_tag_id:e.target.value})}><option value="">全部能力</option>{options.data?.capabilities.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      {filterFields.map(([key,label])=><label className="enablement-field" key={key}>{label}<select aria-label={label} value={filters[key]||""} onChange={e=>setFilters({...filters,[key]:e.target.value})}><option value="">全部</option>{((options.data?.[key]||[]) as string[]).map(v=><option key={v} value={v}>{display(v)}</option>)}</select></label>)}
      <label className="enablement-field">发布状态<select aria-label="发布状态" value={filters.status||"published"} onChange={e=>setFilters({...filters,status:e.target.value})}><option value="published">已发布</option><option value="unpublished">已下架</option></select></label></div>
      <p className="muted">仅展示当前已发布且获准在系统内查看的版本。已下架、撤权内容不可查看。</p>
    </form>
    {result.error ? <ReadError message={result.error} retry={result.retry}/> : !result.data ? <p role="status">正在读取资源…</p> : <><p className="muted" role="status">共 {result.data.total} 条资源</p><div className="enablement-resource-grid">{result.data.items.map(r=><article className="card enablement-resource-card" key={r.source_type+r.source_id}><div><span className="enablement-badge">{typeLabels[r.source_type]} · 已发布</span><h2><Link href={resourcePath(r)}>{r.title}</Link></h2><p>{r.summary}</p></div><div className="enablement-tags">{r.capabilities.map(c=><span key={c.id}>{c.name}</span>)}</div><p className="muted">{r.source_platform} · {display(r.difficulty)} · {display(r.language)}</p><div className="enablement-actions"><span className="muted">人工核验{r.review?"已记录":"未知"}</span><Link href={resourcePath(r)}>查看详情</Link></div></article>)}</div>{result.data.items.length===0&&<div className="card empty-state"><h2>暂无符合条件的资源</h2><p>可调整筛选，或等待管理员核验并发布资源。</p></div>}
    <div className="enablement-actions"><button className="secondary-btn" disabled={page===1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>第 {page} 页</span><button className="secondary-btn" disabled={page*12>=result.data.total} onClick={()=>setPage(p=>p+1)}>下一页</button></div></>}
  </section>;
}

export function ResourceDetail({type,id}:{type:string;id:string}) {
  const search=useSearchParams();const version=search.get("source_version");
  const resource=useAuthorizedData<Resource>(`/enablement/resources/${encodeURIComponent(type)}/${encodeURIComponent(id)}${version?`?source_version=${encodeURIComponent(version)}`:""}`);
  const [jumping,setJumping]=useState(false);const [event,setEvent]=useState("");
  async function redirect(){
    if(!resource.data||jumping)return;
    const popup=window.open("about:blank","_blank");if(popup)popup.opener=null;
    setJumping(true);setEvent("");
    try {
      const response=await apiFetch(`/enablement/resources/${encodeURIComponent(type)}/${encodeURIComponent(id)}/redirect`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({source_version:resource.data.source_version})});
      if(!response.ok)throw new Error("资源授权或版本已变化，请重新选择。");
      const result=await response.json();
      if(popup)popup.location.replace(result.url);else {setEvent("已记录发起跳转；浏览器拦截了新窗口，请允许弹窗后重试。");return;}
      setEvent("已记录发起跳转；外部平台是否打开或完成学习不在此记录范围内。");
    } catch {popup?.close();resource.clear();setEvent("无法发起跳转，请重新核验资源。");}finally{setJumping(false);}
  }
  const r=resource.data;
  return <div className="page enablement-page"><Link href={`/resources?resource_type=${encodeURIComponent(type)}`}>返回资源中心</Link>{resource.error?<ReadError message={resource.error} retry={resource.retry}/>:!r?<p role="status">正在核验资源…</p>:<>
    <div className="page-heading-row"><div><p className="eyebrow">{typeLabels[r.source_type]}资源</p><h1>{r.title}</h1><p className="lead">{r.summary}</p></div><span className="enablement-badge">已发布 · {r.availability==="available"?"人工核验可用":"可用性未知"}</span></div>
    <section className="card"><h2>资源信息</h2><div className="enablement-tags">{r.capabilities.map(c=><span key={c.id}>{c.name}</span>)}</div><dl className="enablement-facts">
    {[["适用对象",r.audience],["目标能力 / 用途",r.target_capability||r.methods],["产品 / 技术方向",r.product_direction],["难度",r.difficulty],["语言 / 站点",`${display(r.language)} / ${display(r.site)}`],["先修条件",r.prerequisites],["预计投入",r.duration_minutes?`${r.duration_minutes} 分钟`:null],["费用",r.cost],["账号条件",r.account_requirement],["环境条件",r.environment_requirement]].map(([label,value])=><div className="enablement-fact" key={label}><dt>{label}</dt><dd>{display(value)}</dd></div>)}
    </dl>{r.source_type==="case"&&<div className="notice-neutral"><h3>贡献伙伴及实际角色</h3><Link href={`/partners/${encodeURIComponent(r.contributor_id||"")}`}>{r.contributor_name}</Link><p>{r.contributor_role}</p><Link href={`/?mode=development&case_id=${encodeURIComponent(r.source_id)}&case_version=${r.source_version}`}>围绕此案例制定发展建议</Link><p className="muted">带入共享实践上下文，结合伙伴画像生成发展建议。</p></div>}</section>
    <section className="card"><h2>来源与人工核验</h2><dl className="enablement-facts"><dt>来源平台</dt><dd>{r.source_platform}</dd><dt>外部来源</dt><dd className="enablement-url">{r.source_url}</dd><dt>共享 / 资源版本</dt><dd>{r.source_version}</dd><dt>发布核验时间</dt><dd>{r.review?new Date(r.review.reviewed_at).toLocaleString("zh-CN"):"未知"}</dd><dt>核验人</dt><dd>{display(r.review?.reviewer_name)}</dd><dt>核验内容</dt><dd>{r.review?.content_checked&&r.review.authorization_checked?"内容、能力映射及用途授权已人工核验":"未知"}</dd></dl><p className="muted">可用状态来自人工核验，外部平台当前响应及访问权限仍以源站为准。</p><button disabled={jumping} onClick={()=>void redirect()}>{jumping?"正在发起跳转…":"发起跳转"}</button></section>
    </>}{event&&<p role="status">{event}</p>}</div>;
}

export function PartnerSharedCases({partnerId}:{partnerId:string}) {
  const result=useAuthorizedData<{items:Resource[]}>(`/enablement/resources?source_type=case&contributor_id=${encodeURIComponent(partnerId)}`);
  return <section className="card"><h2>共享学习案例</h2>{result.error?<ReadError message={result.error} retry={result.retry}/>:result.data?.items.length?<div className="case-stack">{result.data.items.map(r=><article className="case-item" key={r.source_id}><h3><Link href={resourcePath(r)}>{r.title}</Link></h3><p>{r.summary}</p></article>)}</div>:<p className="placeholder-text">暂无当前可查看的已发布共享学习案例。</p>}</section>;
}
