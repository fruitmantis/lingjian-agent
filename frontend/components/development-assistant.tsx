"use client";
import {TaskProgress,type TaskProgressData} from "./task-progress";
import {AdvisorAnswer} from "./advisor-answer";
import {FailureNotice,failureMessage,actionFailure,uncertainResult,serviceFailure,type FailureDetail} from "./task-failure";
import Link from "next/link";
import { CardEntry } from "./card-entry";
import {UiIcon} from "./ui-icons";
import {PlanStatus,type PlanPresentation} from "./plan-status";
import {useEffect,useState,useRef,type RefObject} from "react";
import {useRouter,usePathname} from "next/navigation";
import {apiFetch,useAuth} from "./auth-provider";
import {ApiResponseError,responseError,submissionIsUncertain} from "../lib/api-request";
import {TaskRequest,TaskResult,TaskArrivalReadError} from "./task-transition";
import {tasksChanged,newTaskId,useTaskNavigation} from "./task-navigation";
import {copyText} from "../lib/copy-text";

type Item={item_id?:string;source_type:string;source_id:string;source_version:number;capability_tag_id:string;focus?:string;reason:string;estimated_hours:number;note:string;title?:string;prerequisites?:string;availability?:string;conditions?:{duration_minutes?:number;level?:string;roles?:{id:string;name:string}[];zones?:{id:string;name:string}[];lab_requirements?:string;cost?:string;account_requirement?:string;environment_requirement?:string;language?:string;site?:string}};
type Stage={title:string;items:Item[]};
type Analysis={intent:string;interpretation:string;partner_assessment?:string;reusable_basis:string[];priorities:{name:string;reason:string;reusable_basis?:string[]}[];basis_limitations:string[]};
type Payload={analysis?:Analysis;answer?:string;next_steps?:string[];overview:{development_direction?:string;development_goal?:string};stages:Stage[];limitations:string[];resource_gaps:string[]};
type Detail={progress?:TaskProgressData|null;analysis?:Analysis|null;scopeMessage?:string|null;executionInput?:string|null;failureDetails?:FailureDetail[];presentation:PlanPresentation;plan:{id:string;current_version_id:string|null;status:string;active_run_id:string|null};partner_name:string|null;request:{development_direction?:string;development_goal?:string;raw_demand?:string};conversation:{submission_id:string;message:string;answer:string;resources?:Item[]}[];payload:Payload|null;hidden:boolean;notice:string|null;versions:{id:string;version_no:number}[];runs:{id:string;submission_id:string;run_type:string;status:string;created_at:string;safe_error_message:string|null}[]};
const names:Record<string,string>={course:"课程",lab:"实验",case:"共享案例",unknown:"未知",free:"免费",paid:"付费",pending:"等待处理",running:"正在处理",ready:"已完成",failed:"失败",partial:"部分完成",interrupted:"已中断"};
const display=(v?:string|number)=>names[String(v)]||v||"未知";
function ResourceAdvice({item:i,position}:{item:Item;position?:number}){
 const duration=Number(i.conditions?.duration_minutes);
 return <article className="advisor-resource" data-testid="resource-advice"><div className="advisor-resource-title"><UiIcon name={i.source_type==="lab"?"settings":i.source_type==="case"?"users":"file"} size={18}/><span className="advisor-resource-type">{names[i.source_type]}</span><h4>{position?`${position}. `:""}{i.title}</h4></div><p>{i.reason}</p><dl className="advisor-conditions">{i.source_type!=="course"&&<div><dt>时长</dt><dd>{Number.isFinite(duration)&&duration>0?`${duration/60} 小时`:"未知"}</dd></div>}{i.source_type==="case"?<><div><dt>费用</dt><dd>{display(i.conditions?.cost)}</dd></div><div><dt>账号</dt><dd>{display(i.conditions?.account_requirement)}</dd></div><div><dt>环境</dt><dd>{display(i.conditions?.environment_requirement)}</dd></div><div><dt>语言 / 站点</dt><dd>{display(i.conditions?.language)} / {display(i.conditions?.site)}</dd></div><div><dt>先修</dt><dd>{i.prerequisites||"未知"}</dd></div></>:<><div><dt>层级</dt><dd>{i.conditions?.level==='basic'?'基础':i.conditions?.level==='advanced'?'进阶':'待补充'}</dd></div>{!![...(i.conditions?.roles||[]),...(i.conditions?.zones||[])].length&&<div><dt>分类</dt><dd>{[...(i.conditions?.roles||[]),...(i.conditions?.zones||[])].map(c=>c.name).join(' · ')}</dd></div>}</>}</dl>{i.availability==="available"?<CardEntry href={`/resources/${i.source_type}/${i.source_id}?source_version=${i.source_version}`}>{i.source_type==="case"?"查看来源与发起跳转":"查看资源"}</CardEntry>:<p className="muted">当前资源不可用，历史引用保留。</p>}</article>;
}
async function request<T>(url:string,body?:unknown,method?:string):Promise<T>{const res=await apiFetch(url,{method:method||(body?"POST":"GET"),headers:{"Content-Type":"application/json"},...(body?{body:JSON.stringify(body)}:{})});if(!res.ok)throw await responseError(res);return res.status===204?undefined as T:res.json();}

