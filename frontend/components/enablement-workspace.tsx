"use client";
import {useAgent} from "./agent-settings";
import {ClassificationNotice} from "@/components/business-taxonomy";


import Link from "next/link";
import { CardEntry, CardEntryLabel } from "./card-entry";
import { MaterialFiles } from "./material-files";
import contract from "../../shared/partner-materials.json";
import { Pagination } from "./pagination";
import {UiIcon} from "./ui-icons";
import {DevelopmentRequestForm,type DevelopmentDraftProps} from "./development-assistant";
import {PartnerSelect} from "./partner-select";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "./auth-provider";

type Resource = {
  source_type: string; source_id: string; source_version: number; title: string; summary: string;
  audience?:string;duration_minutes?:number|null;category?:string;subcategory?:string;
  role_ids?:string[];zone_ids?:string[];roles?:Category[];zones?:Category[];level?:string|null;course_goals?:string;outline?:string;cover_url?:string;lab_goals?:string;lab_requirements?:string;
  source_url: string; capabilities: {id: string; name: string}[]; status: string; availability: string;
  contributor_name?:string;contributor_id?:string;

};
type Context = { partner: { classification_pending?: Record<string,string[]>; id: string; name: string; intro: string | null; capabilities: string | null; industries: string | null; service_areas: string | null; ai_profile: string | null } | null;
  evidence: {source_type: string; source_id: string; title: string}[];
  project: {task_id: string; requirement: string; risk_notes: string; risk_status: string} | null; shared_case: Resource | null; };
const typeLabels: Record<string,string> = {course:"课程",lab:"实验",case:"案例"};
const values: Record<string,string> = {unknown:"未知",beginner:"入门",intermediate:"进阶",advanced:"高级",free:"免费",paid:"付费"};
const display = (value?: string | number | null) => value === null || value === undefined || value === "" ? "未知" : values[String(value)] || String(value);
const resourcePath = (r: Resource) => `/resources/${r.source_type}/${encodeURIComponent(r.source_id)}${r.source_type==='case'?'':`?source_version=${r.source_version}`}`;

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
export function DevelopmentEntry(draft:DevelopmentDraftProps) {
  const agent=useAgent("partner_development");
  const search=useSearchParams();
  const contextParams=new URLSearchParams();
  for(const key of ["partner_id","task_id","case_id","case_version"]) {const value=search.get(key);if(value)contextParams.set(key,value);}
  const context=useAuthorizedData<Context>(`/enablement/context?${contextParams}`);
  const partners=useAuthorizedData<{id:string;name:string}[]>("/partners");
  function selectPartner(id:string){const next=new URLSearchParams(search);next.set("mode","development");if(id)next.set("partner_id",id);else next.delete("partner_id");if(id!==(search.get("partner_id")||"")||!id){for(const key of ["task_id","case_id","case_version"])next.delete(key);}window.history.replaceState(null,"",`/?${next}`);}
  const partner=context.data?.partner,project=context.data?.project,shared=context.data?.shared_case;
  return <div className="development-entry">
    <p className="assistant-subtitle">{agent.description}</p>{!agent.enabled&&<p className="notice-neutral" role="status">该智能体已停用，历史任务仍可查看。</p>}
    <div className="development-composer"><div className={`development-context-row${project||shared?" has-source":""}`} >
    <section className="card development-partner"><div className="enablement-field"><span>关联已有伙伴资料（可选）</span><PartnerSelect label="关联已有伙伴资料（可选）" placeholder="不关联已有伙伴资料" partners={partners.data||[]} value={search.get("partner_id")||""} onChange={selectPartner}/></div>{partners.error&&<ReadError message={partners.error} retry={partners.retry}/>}
    {(search.get("task_id")||search.get("case_id"))&&<p className="muted">已关联来源资料；更换或清除关联会移除来源，保留输入。</p>}
    {context.error?<ReadError message={context.error} retry={context.retry}/>:!context.data?<p role="status">正在核验来源上下文…</p>:partner&&<details className="development-profile"><summary>当前伙伴画像摘要</summary><div className="development-profile-heading"><CardEntry href={`/partners/${encodeURIComponent(partner.id)}`}>查看伙伴资料</CardEntry></div><dl className="development-profile-facts">{[["正式能力",partner.capabilities],["行业经验",partner.industries],["服务区域",partner.service_areas]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value||"暂无已维护信息"}</dd></div>)}</dl><ClassificationNotice pending={partner.classification_pending}/><p className="profile-preview">{partner.ai_profile||partner.intro||"当前画像依据有限，可继续描述发展方向。"}</p><details className="development-profile-evidence"><summary>查看获准引用的依据</summary><h3>当前可访问的证据引用</h3>{context.data.evidence.length?<ul>{context.data.evidence.map(e=><li key={e.source_type+e.source_id}>{e.title}</li>)}</ul>:<p className="muted">暂无可引用证据。</p>}<p className="muted">内部资料可见不代表获准发送模型或对伙伴外发。</p></details></details>}
    </section>
    {(project||shared)&&<section className="card development-source" data-testid="source-context"><h2>来源上下文</h2>{project&&<><Link href={`/tasks/${encodeURIComponent(project.task_id)}`}>返回来源项目任务</Link><h3>项目需求</h3><p className="enablement-prose">{project.requirement}</p><h3>原匹配风险 / 缺口</h3><span className="enablement-badge">{project.risk_status}</span><p className="enablement-prose">{project.risk_notes||"原匹配未提供风险信息"}</p><p className="muted">这是原匹配提示，尚未确认能力短板，也未转化为培训需求。</p></>}{shared&&<><Link href={resourcePath(shared)}>{shared.title}</Link><p>{shared.summary}</p><p className="muted">贡献伙伴：{shared.contributor_name}</p></>}</section>}
    </div>
    <DevelopmentRequestForm {...draft} partnerId={search.get("partner_id")} sourceTask={search.get("task_id")} sourceCase={search.get("case_id")} sourceVersion={search.get("case_version")?Number(search.get("case_version")):null}/>
    </div>
  </div>;
}

