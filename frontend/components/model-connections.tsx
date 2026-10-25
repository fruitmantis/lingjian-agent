"use client";
import {useEffect,useState} from "react";
import {adminApiFetch} from "./auth-provider";
import {responseError} from "../lib/api-request";
import {AgentManagement} from "./agent-settings";
import styles from "./model-connections.module.css";
type Provider={id:string;name:string;baseUrl:string|null;protocol:string;apiKeyConfigured:boolean;apiKeySource:string|null;modelCount:number;updatedAt:string};
type Model={id:string;providerId:string;providerName:string;name:string;modelName:string|null;temperature:number;topP:number;maxTokens:number;enabled:boolean;userSelectable:boolean;defaultBindings:string[];updatedAt:string};
type ProviderDraft={name:string;baseUrl:string;apiKey:string};
type ModelDraft={name:string;modelName:string;temperature:number;topP:number;maxTokens:number;enabled:boolean;userSelectable:boolean};
type Result={success:boolean;message:string;latencyMs?:number;at:number;signature:string};
const bindingNames:Record<string,string>={partner_match:"找伙伴默认",partner_development:"促发展默认",processing:"基础处理默认"};
const modelDraft=(m?:Model):ModelDraft=>({name:m?.name||"",modelName:m?.modelName||"",temperature:m?.temperature??0.2,topP:m?.topP??1,maxTokens:m?.maxTokens??131072,enabled:m?.enabled??true,userSelectable:m?.userSelectable??false});
const providerDraft=(p?:Provider):ProviderDraft=>({name:p?.name||"",baseUrl:p?.baseUrl||"",apiKey:""});
async function request<T>(path:string,method="GET",body?:unknown):Promise<T>{
 const response=await adminApiFetch(path,{method,cache:"no-store",...(body?{headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{})});
 if(!response.ok)throw await responseError(response);
 return response.status===204?undefined as T:response.json();
}
export function ModelConfiguration(){
 const [providers,setProviders]=useState<Provider[]>([]),[models,setModels]=useState<Model[]>([]),[loading,setLoading]=useState(true);
 const [tab,setTab]=useState<"settings"|"providers">("settings"),[selected,setSelected]=useState<string|null>(null);
 const [mode,setMode]=useState<"overview"|"provider"|"add-provider"|"model">("overview"),[editing,setEditing]=useState<string|null>(null);
 const [pd,setPd]=useState<ProviderDraft>(providerDraft()),[md,setMd]=useState<ModelDraft>(modelDraft()),[replaceKey,setReplaceKey]=useState(false);
 const [saving,setSaving]=useState(false),[testing,setTesting]=useState<string|null>(null),[tests,setTests]=useState<Record<string,Result>>({});
 const [error,setError]=useState(""),[notice,setNotice]=useState("");
 const provider=mode==="add-provider"?undefined:providers.find(p=>p.id===selected),model=models.find(m=>m.id===editing),owned=models.filter(m=>m.providerId===provider?.id);
 const busy=saving||!!testing;
 const dirty=(mode==="provider"||mode==="add-provider")?JSON.stringify(pd)!==JSON.stringify(providerDraft(provider)):mode==="model"?JSON.stringify(md)!==JSON.stringify(modelDraft(model)):false;
 const signature=(m:Model)=>JSON.stringify([modelDraft(m),providers.find(p=>p.id===m.providerId)?.updatedAt]);
 async function load(){
  setError("");try{const [ps,ms]=await Promise.all([request<Provider[]>("/admin/model-providers"),request<Model[]>("/admin/model-configs")]);setProviders(ps);setModels(ms);setSelected(old=>ps.some(p=>p.id===old)?old:ps[0]?.id||null);}
  catch(e){setError(e instanceof Error?e.message:"模型提供商加载失败");}finally{setLoading(false);}
 }
 useEffect(()=>{void load();},[]);
 function select(id:string){setSelected(id);setMode("overview");setEditing(null);setError("");setNotice("");}
 function editProvider(add=false){setPd(providerDraft(add?undefined:provider));setReplaceKey(add||!provider?.apiKeyConfigured);setMode(add?"add-provider":"provider");setError("");setNotice("");}
 function editModel(m?:Model){setEditing(m?.id||null);setMd(modelDraft(m));setMode("model");setError("");setNotice("");}
 async function saveProvider(){
  if(busy)return;setSaving(true);setError("");setNotice("");
  try{const saved=await request<Provider>("/admin/model-providers"+(provider?"/"+provider.id:""),provider?"PUT":"POST",{name:pd.name,baseUrl:pd.baseUrl,apiKey:pd.apiKey||undefined});setProviders(old=>[...old.filter(p=>p.id!==saved.id),saved]);setSelected(saved.id);setPd(providerDraft(saved));setReplaceKey(false);setMode("overview");setNotice("提供商已保存");}
  catch(e){setError(e instanceof Error?e.message:"提供商保存失败");}finally{setSaving(false);}
 }
 async function saveModel(){
  if(!provider||busy)return;setSaving(true);setError("");setNotice("");
  try{const saved=await request<Model>("/admin/model-configs"+(model?"/"+model.id:""),model?"PUT":"POST",{...md,providerId:provider.id});setModels(old=>[...old.filter(m=>m.id!==saved.id),saved]);setEditing(saved.id);setMd(modelDraft(saved));setNotice("模型已保存");}
  catch(e){setError(e instanceof Error?e.message:"模型保存失败");}finally{setSaving(false);}
 }
 async function testSaved(m:Model){
  if(busy||(mode==="model"&&dirty))return;setTesting(m.id);setError("");
  try{const res=await request<Omit<Result,"at"|"signature">>("/admin/model-configs/"+m.id+"/test","POST");setTests(old=>({...old,[m.id]:{...res,at:Date.now(),signature:signature(m)}}));}
  catch(e){setTests(old=>({...old,[m.id]:{success:false,message:e instanceof Error?e.message:"测试失败",at:Date.now(),signature:signature(m)}}));}finally{setTesting(null);}
 }
 async function remove(kind:"provider"|"model"){
  const item=kind==="provider"?provider:model;if(!item||busy)return;
  if(!window.confirm(kind==="provider"?"确定删除提供商“"+item.name+"”？":"确定删除模型“"+item.name+"”？任务和历史结果保留。引用该模型的智能体将无法发起模型调用，请先更换其模型选择。"))return;
  setSaving(true);setError("");
  try{await request("/admin/"+(kind==="provider"?"model-providers":"model-configs")+"/"+item.id,"DELETE");
   if(kind==="provider"){setProviders(old=>old.filter(p=>p.id!==item.id));setSelected(providers.find(p=>p.id!==item.id)?.id||null);}
   else setModels(old=>old.filter(m=>m.id!==item.id));setMode("overview");setEditing(null);setNotice("已删除");
  }catch(e){setError(e instanceof Error?e.message:"删除失败");}finally{setSaving(false);}
 }
 function result(m?:Model){
  const res=m?tests[m.id]:undefined,changed=!!res&&(res.signature!==signature(m!)||(mode==="model"&&editing===m?.id&&dirty));
  return <div className={styles.result} role="status"><span className={res&&!changed?(res.success?styles.pass:styles.fail):""}>{!res?"尚未测试":changed?"配置已变更":res.success?"本次测试通过":"本次测试失败"}</span>{res&&!changed&&<small>{new Date(res.at).toLocaleString("zh-CN")}{res.latencyMs!=null?" · "+res.latencyMs+" ms":""}{!res.success?" · "+res.message:""}</small>}</div>;
 }
 if(loading)return <p role="status">正在读取模型配置…</p>;
 return <div className={styles.root}>
  <nav className={styles.tabs} role="tablist" aria-label="智能体管理">
   <button role="tab" aria-selected={tab==="settings"} onClick={()=>setTab("settings")}>智能体设置</button>
   <button role="tab" aria-selected={tab==="providers"} onClick={()=>{setTab("providers");void load();}}>模型提供商</button>
   {tab==="providers"&&<button className={styles.add} disabled={busy} onClick={()=>editProvider(true)}>＋ 添加提供商</button>}
  </nav>
  {error&&<p role="alert" className="error-text">{error} <button className="secondary-btn" onClick={()=>void load()}>重新读取</button></p>}{notice&&<p role="status">{notice}</p>}
  <div hidden={tab!=="settings"} role="tabpanel" aria-label="智能体设置"><AgentManagement models={models}/></div>
  <section hidden={tab!=="providers"} role="tabpanel" aria-label="模型提供商" className={styles.panel}>
   <aside className={styles.list}><div className={styles.count}>模型提供商 <span>{providers.length}</span></div>
    {providers.map(p=><button key={p.id} className={styles.item+" "+(selected===p.id?styles.active:"")} aria-pressed={selected===p.id} disabled={busy} onClick={()=>select(p.id)}>
     <span className={styles.providerIcon} aria-hidden="true">{p.name.slice(0,1).toUpperCase()}</span><span><strong>{p.name}</strong><small>{models.filter(m=>m.providerId===p.id).length} 个模型</small></span>
    </button>)}
    {!providers.length&&<p className="muted">暂无模型提供商。</p>}
   </aside>
   {(mode==="provider"||mode==="add-provider")?<form className={styles.editor} onSubmit={e=>{e.preventDefault();void saveProvider();}}>
    <div className={styles.breadcrumb}>{provider?.name||"新提供商"} <span>/ 连接配置</span></div>
    <div className={styles.heading}><div><h2>{provider?"编辑提供商":"添加提供商"}</h2><p>此连接由提供商下的模型共用</p></div></div>
    <div className={styles.fields}><label>提供商名称<input required maxLength={120} value={pd.name} onChange={e=>setPd({...pd,name:e.target.value})}/></label><label>API 协议<input readOnly value="OpenAI Chat Completions"/></label></div>
    <label className={styles.field}>API 地址<input type="url" required value={pd.baseUrl} placeholder="https://…/v1" onChange={e=>setPd({...pd,baseUrl:e.target.value})}/><small>填写基础地址，不包含 /chat/completions</small></label>
    <label className={styles.credentialLabel}>API Key</label><div className={styles.credential}>{provider?.apiKeyConfigured&&!replaceKey?<><span>♧ 已保存凭据{provider.apiKeySource==="env"?"（环境变量）":""}</span><button type="button" onClick={()=>setReplaceKey(true)}>更换</button></>:<input aria-label="替换 API Key" type="password" autoComplete="new-password" value={pd.apiKey} placeholder={provider?.apiKeyConfigured?"留空保留原凭据":"输入此提供商的 API Key"} onChange={e=>setPd({...pd,apiKey:e.target.value})}/>}</div>
    <footer className={styles.footer}><small className={styles.usedBy}>{owned.length?"用于 "+owned.map(m=>m.name).join("、"):"尚未添加模型"}</small><div className={styles.buttons}>{provider&&<button type="button" className="secondary-btn danger-outline" disabled={busy} onClick={()=>void remove("provider")}>删除提供商</button>}<button type="button" className="secondary-btn" disabled={busy} onClick={()=>setMode("overview")}>取消</button><button type="submit" disabled={busy||!pd.name.trim()||!pd.baseUrl.trim()}>{saving?"保存中…":"保存提供商"}</button></div></footer>
   </form>:mode==="model"&&provider?<form className={styles.editor} onSubmit={e=>{e.preventDefault();void saveModel();}}>
    <div className={styles.breadcrumb}>{provider.name} <span>/ 模型配置</span></div>
    <div className={styles.heading}><h2>{model?"编辑模型":"添加模型"}</h2><label className={styles.toggle}>{md.enabled?"已启用":"已停用"}<input aria-label="启用模型" type="checkbox" checked={md.enabled} onChange={e=>setMd({...md,enabled:e.target.checked})}/></label></div>
    <div className={styles.fields}><label>显示名称<input required maxLength={120} value={md.name} onChange={e=>setMd({...md,name:e.target.value})}/></label><label>模型 ID<input required value={md.modelName} onChange={e=>setMd({...md,modelName:e.target.value})}/></label></div>
    <div className={styles.usage}><label className={styles.toggle}><span>允许用户手动选择<small>在找伙伴、促发展输入框的模型菜单中提供</small></span><input type="checkbox" checked={md.userSelectable} onChange={e=>setMd({...md,userSelectable:e.target.checked})}/></label>
     <div className={styles.binding}><span>默认绑定</span><span>{model?.defaultBindings?.map(id=><em key={id}>{bindingNames[id]||id}</em>)}<button type="button" onClick={()=>setTab("settings")}>管理绑定 →</button></span></div></div>
    <details className={styles.advanced}><summary>高级参数 <span>温度 · Top P · 最大输出</span></summary><div className={styles.fields}><label>temperature<input type="number" min={0} step="any" value={md.temperature} onChange={e=>setMd({...md,temperature:Number(e.target.value)})}/></label><label>top_p<input type="number" min={0} max={1} step="any" value={md.topP} onChange={e=>setMd({...md,topP:Number(e.target.value)})}/></label><label>max_tokens<input type="number" min={1} step={1} value={md.maxTokens} onChange={e=>setMd({...md,maxTokens:Number(e.target.value)})}/></label></div></details>
    <footer className={styles.footer}>{result(model)}<div className={styles.buttons}>{model&&<button type="button" className="secondary-btn danger-outline" disabled={busy} onClick={()=>void remove("model")}>删除模型</button>}<button type="button" className="secondary-btn" disabled={!model||dirty||busy} title={dirty?"请先保存模型，再测试已保存的连接":undefined} onClick={()=>model&&void testSaved(model)}>{testing===editing?"测试中…":"测试连接"}</button><button type="button" className="secondary-btn" disabled={busy} onClick={()=>setMode("overview")}>取消</button><button type="submit" disabled={busy||!md.name.trim()||!md.modelName.trim()}>{saving?"保存中…":"保存模型"}</button></div></footer>
   </form>:provider?<div className={styles.editor}>
    <div className={styles.heading}><div><h2>{provider.name}</h2><p>共享连接配置 · {owned.length} 个模型</p></div><button className="secondary-btn" disabled={busy} onClick={()=>editProvider()}>编辑提供商</button></div>
    <div className={styles.connectionInfo}><div><small>API 地址</small><code>{provider.baseUrl||"未设置"}</code></div><div><small>协议与凭据</small><span>OpenAI Chat Completions</span><small>♧ {provider.apiKeyConfigured?"已配置":"未配置凭据"}</small></div></div>
    <div className={styles.modelHeading}><h3>模型 <span>{owned.length}</span></h3><button disabled={busy} onClick={()=>editModel()}>＋ 添加模型</button></div>
    <div className={styles.modelList}>{owned.map(m=><article key={m.id} className={styles.modelRow} aria-label={m.name}>
     <div><strong>{m.name}</strong><em className={styles.enabled}>{m.enabled?"已启用":"已停用"}</em><code>{m.modelName}</code><div className={styles.tags}>{m.userSelectable&&<span>✓ 用户可选</span>}{m.defaultBindings?.map(id=><em key={id}>{bindingNames[id]||id}</em>)}</div></div>
     <div className={styles.modelActions}><div><button disabled={busy} onClick={()=>void testSaved(m)}>{testing===m.id?"测试中…":"测试"}</button><button disabled={busy} onClick={()=>editModel(m)}>编辑</button></div>{result(m)}</div>
    </article>)}{!owned.length&&<p className="muted">尚未添加模型。</p>}</div>
    <footer className={styles.overviewFooter}><span>默认模型在智能体设置中管理</span><button onClick={()=>setTab("settings")}>智能体设置 →</button></footer>
   </div>:<div className={styles.empty}><p>选择提供商，或添加一个模型提供商。</p><button onClick={()=>editProvider(true)}>添加提供商</button></div>}
  </section>
 </div>;
}