const CREATE_SETTLED="lingjian:development-create-settled";
type CreateSettlement={key:string;id:string;error:string};
function settleCreate(key:string,id:string,error="") {
 // An old response may release only its own submission, even after a remount.
 if(sessionStorage.getItem(key)!==id)return;
 sessionStorage.removeItem(key);
 window.dispatchEvent(new CustomEvent<CreateSettlement>(CREATE_SETTLED,{detail:{key,id,error}}));
}

export type DevelopmentDraftProps={direction:string;onDirectionChange:(value:string)=>void;inputRef:RefObject<HTMLTextAreaElement|null>;onBusyChange:(busy:boolean)=>void};
export function DevelopmentRequestForm({partnerId,sourceTask=null,sourceCase=null,sourceVersion=null,direction,onDirectionChange,inputRef,onBusyChange}:DevelopmentDraftProps&{partnerId:string|null;sourceTask?:string|null;sourceCase?:string|null;sourceVersion?:number|null}){
 const {user}=useAuth(),router=useRouter();
 const {openCreatedTask}=useTaskNavigation();
 const form=useRef<HTMLElement>(null),generation=useRef(0);
 useEffect(()=>{return()=>{generation.current++;};},[partnerId,sourceTask,sourceCase,sourceVersion]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[pending,setPending]=useState("");
 const inFlight=useRef(false);
 useEffect(()=>{onBusyChange(busy||!!pending);return()=>onBusyChange(false);},[busy,pending,onBusyChange]);
 const submission=useRef(newTaskId()),storageKey=`development:pending-create:${user?.id}:${partnerId}`;
 useEffect(()=>{if(!pending&&!inFlight.current)submission.current=newTaskId();},[direction,pending]);
 useEffect(()=>{
  const saved=sessionStorage.getItem(storageKey)||"";
  submission.current=saved||newTaskId();setPending(saved);setError(saved?uncertainResult:"");
  const settled=(event:Event)=>{
   const detail=(event as CustomEvent<CreateSettlement>).detail;
   if(detail.key!==storageKey||detail.id!==submission.current)return;
   setPending("");setError(detail.error);submission.current=newTaskId();
  };
  window.addEventListener(CREATE_SETTLED,settled);
  return()=>window.removeEventListener(CREATE_SETTLED,settled);
 },[storageKey]);
 async function check(){
  const current=++generation.current,id=pending;
  setBusy(true);
  try{
   const result=await request<{plan_id:string}>(`/development/submissions/${encodeURIComponent(id)}`);
   settleCreate(storageKey,id);tasksChanged();
   if(current===generation.current)router.push(`/tasks/${result.plan_id}`);
  }catch(e){if(current===generation.current&&sessionStorage.getItem(storageKey)===id)setError(e instanceof ApiResponseError&&e.status!==404?e.message:uncertainResult);}
  finally{setBusy(false);}
 }
 async function submit(){
  if(pending||busy||inFlight.current)return;
  setError("");if(!direction.trim()){setError("请描述发展需求。");return;}
  const current=++generation.current,id=submission.current;
  inFlight.current=true;setBusy(true);sessionStorage.setItem(storageKey,id);
  try{
   const result=await request<{plan_id:string}>("/development/plans",{submission_id:id,request:{target_partner_id:partnerId,development_direction:direction,source_task_id:sourceTask,source_case_id:sourceCase,source_case_version:sourceVersion,model_input_allowed:true}});
   settleCreate(storageKey,id);
   if(current!==generation.current){tasksChanged();return;}
   tasksChanged({id:result.plan_id,requirement:direction,createdAt:new Date().toISOString(),taskStatus:"matching",task_type:"development_plan"});openCreatedTask(result.plan_id,direction,form.current);
  }catch(e){
   const uncertain=submissionIsUncertain(e),message=actionFailure((e as Error).message,"建议");
   if(!uncertain)settleCreate(storageKey,id,message);
   if(current!==generation.current)return;
   setError(uncertain?uncertainResult:message);if(uncertain)setPending(id);
  }finally{inFlight.current=false;setBusy(false);}
 }

 return <section ref={form} className="card development-form" data-task-composer><label className="enablement-field">描述当前情况和发展需求<textarea ref={inputRef} aria-label="发展方向" disabled={busy||!!pending} rows={5} maxLength={4000} value={direction} onChange={e=>onDirectionChange(e.target.value)} placeholder="例如：目前有基本的上云迁移能力，希望向 AI Agent 开发方向发展，请推荐适合的课程和实验。"/></label>{error&&<FailureNotice message={error} partial={false}>{pending&&<button className="secondary-btn" disabled={busy} onClick={()=>void check()}>刷新查看</button>}</FailureNotice>}<div className="development-form-actions"><button disabled={busy||!!pending||error===serviceFailure} onClick={()=>void submit()}>{busy?"提交中":error==="本次建议未生成，请重试。"?"重试":"开始"}</button></div></section>;
}

export function DevelopmentPlanDetail({id}:{id:string}){
 const pathname=usePathname(),{user}=useAuth();
 const [data,setData]=useState<Detail|null>(null),[error,setError]=useState(""),[selected,setSelected]=useState(""),[message,setMessage]=useState(""),[busy,setBusy]=useState(false),[preview,setPreview]=useState<{text:string;version_id:string}|null>(null);
 const [panel,setPanel]=useState<"history"|"runs"|null>(null);
 useEffect(()=>{if(panel)document.getElementById(`advisor-${panel}`)?.scrollIntoView({behavior:"smooth",block:"start"});},[panel]);
 const sequence=useRef(0),submission=useRef(newTaskId());
 const [actionError,setActionError]=useState<{text:string;retry:()=>Promise<void>}|null>(null),[pending,setPending]=useState("");
 const pendingRef=useRef(""),inFlight=useRef(false),storageKey=`development:pending:${user?.id}:${id}`;
 function track(value:string){pendingRef.current=value;if(!value)setPending("");if(value)sessionStorage.setItem(storageKey,value);else sessionStorage.removeItem(storageKey);}
 async function load(){
  const seq=++sequence.current;
  try{
   const next=await request<Detail>(`/development/plans/${id}${selected?`?version_id=${encodeURIComponent(selected)}`:""}`);
   if(seq===sequence.current){
    setData(next);setError("");if(next.hidden)setPreview(null);
    const original=pendingRef.current;
    if(original&&(next.runs.some(r=>r.submission_id===original)||next.conversation.some(m=>m.submission_id===original)||(!inFlight.current&&!next.plan.active_run_id&&!next.plan.current_version_id&&["failed","partial","interrupted"].includes(next.runs[0]?.status)))){track("");setActionError(null);submission.current=newTaskId();setMessage("");tasksChanged();}
   }
  }catch(e){if(seq===sequence.current){if(e instanceof ApiResponseError&&[401,403,404].includes(e.status)){setData(null);setPreview(null);}setError((e as Error).message);}}
 }
 useEffect(()=>{const saved=sessionStorage.getItem(storageKey)||"";pendingRef.current=saved;setPending(saved);void load();const timer=setInterval(()=>void load(),2000);return()=>{clearInterval(timer);sequence.current++;};},[id,selected,storageKey]);
 useEffect(()=>{setPreview(null);},[data?.plan.current_version_id,data?.hidden,selected]);
 useEffect(()=>{if(!preview)return;let live=true;async function refresh(){try{const r=await request<{text:string;version_id:string}>(`/development/plans/${id}/transferable`);if(live)setPreview(r);}catch{if(live)setPreview(null);}}const t=setInterval(()=>void refresh(),10000);window.addEventListener("focus",refresh);return()=>{live=false;clearInterval(t);window.removeEventListener("focus",refresh);};},[id,!!preview]);
 async function action(fn:()=>Promise<void>,operation="处理",submissionId?:string){
  if(busy||pendingRef.current)return;
  inFlight.current=true;setBusy(true);setActionError(null);
  if(submissionId)track(submissionId);
  try{await fn();if(submissionId)track("");await load();tasksChanged();}
  catch(e){
   if(submissionId){if(!submissionIsUncertain(e))track("");else if(pendingRef.current)setPending(submissionId);else return;}
   setActionError({text:actionFailure((e as Error).message,operation),retry:()=>action(fn,operation,submissionId)});
  }finally{inFlight.current=false;setBusy(false);}
 }
 if(!data)return <div className="page advisor-detail">{error&&<TaskArrivalReadError id={id}/>}{error?<FailureNotice message={error} partial={false}>{error===uncertainResult&&<button className="secondary-btn" onClick={()=>void load()}>刷新查看</button>}</FailureNotice>:<p role="status">正在读取发展建议…</p>}</div>;
 const {plan,payload}=data,analysis=payload?.analysis,running=!!plan.active_run_id,locked=busy||running||!!pending||plan.status==="archived",historical=!!selected&&selected!==plan.current_version_id;
 const currentAvailable=!!plan.current_version_id&&data.presentation.current_available&&!error;
 const impact=["发展诉求已保留。",currentAvailable?"当前建议仍可使用。":""].filter(Boolean).join("");
 async function chat(){await action(async()=>{await request(`/development/plans/${id}/conversation`,{submission_id:submission.current,based_on_version_id:plan.current_version_id,message});submission.current=newTaskId();setMessage("");setSelected("");},"回答",submission.current);}
 const legacyAnswer=analysis?[analysis.interpretation,...analysis.priorities.map((p,i)=>`${i+1}. ${p.name}：${p.reason}`)].filter(Boolean).join("\n\n"):"";
 const items=payload?.stages.flatMap(s=>s.items)||[];
 const latest=data.runs[0],failed=latest&&["failed","partial","interrupted"].includes(latest.status);
 const summary=data.presentation.state==="archived"?"已归档":data.hidden?"部分内容已受限":data.scopeMessage?"处理完成":payload?"建议可用":running?"正在整理建议":failed?"生成失败，可重试":"暂未生成建议";
 function suggest(text:string){if(locked||historical)return;setActionError(null);setMessage(text);submission.current=newTaskId();document.getElementById("advisor-chat")?.scrollIntoView({behavior:"smooth",block:"center"});}
 return <div className="page development-detail advisor-detail"><Link href={pathname.startsWith("/admin") ? "/admin/tasks" : "/tasks"}>← 全部任务</Link>
 <header className="advisor-heading"><div>{data.partner_name&&<p className="eyebrow">{data.partner_name}</p>}<h1>能力发展建议</h1><p className="advisor-status" data-testid="advisor-status">{summary}</p></div><details className="advisor-more"><summary>更多</summary><div className="advisor-menu" onClick={e=>{if((e.target as HTMLElement).closest("button"))e.currentTarget.closest("details")?.removeAttribute("open");}}><button className="secondary-btn" onClick={()=>setPanel(panel==="history"?null:"history")}>历史版本</button><button className="secondary-btn" disabled={busy||historical||!plan.current_version_id||data.hidden||plan.status==="archived"} onClick={()=>void action(async()=>{setPreview(await request<{text:string;version_id:string}>(`/development/plans/${id}/transferable`));})}>伙伴可传递视图预览</button><button className="secondary-btn" onClick={()=>setPanel(panel==="runs"?null:"runs")}>运行记录</button><button className="secondary-btn" disabled={busy||running||!!pending} onClick={()=>void action(async()=>{await request(`/agent/tasks/${id}/${plan.status==="archived"?"restore":"archive"}`,{},"PATCH");})}>{plan.status==="archived"?"恢复方案":"归档方案"}</button></div></details></header>
 {error&&!pending&&<div role="alert"><FailureNotice message={error} partial={false}>{error===uncertainResult&&<button className="secondary-btn" disabled={busy} onClick={()=>void load()}>刷新查看</button>}</FailureNotice></div>}
 {running&&<p role="status" className="notice-neutral">{currentAvailable?"伴飞正在整理建议，你可以继续查看已有内容。":"伴飞正在整理建议。"}</p>}
 {(pending||actionError)&&<FailureNotice message={pending?uncertainResult:actionError?.text} partial={currentAvailable} impact={currentAvailable?"当前建议仍可使用。":undefined}>
  {pending?<button className="secondary-btn" disabled={busy} onClick={()=>void load()}>刷新查看</button>:actionError?.text===uncertainResult?<button className="secondary-btn" disabled={busy} onClick={()=>{setActionError(null);void load();}}>刷新查看</button>:actionError?.text.includes("失败，请重试。")&&<button className="secondary-btn" disabled={locked||historical||!!error} onClick={()=>void actionError.retry()}>重试</button>}
 </FailureNotice>}
 {failed&&!pending&&!actionError&&<div data-testid="advisor-run-notice"><FailureNotice details={data.failureDetails} operation={latest.run_type==="generate"?"建议":"调整"} partial={currentAvailable} impact={impact}>
  {!running&&failureMessage(data.failureDetails)!==serviceFailure&&<button className="secondary-btn" disabled={locked||historical||!!error} onClick={()=>void action(async()=>{await request(`/development/plans/${id}/retry`,{submission_id:submission.current,based_on_version_id:plan.current_version_id,run_id:latest.id});submission.current=newTaskId();},latest.run_type==="generate"?"建议":"调整",submission.current)}>重试</button>}
 </FailureNotice></div>}{data.notice&&<p className="notice-neutral">{data.notice}</p>}

 {data.hidden&&<TaskArrivalReadError id={id} keepInput={false}/>}
 {panel==="history"&&<section className="card advisor-secondary" id="advisor-history" data-testid="version-history"><h2>历史版本</h2><PlanStatus value={data.presentation}/><label className="enablement-field">查看版本<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">最新建议</option>{data.versions.map(v=><option key={v.id} value={v.id}>V{v.version_no}{v.id===plan.current_version_id?" · 当前版本":" · 历史版本"}</option>)}</select></label><button className="secondary-btn" onClick={()=>setPanel(null)}>收起历史版本</button></section>}
 {historical&&<p className="notice-neutral">正在查看历史内容。<button className="secondary-btn" onClick={()=>setSelected("")}>返回最新建议继续交流</button></p>}
 {!data.hidden&&<TaskRequest id={id} className="advisor-direction" testId="advisor-direction">{data.executionInput||data.request.raw_demand||data.request.development_direction||data.request.development_goal}</TaskRequest>}
 <TaskProgress value={data.progress} taskId={id}/>
 {data.scopeMessage&&<TaskResult id={id} className="card" testId="scope-result"><p>{data.scopeMessage}</p></TaskResult>}
 {data.analysis&&(!payload||running)&&<TaskResult id={id} className="card" testId="development-analysis"><h2>发展方向分析</h2><p>{data.analysis.interpretation}</p>{data.analysis.partner_assessment&&<p>{data.analysis.partner_assessment}</p>}{data.analysis.priorities.map((item,i)=><p key={i}><strong>{item.name}</strong>：{item.reason}</p>)}{data.analysis.basis_limitations?.map((text,i)=><p className="muted" key={`limit-${i}`}>{text}</p>)}</TaskResult>}
 {payload&&<>
 <TaskResult id={id} className="card task-answer" testId="advisor-main-answer"><AdvisorAnswer text={payload.answer||legacyAnswer}/></TaskResult>
 <TaskResult id={id} testId="stages" className="card advisor-priorities"><h2>引用资源</h2>{items.length?items.map((item,index)=><ResourceAdvice key={item.item_id||index} item={item} position={index+1}/>):<p className="muted">本次答复没有引用资源。</p>}</TaskResult>
 {(payload.limitations.length>0||payload.resource_gaps.length>0)&&<TaskResult id={id} className="card" testId="gaps"><h2>使用提示</h2>{[...payload.limitations,...payload.resource_gaps].map((v,i)=><p key={i}>{v}</p>)}</TaskResult>}
 </>}
 {!data.hidden&&<section id="advisor-chat" className="card advisor-chat" data-testid="conversation"><h2>继续问伴飞</h2><p className="muted">问问原因、比较资源，或告诉我你想怎样调整。</p>{data.conversation?.map(m=><div key={m.submission_id} className="advisor-exchange"><p className="advisor-question"><strong>你</strong><br/>{m.message}</p><AdvisorAnswer text={m.answer}/>{m.resources?.map((item,i)=><ResourceAdvice key={i} item={item}/>)}</div>)}<div className="advisor-composer"><div className="advisor-prompts">{["为什么优先推荐这个方向？","这两个实验有什么区别？","有没有更进阶一点的实验？","不要基础课，多给实验。","系统集成优先，RAG 放后面。"].map(text=><button key={text} className="secondary-btn" disabled={locked||historical} onClick={()=>suggest(text)}>{text}</button>)}</div><label className="enablement-field">消息<textarea disabled={locked} rows={3} maxLength={2000} value={message} onChange={e=>{setMessage(e.target.value);submission.current=newTaskId();setActionError(null);}} placeholder="继续问伴飞，或说说希望如何调整…"/></label><div className="enablement-actions"><button disabled={locked||!message.trim()||historical||!plan.current_version_id} onClick={()=>void chat()}>{busy?"正在回复…":"发送"}</button>{!plan.current_version_id&&!running&&!failed&&!pending&&!actionError&&<button className="secondary-btn" disabled={busy||plan.status==="archived"} onClick={()=>void action(async()=>{await request(`/development/plans/${id}/revise`,{submission_id:submission.current,based_on_version_id:null,instruction:"重新生成能力发展建议"});submission.current=newTaskId();},"建议",submission.current)}>重新生成</button>}</div></div></section>}
 {preview&&<section id="transfer-preview" className="card" data-testid="transfer-preview"><h2>伙伴可传递视图</h2><pre className="development-text">{preview.text}</pre><button disabled={busy} onClick={()=>void action(async()=>{const r=await request<{text:string;version_id:string}>(`/development/plans/${id}/copy`,{version_id:preview.version_id});if (!await copyText(r.text,document.querySelector<HTMLElement>("#transfer-preview pre"))) throw new Error("复制失败，内容已选中，请按 Ctrl+C 手动复制。");setPreview(r);})}>复制内容</button><button className="secondary-btn" onClick={()=>setPreview(null)}>关闭预览</button></section>}
 {panel==="runs"&&<section className="card advisor-secondary" id="advisor-runs" data-testid="run-records"><h2>运行记录</h2>{data.runs.map(r=><p key={r.id}>{r.run_type==="generate"?"生成":"调整"} · {names[r.status]||r.status} · {new Date(r.created_at).toLocaleString("zh-CN")}</p>)}</section>}</div>;
}
