"use client";
import Link from "next/link";
import {FormEvent,use,useCallback,useEffect,useRef,useState} from "react";
import {adminApiFetch as apiFetch} from "@/components/auth-provider";
import {ClassificationFields,ClassificationNotice} from "@/components/business-taxonomy";
import {MaterialFiles,uploadMaterials} from "@/components/material-files";
import {PartnerProfileReport} from "@/components/partner-profile-report";
import {responseError} from "@/lib/api-request";

type Partner={id:string;name:string;intro:string|null;capabilities:string|null;industries:string|null;service_areas:string|null;ai_profile:string|null;profile_needs_update:boolean;profile_status:string;profile_sources?:{source_kind:string;source_id:string;state:string;error?:string}[];classification_pending?:Record<string,string[]>};
const capabilityNames=(value:string)=>value.split(/[,，;；\n]+/).map(name=>name.trim()).filter(Boolean);
async function request(path:string,method='GET',body?:unknown){const r=await apiFetch(path,{method,headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined,cache:'no-store'});if(!r.ok)throw await responseError(r);return r.status===204?null:r.json();}

export default function AdminPartnerDetailPage({params}:{params:Promise<{id:string}>}){
  const {id}=use(params);const [partner,setPartner]=useState<Partner|null>(null);
  const [form,setForm]=useState<Record<string,string>>({}),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [refresh,setRefresh]=useState(0);
  const [tags,setTags]=useState<string[]>([]),[tagError,setTagError]=useState('');
  const initial=useRef(false),importing=useRef(false);
  const load=useCallback(async()=>{const p=await request(`/partners/${id}`);setPartner(p);if(!initial.current){setForm({name:p.name,capabilities:p.capabilities||'',industries:p.industries||'',service_areas:p.service_areas||''});initial.current=true;}},[id]);
  useEffect(()=>{initial.current=false;void load().catch(e=>setError(e.message));},[load]);
  const loadTags=useCallback(async()=>{setTagError('');try{const items:{name:string;enabled:boolean}[]=await request('/admin/capability-tags');setTags(items.filter(tag=>tag.enabled).map(tag=>tag.name));}catch{setTagError('可选能力标签加载失败，已有标签仍可维护。');}},[]);
  useEffect(()=>{void loadTags();},[loadTags]);
  useEffect(()=>{if(!partner||!['pending','processing'].includes(partner.profile_status))return;const timer=setInterval(()=>void load().catch(()=>{}),1500);return()=>clearInterval(timer);},[partner?.profile_status,load]);
  const selectedCapabilities=capabilityNames(form.capabilities||'');
  const capabilityOptions=[...new Set([...capabilityNames(partner?.capabilities||''),...tags,...selectedCapabilities])];
  async function action(fn:()=>Promise<void>){if(busy)return;setBusy(true);setError('');setNotice('');try{await fn();await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  function changed(){void load().catch(e=>setError(e.message));}
  function processed(){changed();if(importing.current){importing.current=false;setNotice('文件处理已结束，请查看当前画像和处理结果。');}}
  async function updateProfile(){await action(async()=>{await request(`/partners/${id}/profile`,'POST');setNotice('来源处理已结束，请查看画像及来源状态。');});}
  async function save(e:FormEvent){e.preventDefault();await action(async()=>{await request(`/partners/${id}`,'PUT',form);setNotice('伙伴信息已保存。');});}
  return <main className="page"><div className="page-heading-row"><div><p className="eyebrow">Partner</p><h1>{partner?.name||'伙伴资料'}</h1><p className="lead">维护伙伴基本信息与画像。案例资料在统一页面管理。</p></div><Link href="/admin/partners" className="secondary-btn">返回伙伴列表</Link></div>
    {error&&<p role="alert" className="error-text">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {partner&&<><section className="card"><h2>基础信息</h2><form onSubmit={save} className="form-grid"><label className="form-row">伙伴名称<input required value={form.name||''} onChange={e=>setForm(f=>({...f,name:e.target.value}))}/></label><ClassificationFields industries={form.industries||''} regions={form.service_areas||''} onIndustries={industries=>setForm(f=>({...f,industries}))} onRegions={service_areas=>setForm(f=>({...f,service_areas}))}/><div className="form-span-two"><ClassificationNotice pending={partner.classification_pending}/></div>
      <fieldset className="classification-options partner-capability-options form-span-two" disabled={busy}>
        <legend>能力标签（多选）</legend>
        <div className="capability-choice-list">{capabilityOptions.map(name=><label key={name}><input type="checkbox" checked={selectedCapabilities.includes(name)} onChange={e=>setForm(f=>({...f,capabilities:(e.target.checked?[...new Set([...capabilityNames(f.capabilities||''),name])]:capabilityNames(f.capabilities||'').filter(value=>value!==name)).join(',')}))}/><span>{name}</span></label>)}</div>
        {tagError&&<p className="error-text" role="alert">{tagError} <button type="button" className="secondary-btn" onClick={()=>void loadTags()}>重试</button></p>}
        <p className="muted">已选 {selectedCapabilities.length} 项；新增可选标签请前往<Link href="/admin/tags">能力标签管理</Link>。</p>
      </fieldset>
<div className="form-span-two"><button disabled={busy}>保存伙伴信息</button></div></form></section>
    <section className="card"><div className="section-heading-row"><div><h2>案例与资料</h2><p className="muted">查看、上传和整理该伙伴的资料。</p></div><Link href={`/admin/partner-materials?partner_id=${encodeURIComponent(id)}`} className="secondary-btn">管理资料</Link></div></section>
    <section className="card" id="profile"><div className="section-heading-row"><div><h2>伙伴画像</h2>{partner.profile_needs_update&&<p className="muted">资料正在更新或处理未完成，当前画像仅含有效来源。</p>}</div><div className="table-actions"><label className="upload-btn">导入 DOCX 画像<input type="file" hidden accept=".docx" disabled={busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void action(async()=>{if(!file.name.toLowerCase().endsWith('.docx'))throw new Error('初始化画像请上传 DOCX 文件');importing.current=true;await uploadMaterials(`/partners/${id}/documents`,[file],true);setRefresh(n=>n+1);setNotice('画像文件已保存，提取成功后直接采用，不调用 AI 重写。');});}}/></label><button disabled={busy} onClick={()=>void updateProfile()}>{busy?'处理中…':'更新伙伴画像'}</button></div></div><p className="muted">导入按十章整理标题和表格；资料处理后自动更新相关章节；删除资料会撤回其贡献。十章画像向普通用户展示，未展示来源信息仅管理员可见。</p>{partner.ai_profile?<PartnerProfileReport text={partner.ai_profile}/>:<p className="placeholder-text">暂无画像，可导入 DOCX 或手动更新。</p>}<details style={{marginTop:24}}><summary>来源处理状态</summary>{partner.profile_sources?.map(source=><p key={source.source_kind+source.source_id}>{source.source_kind}：{source.source_id} — {source.state}{source.error&&<span className="error-text"> · {source.error}</span>}</p>)}</details><details style={{marginTop:24}}><summary>画像原件</summary><MaterialFiles endpoint={`/partners/${id}/documents`} admin profileOnly allowUpload={false} refresh={refresh} onChange={changed} onProcessed={processed}/></details></section>
    </>}
  </main>;
}
