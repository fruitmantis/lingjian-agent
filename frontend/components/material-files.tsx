"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, adminApiFetch } from "./auth-provider";
import { responseError } from "@/lib/api-request";
import contract from "../../shared/partner-materials.json";
import styles from "./material-files.module.css";

export type Material = {id:string;filename:string;file_type:string;processing_status:"processing"|"ready"|"empty"|"failed";processing_error?:string|null;preview_error?:string|null;doc_category?:string|null};
export const materialAccept=contract.formats.flatMap(f=>f.extensions).join(",");
export function validateMaterials(files:File[]) {
  if(files.some(f=>!contract.formats.some(t=>t.extensions.some(ext=>f.name.toLowerCase().endsWith(ext))))) throw new Error(contract.unsupported_message);
}
export async function uploadMaterials(endpoint:string,files:File[],initialize=false) {
  validateMaterials(files);
  for(const file of files){const body=new FormData();body.append("file",file);if(initialize)body.append("initialize_profile","true");const response=await adminApiFetch(endpoint,{method:"POST",body});if(!response.ok)throw await responseError(response);}
}
export function CaseCategory({value,onChange}:{value:string;onChange:(id:string)=>void}) {
  const parent=contract.categories.find(g=>g.children.some(c=>c.id===value));
  const [group,setGroup]=useState(parent?.id||"");
  useEffect(()=>{if(parent)setGroup(parent.id);},[parent]);
  return <div className={styles.categories}><label>一级分类<select required aria-label="一级分类" value={group} onChange={e=>{setGroup(e.target.value);onChange("");}}><option value="">请选择</option>{contract.categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>二级分类<select required aria-label="二级分类" value={value} onChange={e=>onChange(e.target.value)}><option value="">请选择</option>{contract.categories.find(c=>c.id===group)?.children.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></div>;
}
export function MaterialFiles({endpoint,admin=false,refresh=0,onChange,onProcessed,profileOnly=false,fileId,allowUpload=true}:{endpoint:string;admin?:boolean;refresh?:number;onChange?:()=>void;onProcessed?:()=>void;profileOnly?:boolean;fileId?:string;allowUpload?:boolean}) {
  const [rows,setRows]=useState<Material[]>([]),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  const [view,setView]=useState<{url?:string;text?:string;type:string;title:string}|null>(null);
  const callbacks=useRef({onChange,onProcessed});callbacks.current={onChange,onProcessed};
  const pending=useRef(false);const request=admin?adminApiFetch:apiFetch;
  const load=useCallback(async()=>{
    const r=await request(endpoint,{cache:"no-store"});if(!r.ok)throw await responseError(r);
    const all=await r.json() as Material[];const next=all.filter(f=>(!profileOnly||f.doc_category==='profile_import')&&(!fileId||f.id===fileId));setRows(next);
    const working=next.some(f=>f.processing_status==='processing');
    if(pending.current&&!working){pending.current=false;if(next.every(f=>f.processing_status!=='failed'))callbacks.current.onProcessed?.();callbacks.current.onChange?.();}
    if(working)pending.current=true;
  },[endpoint,request,profileOnly,fileId]);
  useEffect(()=>{void load().catch(e=>setError(e.message));},[load,refresh]);
  useEffect(()=>{if(!rows.some(f=>f.processing_status==='processing'))return;const timer=setInterval(()=>void load().catch(e=>setError(e.message)),1500);return()=>clearInterval(timer);},[rows,load]);
  useEffect(()=>()=>{if(view?.url)URL.revokeObjectURL(view.url);},[view]);
  async function action(fn:()=>Promise<void>,notify=true){if(busy)return;setBusy(true);setError("");try{await fn();await load();if(notify)callbacks.current.onChange?.();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function open(file:Material,download=false){
    await action(async()=>{const r=await request(`${endpoint}/${file.id}/${download?'file':'preview'}`,{cache:'no-store'});if(!r.ok)throw await responseError(r);const blob=await r.blob();if(download){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=file.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}else if(file.file_type==='txt')setView({text:await blob.text(),type:'txt',title:file.filename});else setView({url:URL.createObjectURL(blob),type:['pdf','docx','pptx'].includes(file.file_type)?'pdf':'html',title:file.filename});},false);
  }
  return <div className={styles.files}>
    {admin&&allowUpload&&<><p className="muted">{contract.upload_notice}</p><label className="upload-btn">上传文件<input type="file" hidden multiple accept={materialAccept} disabled={busy} onChange={e=>{const list=Array.from(e.target.files||[]);e.target.value='';if(list.length)void action(async()=>{await uploadMaterials(endpoint,list);pending.current=true;});}}/></label></>}
    {error&&<p role="alert" className="error-text">{error}</p>}
    {rows.map(file=><article key={file.id} className={styles.row}><div><strong>{file.filename}</strong>{admin&&<span className={styles.state}>{{processing:'处理中',ready:'已处理',empty:'无可提取文字',failed:'处理失败'}[file.processing_status]}</span>}</div>
      <div className={styles.actions}><button type="button" disabled={busy} className="secondary-btn" onClick={()=>void open(file)}>在线查看</button><button type="button" disabled={busy} className="secondary-btn" onClick={()=>void open(file,true)}>下载原件</button>{admin&&<>{!profileOnly&&<label className="secondary-btn">替换文件<input aria-label={`替换 ${file.filename}`} type="file" hidden accept={materialAccept} disabled={busy||file.processing_status==='processing'} onChange={e=>{const replacement=e.target.files?.[0];e.target.value='';if(replacement)void action(async()=>{validateMaterials([replacement]);const body=new FormData();body.append('file',replacement);const r=await request(`${endpoint}/${file.id}`,{method:'PUT',body});if(!r.ok)throw await responseError(r);pending.current=true;});}}/></label>}<button type="button" disabled={busy||file.processing_status==='processing'} className="secondary-btn" onClick={()=>void action(async()=>{const r=await request(`${endpoint}/${file.id}/retry`,{method:'POST'});if(!r.ok)throw await responseError(r);pending.current=true;})}>{file.processing_status==='failed'||file.preview_error?'重试':'重新解析'}</button><button type="button" disabled={busy} className="secondary-btn danger-outline" onClick={()=>{if(confirm('确定删除此文件？'))void action(async()=>{const r=await request(`${endpoint}/${file.id}`,{method:'DELETE'});if(!r.ok)throw await responseError(r);});}}>删除</button></>}</div>
      {admin&&file.processing_status==='empty'&&<p>{contract.empty_message}</p>}{admin&&file.processing_error&&<p role="status" className="error-text">{file.processing_error}</p>}{admin&&file.preview_error&&<p role="status">文字提取结果已保留。预览失败：{file.preview_error}</p>}
    </article>)}{!rows.length&&<p className="muted">暂无文件。</p>}
    {view&&<div className={styles.overlay} onClick={()=>setView(null)}><section role="dialog" aria-modal="true" aria-label={view.title} className={styles.viewer} onClick={e=>e.stopPropagation()}><header><strong>{view.title}</strong><button className="secondary-btn" onClick={()=>setView(null)}>关闭</button></header>{view.type==='txt'?<pre>{view.text}</pre>:view.type==='pdf'?<object data={view.url} type="application/pdf" aria-label="文档预览"><p>浏览器未能预览，请下载原件查看。</p></object>:<iframe sandbox="" referrerPolicy="no-referrer" src={view.url} title="文档预览"/>}</section></div>}
  </div>;
}
