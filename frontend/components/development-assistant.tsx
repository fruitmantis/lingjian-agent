"use client";
import {AdvisorAnswer} from "./advisor-answer";
import {FailureNotice,failureMessage,actionFailure,uncertainResult,serviceFailure,type FailureDetail} from "./task-failure";
import Link from "next/link";
import {UiIcon} from "./ui-icons";
import {PlanStatus,type PlanPresentation} from "./plan-status";
import {useEffect,useState,useRef} from "react";
import {useRouter,usePathname} from "next/navigation";
import {apiFetch,useAuth} from "./auth-provider";
import {ApiResponseError,responseError} from "../lib/api-request";
import {tasksChanged,newTaskId} from "./task-navigation";

type Item={source_type:string;source_id:string;source_version:number;capability_tag_id:string;focus?:string;reason:string;estimated_hours:number;note:string;title?:string;prerequisites?:string;availability?:string;conditions?:{duration_minutes?:number;level?:string;roles?:{id:string;name:string}[];zones?:{id:string;name:string}[];lab_requirements?:string;cost?:string;account_requirement?:string;environment_requirement?:string;language?:string;site?:string}};
type Stage={title:string;items:Item[]};
type Analysis={intent:string;interpretation:string;partner_assessment?:string;reusable_basis:string[];priorities:{name:string;reason:string;reusable_basis?:string[]}[];basis_limitations:string[]};
type Payload={analysis?:Analysis;answer?:string;next_steps?:string[];overview:{development_direction?:string;development_goal?:string};stages:Stage[];limitations:string[];resource_gaps:string[]};
type Detail={failureDetails?:FailureDetail[];presentation:PlanPresentation;plan:{id:string;current_version_id:string|null;status:string;active_run_id:string|null};partner_name:string;request:{development_direction?:string;development_goal?:string;raw_demand?:string};conversation:{submission_id:string;message:string;answer:string}[];payload:Payload|null;hidden:boolean;notice:string|null;versions:{id:string;version_no:number}[];runs:{id:string;submission_id:string;run_type:string;status:string;created_at:string;safe_error_message:string|null}[]};
const names:Record<string,string>={course:"课程",lab:"实验",case:"共享案例",unknown:"未知",free:"免费",paid:"付费",pending:"等待处理",running:"正在处理",ready:"已完成",failed:"失败",partial:"部分完成",interrupted:"已中断"};
const display=(v?:string|number)=>names[String(v)]||v||"未知";
function ResourceAdvice({item:i}:{item:Item}){
 const duration=Number(i.conditions?.duration_minutes);
 return <article className="advisor-resource" data-testid="resource-advice"><div className="advisor-resource-title"><UiIcon name={i.source_type==="lab"?"settings":i.source_type==="case"?"users":"file"} size={18}/><span className="advisor-resource-type">{names[i.source_type]}</span><h4>{i.title}</h4></div><p>{i.reason}</p><dl className="advisor-conditions">{i.source_type!=="course"&&<div><dt>时长</dt><dd>{Number.isFinite(duration)&&duration>0?`${duration/60} 小时`:"未知"}</dd></div>}{i.source_type==="case"?<><div><dt>费用</dt><dd>{display(i.conditions?.cost)}</dd></div><div><dt>账号</dt><dd>{display(i.conditions?.account_requirement)}</dd></div><div><dt>环境</dt><dd>{display(i.conditions?.environment_requirement)}</dd></div><div><dt>语言 / 站点</dt><dd>{display(i.conditions?.language)} / {display(i.conditions?.site)}</dd></div><div><dt>先修</dt><dd>{i.prerequisites||"未知"}</dd></div></>:<><div><dt>层级</dt><dd>{i.conditions?.level==='basic'?'基础':i.conditions?.level==='advanced'?'进阶':'待补充'}</dd></div>{!![...(i.conditions?.roles||[]),...(i.conditions?.zones||[])].length&&<div><dt>分类</dt><dd>{[...(i.conditions?.roles||[]),...(i.conditions?.zones||[])].map(c=>c.name).join(' · ')}</dd></div>}</>}</dl>{i.availability==="available"?<Link href={`/resources/${i.source_type}/${i.source_id}?source_version=${i.source_version}`}>{i.source_type==="case"?"查看来源与发起跳转 →":"查看资源 →"}</Link>:<p className="muted">当前资源不可用，历史引用保留。</p>}</article>;
}
async function request<T>(url:string,body?:unknown,method?:string):Promise<T>{const res=await apiFetch(url,{method:method||(body?"POST":"GET"),headers:{"Content-Type":"application/json"},...(body?{body:JSON.stringify(body)}:{})});if(!res.ok)throw await responseError(res);return res.status===204?undefined as T:res.json();}