type Category = {id:string;name:string};
type Filters = {roles?:Category[];zones?:Category[]};
function CaseCatalog(){
  const [q,setQ]=useState(''),[query,setQuery]=useState(''),[group,setGroup]=useState(''),[category,setCategory]=useState(''),[page,setPage]=useState(1);
  const selected=contract.categories.find(c=>c.id===group);
  const params=new URLSearchParams({source_type:'case',q:query,category_id:category,page:String(page),page_size:'12'});
  if(group&&!category)params.set('category_group',group);
  const result=useAuthorizedData<{items:Resource[];total:number}>(`/enablement/resources?${params}`);
  return <section aria-label="案例资源"><form className="card resource-filters" onSubmit={e=>{e.preventDefault();setQuery(q);setPage(1);}}><div className="enablement-search"><label className="enablement-field">搜索案例<input maxLength={200} value={q} onChange={e=>setQ(e.target.value)} placeholder="案例名称或简介"/></label><button>搜索</button></div><div className="enablement-filter-grid"><label className="enablement-field">一级分类<select aria-label="一级分类" value={group} onChange={e=>{setGroup(e.target.value);setCategory('');setPage(1);}}><option value="">全部</option>{contract.categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label className="enablement-field">二级分类<select aria-label="二级分类" value={category} onChange={e=>{setCategory(e.target.value);setPage(1);}}><option value="">全部</option>{(selected?selected.children:contract.categories.flatMap(c=>c.children)).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></div></form>
    {result.error?<ReadError message={result.error} retry={result.retry}/>:!result.data?<p role="status">正在读取案例…</p>:<><p className="muted">共 {result.data.total} 条案例</p><div className="enablement-resource-grid">{result.data.items.map(r=><article className="card enablement-resource-card" key={r.source_id}><span className="enablement-badge">{r.category} / {r.subcategory}</span><h2><Link href={resourcePath(r)}>{r.title}</Link></h2><p>{r.summary}</p><div className="enablement-actions"><span className="muted">{r.contributor_name}</span><CardEntry href={resourcePath(r)} /></div></article>)}</div>{!result.data.total&&<p className="placeholder-text">暂无符合条件的案例。</p>}<Pagination label="案例分页" page={page} total={result.data.total} pageSize={12} onPageChange={setPage}/></>}
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
  if(r&&r.source_type!=="case")return <div className="page enablement-page learning-detail"><Link href={`/resources?resource_type=${r.source_type}`}>返回资源中心</Link>
    <header className="learning-detail-heading"><h1>{r.title}</h1><p className="lead">{r.summary}</p><ResourceLabels resource={r}/><div className="learning-meta"><span>{levelName(r.level)}</span>{r.source_type==='lab'&&<span>{duration(r.duration_minutes)}</span>}</div></header>
    {r.source_type==='course'&&r.cover_url&&<img className="learning-cover" src={r.cover_url} alt="" referrerPolicy="no-referrer" loading="lazy"/>}
    <section className="card learning-content">{(r.source_type==='course'?[['课程目标',r.course_goals],['目标学员',r.audience],['课程大纲',r.outline]]:[['实验目标',r.lab_goals],['基本要求',r.lab_requirements]]).map(([label,value])=><section key={label}><h2>{label}</h2><p className="enablement-prose">{value||'暂未填写'}</p></section>)}
      <div className="learning-cta"><button disabled={jumping} onClick={()=>void redirect()}>{jumping?'正在跳转…':r.source_type==='course'?'前往课程':'前往实验'}</button></div>
    </section>{event&&<p role="status">{event}</p>}
  </div>;
  return <div className="page enablement-page"><Link href="/resources?resource_type=case">返回资源中心</Link>{resource.error?<ReadError message={resource.error} retry={resource.retry}/>:!r?<p role="status">正在读取案例…</p>:<><header className="learning-detail-heading"><span className="enablement-badge">{r.category} / {r.subcategory}</span><h1>{r.title}</h1><p className="lead">{r.summary}</p><Link href={`/partners/${r.contributor_id}`}>{r.contributor_name}</Link></header><section className="card"><h2>案例文件</h2><MaterialFiles endpoint={`/cases/${r.source_id}/deliverables`}/></section><Link className="secondary-btn" href={`/?mode=development&partner_id=${encodeURIComponent(r.contributor_id||'')}&case_id=${encodeURIComponent(r.source_id)}`}>围绕此案例制定发展建议</Link></>}</div>;

}

export function PartnerSharedCases({partnerId}:{partnerId:string}) {
  const result=useAuthorizedData<{items:Resource[]}>(`/enablement/resources?source_type=case&contributor_id=${encodeURIComponent(partnerId)}`);
  return <section className="card"><h2>伙伴案例</h2>{result.error?<ReadError message={result.error} retry={result.retry}/>:result.data?.items.length?<div className="case-stack">{result.data.items.map(r=><article className="case-item" key={r.source_id}><h3><Link href={resourcePath(r)}>{r.title}</Link></h3><p>{r.summary}</p><div className="card-entry-row"><CardEntry href={resourcePath(r)} /></div></article>)}</div>:<p className="placeholder-text">暂无可展示的伙伴案例。</p>}</section>;
}

const levelName=(level?:string|null)=>level==='basic'?'基础':level==='advanced'?'进阶':'层级待补充';
const duration=(minutes?:number|null)=>minutes?`${minutes} 分钟`:'时长待补充';
function ResourceLabels({resource}:{resource:Resource}) {
  return <div className="enablement-tags learning-labels">{[...(resource.roles||[]),...(resource.zones||[])].map(c=><span key={c.id}>{c.name}</span>)}</div>;
}

export function ResourceCatalog() {
  const search=useSearchParams(),router=useRouter();
  const source=['course','lab','case'].includes(search.get('resource_type')||'')?search.get('resource_type')!:'course';
  function tab(type:string){const next=new URLSearchParams(search);next.delete('tab');next.set('resource_type',type);router.replace(`/resources?${next}`,{scroll:false});}
  return <section aria-label="资源中心"><div className="enablement-tabs" role="tablist" aria-label="资源类型">{Object.entries(typeLabels).map(([key,label])=><button role="tab" aria-selected={source===key} className={source===key?'active':''} key={key} onClick={()=>tab(key)}>{label}</button>)}</div>
    {source==='case'?<CaseCatalog/>:<LearningCatalog key={source} source={source}/>}
  </section>;
}
function LearningCatalog({source}:{source:string}) {
  const [axis,setAxis]=useState<'roles'|'zones'>('roles'),[category,setCategory]=useState(''),[level,setLevel]=useState('');
  const [query,setQuery]=useState(''),[applied,setApplied]=useState(''),[page,setPage]=useState(1);
  const options=useAuthorizedData<Filters>('/enablement/resource-filters');
  const params=new URLSearchParams({source_type:source,page:String(page),page_size:'12'});
  if(category)params.set(axis==='roles'?'role_id':'zone_id',category);
  if(level)params.set('level',level);if(applied)params.set('q',applied);
  const result=useAuthorizedData<{items:Resource[];total:number}>(`/enablement/resources?${params}`);
  return <>
    <section className="card learning-filters">
      <div className="learning-toolbar"><div className="learning-axis" role="group" aria-label="浏览方式">{([['roles','按岗位'],['zones','按专区']] as const).map(([value,label])=><button className={axis===value?'active':''} key={value} aria-pressed={axis===value} onClick={()=>{setAxis(value);setCategory('');setPage(1);}}>{label}</button>)}</div>
      <form className="learning-search" onSubmit={e=>{e.preventDefault();setApplied(query.trim());setPage(1);}}><input aria-label="搜索课程或实验" placeholder="搜索名称或简介" maxLength={200} value={query} onChange={e=>setQuery(e.target.value)}/><button type="submit" className="secondary-btn">搜索</button></form></div>
      {options.error?<ReadError message={options.error} retry={options.retry}/>:<div className="learning-categories" role="group" aria-label={axis==='roles'?'岗位分类':'专区分类'}><button aria-pressed={!category} className={!category?'active':''} onClick={()=>{setCategory('');setPage(1);}}>全部{axis==='roles'?'岗位':'专区'}</button>{(options.data?.[axis]||[]).map(c=><button key={c.id} aria-pressed={category===c.id} className={category===c.id?'active':''} onClick={()=>{setCategory(c.id);setPage(1);}}>{c.name}</button>)}</div>}
      <div className="learning-levels" role="group" aria-label="资源层级">{[['','全部'],['basic','基础'],['advanced','进阶']].map(([value,label])=><button key={value} className={level===value?'active':''} aria-pressed={level===value} onClick={()=>{setLevel(value);setPage(1);}}>{label}</button>)}</div>
    </section>
    {result.error?<ReadError message={result.error} retry={result.retry}/>:!result.data?<p role="status">正在读取资源…</p>:<><p className="muted" role="status">共 {result.data.total} 条资源</p><div className="enablement-resource-grid learning-grid">{result.data.items.map(r=><article className="card learning-card" key={r.source_id}><div className="resource-card-kicker"><UiIcon name={source==='lab'?'settings':'file'} size={18}/><span>{typeLabels[source]}</span></div><h2><Link href={resourcePath(r)}>{r.title}</Link></h2><p>{r.summary}</p><ResourceLabels resource={r}/><div className="learning-meta"><span className="learning-level">{levelName(r.level)}</span>{r.source_type==='lab'&&<span>{duration(r.duration_minutes)}</span>}<CardEntryLabel /></div></article>)}</div>{!result.data.items.length&&<div className="card empty-state"><h2>暂无符合条件的资源</h2><p>试试其他分类或搜索词。</p></div>}
    <Pagination label="资源分页" page={page} total={result.data.total} pageSize={12} onPageChange={setPage}/></>}
  </>;
}
