"use client";
import {useEffect,useState} from "react";
import {adminApiFetch} from "./auth-provider";
import {responseError} from "../lib/api-request";
import {AgentManagement} from "./agent-settings";
import styles from "./model-connections.module.css";
type Connection={id:string;name:string;provider:string|null;baseUrl:string|null;modelName:string|null;temperature:number;topP:number;maxTokens:number;enabled:boolean;userSelectable:boolean;defaultBindings?:string[];apiKeyConfigured:boolean;apiKeySource:string|null;updatedAt:string};
type Editor=Omit<Connection,"id"|"updatedAt">&{apiKey:string};
type Test={success:boolean;message:string;latencyMs?:number;at:number;changed?:boolean};
const bindingNames:Record<string,string>={partner_match:"找伙伴默认",partner_development:"促发展默认",processing:"基础处理默认"};
const editor=(c:Connection):Editor=>({...c,userSelectable:!!c.userSelectable,apiKey:""});
const signature=(c:Editor|Connection)=>JSON.stringify([c.name,c.provider,c.baseUrl,c.modelName,c.temperature,c.topP,c.maxTokens,c.enabled,c.userSelectable]);
const blank=():Editor=>({name:"",provider:"OpenAI Compatible",baseUrl:"",modelName:"",apiKey:"",temperature:0.2,topP:1,maxTokens:131072,enabled:true,userSelectable:false,defaultBindings:[],apiKeyConfigured:false,apiKeySource:"db"});
export function ModelConfiguration(){
 const [configs,setConfigs]=useState<Connection[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(""),[tab,setTab]=useState<"settings"|"connections">("settings");
 const [selected,setSelected]=useState<string|null>(null),[draft,setDraft]=useState<Editor|null>(null),[q,setQ]=useState(""),[saving,setSaving]=useState(false),[testing,setTesting]=useState<string|null>(null),[tests,setTests]=useState<Record<string,Test>>({}),[replaceKey,setReplaceKey]=useState(false),[notice,setNotice]=useState("");
 async function load(){setError("");try{const response=await adminApiFetch("/admin/model-configs",{cache:"no-store"});if(!response.ok)throw await responseError(response);const list:Connection[]=await response.json();setConfigs(list);if(!draft&&list.length){setSelected(list[0].id);setDraft(editor(list[0]));}}catch(e){setError(e instanceof Error?e.message:"模型配置加载失败");}finally{setLoading(false);}}
 useEffect(()=>{void load();},[]);
 const connection=configs.find(c=>c.id===selected),dirty=!!draft&&(!connection||signature(draft)!==signature(connection)||!!draft.apiKey);
 function select(c:Connection){setSelected(c.id);setDraft(editor(c));setReplaceKey(false);setError("");setNotice("");}
 function change(values:Partial<Editor>){setDraft(old=>old?{...old,...values}:old);setNotice("");}
 function newConnection(){setSelected(null);setDraft(blank());setReplaceKey(true);setNotice("");setTab("connections");}
 async function save(){
  if(!draft||saving||testing)return;setSaving(true);setError("");setNotice("");
  try{
   const response=await adminApiFetch(`/admin/model-configs${selected?`/${selected}`:""}`,{method:selected?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:draft.name,provider:draft.provider,baseUrl:draft.baseUrl||undefined,modelName:draft.modelName||undefined,apiKey:draft.apiKey||undefined,temperature:draft.temperature,topP:draft.topP,maxTokens:draft.maxTokens,enabled:draft.enabled,userSelectable:draft.userSelectable})});
   if(!response.ok)throw await responseError(response,"保存失败");const saved:Connection=await response.json();setConfigs(old=>[...old.filter(c=>c.id!==saved.id),saved]);setSelected(saved.id);setDraft(editor(saved));setReplaceKey(false);if(dirty)setTests(old=>old[saved.id]?{...old,[saved.id]:{...old[saved.id],changed:true}}:old);setNotice("配置已保存");
  }catch(e){setError(e instanceof Error?e.message:"配置保存失败");}finally{setSaving(false);}
 }
 async function testSaved(){
  if(!connection||dirty||testing||saving)return;const id=connection.id;setTesting(id);setError("");
  try{const response=await adminApiFetch(`/admin/model-configs/${id}/test`,{method:"POST"});if(!response.ok)throw await responseError(response,"连接测试失败");const result=await response.json();setTests(old=>({...old,[id]:{...result,at:Date.now(),changed:false}}));}
  catch(e){setTests(old=>({...old,[id]:{success:false,message:e instanceof Error?e.message:"测试失败",at:Date.now()}}));}finally{setTesting(null);}
 }
 async function remove(){
  if(!connection||saving||testing)return;
  if(!window.confirm(`确定删除模型配置“${connection.name}”？删除后无法恢复，任务和历史结果保留。引用该连接的智能体将无法发起模型调用，请先更换其模型选择。`))return;
  setSaving(true);setError("");try{const response=await adminApiFetch(`/admin/model-configs/${connection.id}`,{method:"DELETE"});if(!response.ok)throw await responseError(response);const next=configs.filter(c=>c.id!==connection.id);setConfigs(next);if(next[0])select(next[0]);else{setSelected(null);setDraft(null);}}catch(e){setError(e instanceof Error?e.message:"删除失败");}finally{setSaving(false);}
 }
 const result=selected?tests[selected]:undefined,changed=!!result&&(!!result.changed||dirty),status=!result?"尚未测试":changed?"配置已变更":result.success?"本次测试通过":"本次测试失败";
 if(loading)return <p role="status">正在读取模型配置…</p>;
 return <div className={styles.root}>
  <nav className={styles.tabs} role="tablist" aria-label="智能体管理"><button role="tab" aria-selected={tab==="settings"} onClick={()=>setTab("settings")}>智能体设置</button><button role="tab" aria-selected={tab==="connections"} onClick={()=>{setTab("connections");void load();}}>模型连接</button>{tab==="connections"&&<button className={styles.add} onClick={newConnection} disabled={saving||!!testing}>＋ 新增连接</button>}</nav>
  {error&&<p role="alert" className="error-text">{error}</p>}{notice&&<p role="status">{notice}</p>}
  <div hidden={tab!=="settings"} role="tabpanel" aria-label="智能体设置"><AgentManagement models={configs}/></div>
  <section hidden={tab!=="connections"} role="tabpanel" aria-label="模型连接" className={styles.panel}>
   <aside className={styles.list}><div className={styles.count}>全部连接 <span>{configs.length}</span></div><label className={styles.search}><span className="sr-only">搜索名称或模型 ID</span><input aria-label="搜索名称或模型 ID" placeholder="搜索名称或模型 ID" value={q} onChange={e=>setQ(e.target.value)}/></label>
    {configs.filter(c=>`${c.name} ${c.modelName||""}`.toLowerCase().includes(q.toLowerCase())).map(c=><button key={c.id} type="button" className={`${styles.item} ${selected===c.id?styles.active:""}`} aria-pressed={selected===c.id} onClick={()=>select(c)}><span className={styles.itemHeading}><strong>{c.name}</strong><small>{c.enabled?"• 启用":"• 停用"}</small></span><span className={styles.technical}>{c.modelName||"未设置模型 ID"}</span><span className={styles.itemMeta}><span>{c.defaultBindings?.length?c.defaultBindings.map(id=><em key={id}>{bindingNames[id]||id}</em>):"未绑定默认"}</span><small>{c.userSelectable?"可选":"不开放选择"}</small></span></button>)}
    {!configs.length&&<p className="muted">暂无模型连接。</p>}
   </aside>
   {draft?<form className={styles.editor} onSubmit={e=>{e.preventDefault();void save();}}>
    <div className={styles.heading}><h2>连接配置</h2><label className={styles.toggle}><input type="checkbox" checked={draft.enabled} onChange={e=>change({enabled:e.target.checked})}/>{draft.enabled?"已启用":"已停用"}</label></div>
    <div className={styles.fields}><label>名称<input required maxLength={120} value={draft.name} onChange={e=>change({name:e.target.value})}/></label><label>模型 ID<input required={!selected} value={draft.modelName||""} onChange={e=>change({modelName:e.target.value})}/></label></div>
    <div className={`${styles.fields} ${styles.endpoint}`}><label>服务商<input value={draft.provider||""} onChange={e=>change({provider:e.target.value})}/></label><label><span className={styles.fieldCaption}>API 地址 <small>OpenAI 兼容</small></span><input type="url" required={!selected} value={draft.baseUrl||""} placeholder="https://…/v1" onChange={e=>change({baseUrl:e.target.value})}/></label></div>
    <label className={styles.credentialLabel}>API Key</label><div className={styles.credential}>{draft.apiKeyConfigured&&!replaceKey?<><span>♧ 已保存凭据{draft.apiKeySource==="env"?"（环境变量）":""}</span><button type="button" onClick={()=>setReplaceKey(true)}>更换</button></>:<input aria-label="替换 API Key" type="password" autoComplete="new-password" value={draft.apiKey} placeholder={draft.apiKeyConfigured?"留空保留原凭据":"输入此连接的 API Key"} onChange={e=>change({apiKey:e.target.value})}/>}</div>
    <div className={styles.usage}><label className={styles.toggle}>允许用户手动选择<input type="checkbox" checked={draft.userSelectable} onChange={e=>change({userSelectable:e.target.checked})}/></label><div className={styles.binding}><span>默认绑定</span><span>{connection?.defaultBindings?.map(id=><em key={id}>{bindingNames[id]||id}</em>)}<button type="button" onClick={()=>setTab("settings")}>管理绑定 →</button></span></div></div>
    <details className={styles.advanced}><summary>高级参数</summary><div className={styles.fields}><label>temperature<input type="number" min={0} step="any" value={draft.temperature} onChange={e=>change({temperature:Number(e.target.value)})}/></label><label>top_p<input type="number" min={0} max={1} step="any" value={draft.topP} onChange={e=>change({topP:Number(e.target.value)})}/></label><label>max_tokens<input type="number" min={1} step={1} value={draft.maxTokens} onChange={e=>change({maxTokens:Number(e.target.value)})}/></label></div></details>
    <footer className={styles.footer}><div className={styles.result} role="status"><span className={!changed&&result?(result.success?styles.pass:styles.fail):""}>{status}</span>{result&&!changed&&<small>{new Date(result.at).toLocaleString("zh-CN")} {result.latencyMs!=null?`· ${result.latencyMs} ms`:""}{!result.success?` · ${result.message}`:""}</small>}</div><div className={styles.buttons}>{selected&&<button type="button" className="secondary-btn danger-outline" disabled={saving||!!testing} onClick={()=>void remove()}>删除</button>}<button type="button" className="secondary-btn" disabled={!selected||dirty||saving||!!testing} title={dirty?"请先保存配置，再测试已保存的连接":undefined} onClick={()=>void testSaved()}>{testing===selected?"测试中…":"测试连接"}</button><button type="submit" disabled={saving||!!testing||!draft.name.trim()||(!selected&&!draft.baseUrl?.trim())}>{saving?"保存中…":"保存配置"}</button></div></footer>
   </form>:<div className={styles.empty}><p>选择连接，或新增一个模型连接。</p><button onClick={newConnection}>新增连接</button></div>}
  </section>
 </div>;
}