export function DevelopmentRequestForm({partnerId,sourceTask=null,sourceCase=null,sourceVersion=null}:{partnerId:string;sourceTask?:string|null;sourceCase?:string|null;sourceVersion?:number|null}){
 const {user}=useAuth(),router=useRouter();
 const [direction,setDirection]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState(""),[pending,setPending]=useState("");
 const submission=useRef(newTaskId()),storageKey=`development:pending-create:${user?.id}:${partnerId}`;
 useEffect(()=>{const saved=sessionStorage.getItem(storageKey)||"";submission.current=saved||newTaskId();setPending(saved);setError(saved?uncertainResult:"");},[storageKey]);
 async function check(){
  setBusy(true);
  try{const result=await request<{plan_id:string}>(`/development/submissions/${encodeURIComponent(pending)}`);sessionStorage.removeItem(storageKey);tasksChanged();router.push(`/tasks/${result.plan_id}`);}
  catch(e){setError(e instanceof ApiResponseError&&e.status!==404?e.message:uncertainResult);}
  finally{setBusy(false);}
 }
 async function submit(){
  if(pending||busy)return;
  setError("");if(!partnerId||!direction.trim()){setError("请选择目标伙伴，并描述想发展的方向。");return;}
  setBusy(true);sessionStorage.setItem(storageKey,submission.current);
  try{const result=await request<{plan_id:string}>("/development/plans",{submission_id:submission.current,request:{target_partner_id:partnerId,development_direction:direction,source_task_id:sourceTask,source_case_id:sourceCase,source_case_version:sourceVersion,model_input_allowed:true}});sessionStorage.removeItem(storageKey);tasksChanged();router.push(`/tasks/${result.plan_id}`);}
  catch(e){const text=(e as Error).message;setError(actionFailure(text,"建议"));if(!(e instanceof ApiResponseError)){setPending(submission.current);setError(uncertainResult);}else sessionStorage.removeItem(storageKey);}
  finally{setBusy(false);}
 }
 return <section className="card development-form"><h2>发展方向</h2><label className="enablement-field">你希望这个伙伴往什么方向发展？<textarea aria-label="发展方向" disabled={busy||!!pending} rows={5} maxLength={4000} value={direction} onChange={e=>{setDirection(e.target.value);submission.current=newTaskId();}} placeholder="例如：希望未来能够独立承担企业级 Agent 和 RAG 项目交付。也可以问：这个伙伴下一步适合往哪里发展？"/></label>{error&&<FailureNotice message={error} partial={false}>{pending&&<button className="secondary-btn" disabled={busy} onClick={()=>void check()}>刷新查看</button>}</FailureNotice>}<div className="development-form-actions"><p className="muted">点击生成，即允许本次分析使用你填写的方向、当前伙伴的最小画像摘要及页面带入的来源上下文。内部附件与案例原文不发送；学习资源仅用于准备，交付能力仍需真实项目验证。</p><button disabled={busy||!!pending||error===serviceFailure} onClick={()=>void submit()}>{busy?"正在处理…":error==="本次建议未生成，请重试。"?"重试":"生成能力发展建议"}</button></div></section>;
}

