"use client";
import {useEffect,useState} from "react";
import {apiFetch} from "./auth-provider";
import {responseError} from "../lib/api-request";
import {UiIcon,type IconName} from "./ui-icons";

export type AgentId="partner_match"|"partner_development";
type PublicAgent={id:AgentId;name:string;description:string;icon:IconName;enabled:boolean};
const defaults:Record<AgentId,PublicAgent>={
 partner_match:{id:"partner_match",name:"伙伴匹配",description:"结合项目需求和已有伙伴资料，寻找合适的交付伙伴。",icon:"users",enabled:true},
 partner_development:{id:"partner_development",name:"伙伴发展",description:"围绕发展目标，提供能力建议与合适的课程、实验资源。",icon:"trend",enabled:true},
};
export function useAgent(id:AgentId){
 const [agents,setAgents]=useState<PublicAgent[]>([]);
 useEffect(()=>{let active=true;apiFetch("/agents",{cache:"no-store"}).then(async r=>{if(r.ok&&active)setAgents(await r.json());}).catch(()=>{});return()=>{active=false;};},[]);
 return agents.find(a=>a.id===id)||defaults[id];
}
export function AgentBadge({id}:{id:AgentId}){
 const agent=useAgent(id);
 return <span className="enablement-badge" data-agent-id={id}><UiIcon name={agent.icon} size={16}/> {agent.name}{!agent.enabled?" · 已停用":""}</span>;
}

type ModelOptions={modelConfigId:string|null;thinking:boolean;timeoutSeconds:number;timeoutRetries:number};
type AgentOptions=ModelOptions&{name:string;description:string;icon:IconName;enabled:boolean};
type Settings={agents:Record<AgentId,AgentOptions>;processing:ModelOptions};
type Model={id:string;name:string;modelName:string;enabled:boolean};
const icons:IconName[]=["users","trend","search","puzzle","building","toolbox","spark"];

function AgentEditor({id,initial,models,onSaved}:{id:AgentId|"processing";initial:AgentOptions|ModelOptions;models:Model[];onSaved:(settings:Settings)=>void}){
 const [draft,setDraft]=useState(initial),[saving,setSaving]=useState(false),[message,setMessage]=useState("");
 useEffect(()=>setDraft(initial),[initial]);
 const agent=id!=="processing"?draft as AgentOptions:null;
 function update(values:Partial<AgentOptions>){setMessage("");setDraft(old=>({...old,...values}));}
 async function save(){
  setSaving(true);setMessage("");
  try{const response=await apiFetch(`/admin/agents/${id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(draft)});if(!response.ok)throw await responseError(response);onSaved(await response.json());setMessage("已保存");}
  catch(error){setMessage(error instanceof Error?error.message:"保存失败");}finally{setSaving(false);}
 }
 return <section className="card" data-testid={`agent-${id}`}>
  <h2>{agent?<><UiIcon name={agent.icon} size={20}/> {agent.name}</>:"基础配置"}</h2>
  <p className="muted">{agent?"停用后不再接受新建、续问和重试；已受理任务继续，历史结果保留。":"用于独立画像生成、摘要等基础任务；资料文件解析不调用模型。"}</p>
  <div className="agent-settings-fields">
   {agent&&<><label className="enablement-field">展示名称<input maxLength={60} value={agent.name} onChange={e=>update({name:e.target.value})}/></label>
    <label className="enablement-field">图标<select value={agent.icon} onChange={e=>update({icon:e.target.value as IconName})}>{icons.map(icon=><option key={icon} value={icon}>{({users:"伙伴",trend:"发展",search:"搜索",puzzle:"能力",building:"行业",toolbox:"工具",spark:"灵感"})[icon as "users"]}</option>)}</select></label>
    <label className="enablement-field agent-description">简介<textarea maxLength={300} rows={2} value={agent.description} onChange={e=>update({description:e.target.value})}/></label></>}
   <label className="enablement-field">模型<select value={draft.modelConfigId||""} onChange={e=>update({modelConfigId:e.target.value||null})}><option value="">请选择模型连接</option>{draft.modelConfigId&&!models.some(m=>m.id===draft.modelConfigId&&m.enabled)&&<option value={draft.modelConfigId}>原模型已停用或删除，请重新选择</option>}{models.filter(m=>m.enabled).map(m=><option key={m.id} value={m.id}>{m.name} · {m.modelName==="deepseek-v4-flash"?"deepseek-flash":m.modelName}</option>)}</select></label>
   <label className="enablement-field">请求超时（秒）<input type="number" min={0.1} step="any" value={draft.timeoutSeconds} onChange={e=>update({timeoutSeconds:Number(e.target.value)})}/></label>
   <label><input type="checkbox" checked={draft.thinking} onChange={e=>update({thinking:e.target.checked})}/> 开启思考（模型支持时）</label>
   {agent&&<label><input type="checkbox" checked={agent.enabled} onChange={e=>update({enabled:e.target.checked})}/> 启用智能体</label>}
  </div>
  <div className="enablement-actions"><button disabled={saving||!draft.modelConfigId||draft.timeoutSeconds<=0||!!(agent&&!agent.name.trim())} onClick={()=>void save()}>{saving?"保存中…":"保存配置"}</button>{message&&<span role="status">{message}</span>}</div>
 </section>;
}

export function AgentManagement({models}:{models:Model[]}){
 const [settings,setSettings]=useState<Settings|null>(null),[error,setError]=useState("");
 async function load(){setError("");try{const r=await apiFetch("/admin/agents",{cache:"no-store"});if(!r.ok)throw await responseError(r);setSettings(await r.json());}catch(e){setError(e instanceof Error?e.message:"智能体配置加载失败");}}
 useEffect(()=>{void load();},[]);
 if(error)return <p role="alert">{error} <button className="secondary-btn" onClick={()=>void load()}>重试</button></p>;
 if(!settings)return <p role="status">正在读取智能体配置…</p>;
 return <><div className="agent-settings-grid">{(["partner_match","partner_development"] as const).map(id=><AgentEditor key={id} id={id} initial={settings.agents[id]} models={models} onSaved={setSettings}/>)}</div><AgentEditor id="processing" initial={settings.processing} models={models} onSaved={setSettings}/></>;
}