export function DevelopmentPlanDetail({id}:{id:string}){
 const pathname=usePathname(),{user}=useAuth();
 const [data,setData]=useState<Detail|null>(null),[error,setError]=useState(""),[selected,setSelected]=useState(""),[message,setMessage]=useState(""),[busy,setBusy]=useState(false),[preview,setPreview]=useState<{text:string;version_id:string}|null>(null);
 const [panel,setPanel]=useState<"history"|"runs"|null>(null);
 useEffect(()=>{if(panel)document.getElementById(`advisor-${panel}`)?.scrollIntoView({behavior:"smooth",block:"start"});},[panel]);
 const sequence=useRef(0),submission=useRef(newTaskId());
 const [actionError,setActionError]=useState<{text:string;retry:()=>Promise<void>}|null>(null),[pending,setPending]=useState("");
 const pendingRef=useRef(""),storageKey=`development:pending:${user?.id}:${id}`;
 function track(value:string){pendingRef.current=value;if(!value)setPending("");if(value)sessionStorage.setItem(storageKey,value);else sessionStorage.removeItem(storageKey);}
 async function load(){
  const seq=++sequence.current;
  try{
   const next=await request<Detail>(`/development/plans/${id}${selected?`?version_id=${encodeURIComponent(selected)}`:""}`);
   if(seq===sequence.current){
    setData(next);setError("");if(next.hidden)setPreview(null);
    const original=pendingRef.current;
    if(original&&(next.runs.some(r=>r.submission_id===original)||next.conversation.some(m=>m.submission_id===original))){track("");setActionError(null);submission.current=newTaskId();setMessage("");tasksChanged();}
   }
  }catch(e){if(seq===sequence.current){if(e instanceof ApiResponseError&&[401,403,404].includes(e.status)){setData(null);setPreview(null);}setError((e as Error).message);}}
 }
 useEffect(()=>{const saved=sessionStorage.getItem(storageKey)||"";pendingRef.current=saved;setPending(saved);void load();const timer=setInterval(()=>void load(),2000);return()=>{clearInterval(timer);sequence.current++;};},[id,selected,storageKey]);
 useEffect(()=>{setPreview(null);},[data?.plan.current_version_id,data?.hidden,selected]);
 useEffect(()=>{if(!preview)return;let live=true;async function refresh(){try{const r=await request<{text:string;version_id:string}>(`/development/plans/${id}/transferable`);if(live)setPreview(r);}catch{if(live)setPreview(null);}}const t=setInterval(()=>void refresh(),10000);window.addEventListener("focus",refresh);return()=>{live=false;clearInterval(t);window.removeEventListener("focus",refresh);};},[id,!!preview]);
 async function action(fn:()=>Promise<void>,operation="处理",submissionId?:string){
  if(busy||pendingRef.current)return;
  setBusy(true);setActionError(null);
  if(submissionId)track(submissionId);
  try{await fn();if(submissionId)track("");await load();tasksChanged();}
  catch(e){
   if(submissionId){if(e instanceof ApiResponseError)track("");else if(pendingRef.current)setPending(submissionId);else return;}
   setActionError({text:actionFailure((e as Error).message,operation),retry:()=>action(fn,operation,submissionId)});
  }finally{setBusy(false);}
 }
 if(!data)return <div className="page">{error?<FailureNotice message={error} partial={false}>{error===uncertainResult&&<button className="secondary-btn" onClick={()=>void load()}>刷新查看</button>}</FailureNotice>:<p role="status">正在读取发展建议…</p>}</div>;
 const {plan,payload}=data,analysis=payload?.analysis,running=!!plan.active_run_id,locked=busy||running||!!pending||plan.status==="archived",historical=!!selected&&selected!==plan.current_version_id;
 const currentAvailable=!!plan.current_version_id&&data.presentation.current_available&&!error;
 const impact=["发展诉求已保留。",currentAvailable?"当前建议仍可使用。":""].filter(Boolean).join("");
 async function chat(){await action(async()=>{await request(`/development/plans/${id}/conversation`,{submission_id:submission.current,based_on_version_id:plan.current_version_id,message});submission.current=newTaskId();setMessage("");setSelected("");},"回答",submission.current);}
 const short=analysis?.intent==="resources",explore=analysis?.intent==="explore",priorities=analysis?.priorities||[];
 const items=payload?.stages.flatMap(s=>s.items)||[];
 const ungrouped=items.filter(i=>!priorities.some(p=>p.name===i.focus));
 const latest=data.runs[0],failed=latest&&["failed","partial","interrupted"].includes(latest.status);
 const summary=data.presentation.state==="archived"?"已归档":data.hidden?"部分内容已受限":payload?"建议可用":running?"正在整理建议":"暂未生成建议";
 function suggest(text:string){if(locked||historical)return;setActionError(null);setMessage(text);submission.current=newTaskId();document.getElementById("advisor-chat")?.scrollIntoView({behavior:"smooth",block:"center"});}
 return <div className="page development-detail advisor-detail"><Link href={pathname.startsWith("/admin") ? "/admin/tasks" : "/tasks"}>← 全部任务</Link>
 <header className="advisor-heading"><div><p className="eyebrow">{data.partner_name}</p><h1>能力发展建议</h1><p className="advisor-status" data-testid="advisor-status">{summary}</p></div><details className="advisor-more"><summary>更多</summary><div className="advisor-menu" onClick={e=>{if((e.target as HTMLElement).closest("button"))e.currentTarget.closest("details")?.removeAttribute("open");}}><button className="secondary-btn" onClick={()=>setPanel(panel==="history"?null:"history")}>历史版本</button><button className="secondary-btn" disabled={busy||historical||!plan.current_version_id||data.hidden||plan.status==="archived"} onClick={()=>void action(async()=>{setPreview(await request<{text:string;version_id:string}>(`/development/plans/${id}/transferable`));})}>伙伴可传递视图预览</button><button className="secondary-btn" onClick={()=>setPanel(panel==="runs"?null:"runs")}>运行记录</button><button className="secondary-btn" disabled={busy||running||!!pending} onClick={()=>void action(async()=>{await request(`/agent/tasks/${id}/${plan.status==="archived"?"restore":"archive"}`,{},"PATCH");})}>{plan.status==="archived"?"恢复方案":"归档方案"}</button></div></details></header>
 {error&&!pending&&<div role="alert"><FailureNotice message={error} partial={false}>{error===uncertainResult&&<button className="secondary-btn" disabled={busy} onClick={()=>void load()}>刷新查看</button>}</FailureNotice></div>}
 {running&&<p role="status" className="notice-neutral">{currentAvailable?"伴飞正在整理建议，你可以继续查看已有内容。":"伴飞正在整理建议。"}</p>}
 {(pending||actionError)&&<FailureNotice message={pending?uncertainResult:actionError?.text} partial={currentAvailable} impact={currentAvailable?"当前建议仍可使用。":undefined}>
  {pending?<button className="secondary-btn" disabled={busy} onClick={()=>void load()}>刷新查看</button>:actionError?.text===uncertainResult?<button className="secondary-btn" disabled={busy} onClick={()=>{setActionError(null);void load();}}>刷新查看</button>:actionError?.text.includes("失败，请重试。")&&<button className="secondary-btn" disabled={locked||historical||!!error} onClick={()=>void actionError.retry()}>重试</button>}
 </FailureNotice>}
 {failed&&!pending&&!actionError&&<div data-testid="advisor-run-notice"><FailureNotice details={data.failureDetails} operation={latest.run_type==="generate"?"建议":"调整"} partial={currentAvailable} impact={impact}>
  {!running&&failureMessage(data.failureDetails)!==serviceFailure&&<button className="secondary-btn" disabled={locked||historical||!!error} onClick={()=>void action(async()=>{await request(`/development/plans/${id}/retry`,{submission_id:submission.current,based_on_version_id:plan.current_version_id,run_id:latest.id});submission.current=newTaskId();},latest.run_type==="generate"?"建议":"调整",submission.current)}>重试</button>}
 </FailureNotice></div>}{data.notice&&<p className="notice-neutral">{data.notice}</p>}

 {panel==="history"&&<section className="card advisor-secondary" id="advisor-history" data-testid="version-history"><h2>历史版本</h2><PlanStatus value={data.presentation}/><label className="enablement-field">查看版本<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">最新建议</option>{data.versions.map(v=><option key={v.id} value={v.id}>V{v.version_no}{v.id===plan.current_version_id?" · 当前版本":" · 历史版本"}</option>)}</select></label><button className="secondary-btn" onClick={()=>setPanel(null)}>收起历史版本</button></section>}
 {historical&&<p className="notice-neutral">正在查看历史内容。<button className="secondary-btn" onClick={()=>setSelected("")}>返回最新建议继续交流</button></p>}
 {!data.hidden&&<section className="card advisor-direction" data-testid="advisor-direction"><h2>{short?(items.length&&items.every(i=>i.source_type==="lab")?"实验建议":items.length&&items.every(i=>i.source_type==="course")?"课程建议":"资源建议"):explore?"值得考虑的发展方向":"目标方向"}</h2><p className="advisor-lead">{analysis?.interpretation||data.request.development_direction||data.request.development_goal||data.request.raw_demand}</p>{!short&&data.request.raw_demand&&data.request.raw_demand!==analysis?.interpretation&&<p className="muted">用户诉求：{data.request.raw_demand}</p>}</section>}
 {payload&&<>
 {analysis&&!short&&<section className="card advisor-basis" data-testid="analysis"><h2>基于当前伙伴画像</h2><p className="advisor-lead">{analysis.partner_assessment||analysis.reusable_basis.join("；")||"当前画像依据有限，本次建议主要结合发展方向形成。"}</p>{analysis.basis_limitations.map((text,i)=><p key={i} className="muted">{text}</p>)}</section>}
 <div data-testid="stages" className="advisor-priorities">
 {!short&&priorities.map((p,index)=><section className="card advisor-focus" key={p.name} data-testid="advisor-focus"><p className="advisor-kicker">{explore?"可考虑方向":"建议重点"} {index+1}</p><h2>{p.name}</h2><p>{p.reason}</p>{!!p.reusable_basis?.length&&<p className="advisor-reuse"><strong>可复用基础：</strong>{p.reusable_basis.join("；")}</p>}{!explore&&items.filter(i=>i.focus===p.name).map((i,n)=><ResourceAdvice key={n} item={i}/>)}{explore&&<button className="secondary-btn" onClick={()=>suggest(`请围绕${p.name}展开建议`)}>继续讨论这个方向</button>}</section>)}
 {!explore&&(short?items:ungrouped).length>0&&<section className="card"><h2>{short?"推荐资源":priorities.length?"其他相关资源":"推荐资源"}</h2>{payload.answer&&short&&<p>{payload.answer}</p>}{(short?items:ungrouped).map((i,n)=><ResourceAdvice key={n} item={i}/>)}</section>}
 </div>
 {!explore&&(payload.limitations.length>0||payload.resource_gaps.length>0)&&<section className="card" data-testid="gaps"><h2>使用提示与资源缺口</h2>{[...payload.limitations,...payload.resource_gaps].map((v,i)=><p key={i}>{v}</p>)}</section>}
 {!!payload.next_steps?.length&&!short&&!explore&&<section className="card"><h2>下一步项目实践</h2>{payload.next_steps.map((s,i)=><p key={i}>{s}</p>)}</section>}
 </>}
 {!data.hidden&&<section id="advisor-chat" className="card advisor-chat" data-testid="conversation"><h2>继续问伴飞</h2><p className="muted">问问原因、比较资源，或告诉我你想怎样调整。</p>{data.conversation?.map(m=><div key={m.submission_id} className="advisor-exchange"><p className="advisor-question"><strong>你</strong><br/>{m.message}</p><AdvisorAnswer text={m.answer}/></div>)}<div className="advisor-prompts">{["为什么优先推荐这个方向？","这两个实验有什么区别？","有没有更进阶一点的实验？","不要基础课，多给实验。","系统集成优先，RAG 放后面。"].map(text=><button key={text} className="secondary-btn" disabled={locked||historical} onClick={()=>suggest(text)}>{text}</button>)}</div><label className="enablement-field">消息<textarea disabled={locked} rows={3} maxLength={2000} value={message} onChange={e=>{setMessage(e.target.value);submission.current=newTaskId();setActionError(null);}} placeholder="继续问伴飞，或说说希望如何调整…"/></label><div className="enablement-actions"><button disabled={locked||!message.trim()||historical||!plan.current_version_id} onClick={()=>void chat()}>{busy?"正在回复…":"发送"}</button>{!plan.current_version_id&&!running&&!failed&&!pending&&!actionError&&<button className="secondary-btn" disabled={busy||plan.status==="archived"} onClick={()=>void action(async()=>{await request(`/development/plans/${id}/revise`,{submission_id:submission.current,based_on_version_id:null,instruction:"重新生成能力发展建议"});submission.current=newTaskId();},"建议",submission.current)}>重新生成</button>}</div></section>}
 {preview&&<section className="card" data-testid="transfer-preview"><h2>伙伴可传递视图</h2><pre className="development-text">{preview.text}</pre><button disabled={busy} onClick={()=>void action(async()=>{const r=await request<{text:string;version_id:string}>(`/development/plans/${id}/copy`,{version_id:preview.version_id});await navigator.clipboard.writeText(r.text);setPreview(r);})}>复制内容</button><button className="secondary-btn" onClick={()=>setPreview(null)}>关闭预览</button></section>}
 {panel==="runs"&&<section className="card advisor-secondary" id="advisor-runs" data-testid="run-records"><h2>运行记录</h2>{data.runs.map(r=><p key={r.id}>{r.run_type==="generate"?"生成":"调整"} · {names[r.status]||r.status} · {new Date(r.created_at).toLocaleString("zh-CN")}</p>)}</section>}</div>;
}
