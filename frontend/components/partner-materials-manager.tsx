"use client";
import Link from 'next/link';
import {CardEntryLabel} from './card-entry';
import {FormEvent,useCallback,useEffect,useRef,useState} from 'react';
import {useRouter,useSearchParams} from 'next/navigation';
import {adminApiFetch} from './auth-provider';
import {CaseCategory,MaterialFiles,materialAccept,uploadMaterials,validateMaterials} from './material-files';
import {Pagination} from './pagination';
import {PartnerSelect} from './partner-select';
import {UiIcon} from './ui-icons';
import {responseError} from '@/lib/api-request';
import contract from '../../shared/partner-materials.json';
import styles from './partner-materials-manager.module.css';

type Partner={id:string;name:string};
type Entry={kind:'case'|'document';id:string;partner_id:string;partner_name:string;title:string;description:string|null;category_id:string|null;visible:boolean;file_count:number;processing_status:string;updated_at:string;profile_needs_update:boolean};
type Catalogue={items:Entry[];total:number;partners:Partner[]};
const states:Record<string,string>={processing:'处理中',ready:'已处理',failed:'处理异常',empty:'无可提取文字',no_files:'暂无文件'};
const categoryName=(id:string|null)=>contract.categories.flatMap(g=>g.children).find(c=>c.id===id)?.name||'待分类';
async function request(path:string,method='GET',body?:unknown){
  const r=await adminApiFetch(path,{method,headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined,cache:'no-store'});
  if(!r.ok)throw await responseError(r);return r.status===204?null:r.json();
}

export function PartnerMaterialsManager(){
  const params=useSearchParams(),router=useRouter();
  const partnerId=params.get('partner_id')||'',group=params.get('category_group')||'',category=params.get('category_id')||'';
  const page=Math.max(1,Number(params.get('page'))||1),query=params.toString(),savedQuery=params.get('q')||'';
  const [data,setData]=useState<Catalogue>({items:[],total:0,partners:[]}),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [q,setQ]=useState(params.get('q')||''),[revision,setRevision]=useState(0);
  const [selected,setSelected]=useState<Entry|null>(null),[creating,setCreating]=useState(false),[notice,setNotice]=useState<Partner|null>(null);
  const refresh=useCallback(()=>setRevision(n=>n+1),[]);
  useEffect(()=>setQ(savedQuery),[savedQuery]);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');
    const search=new URLSearchParams(query);search.set('page_size','12');
    void adminApiFetch('/admin/partner-materials?'+search,{cache:'no-store',signal:controller.signal})
      .then(async r=>{if(!r.ok)throw await responseError(r);return r.json();})
      .then(result=>{if(!controller.signal.aborted)setData(result);})
      .catch(e=>{if(!controller.signal.aborted)setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[query,revision]);
  useEffect(()=>{if(!data.items.some(e=>e.processing_status==='processing'))return;const timer=setInterval(refresh,2000);return()=>clearInterval(timer);},[data.items,refresh]);
  function filter(updates:Record<string,string|null>){
    const next=new URLSearchParams(params.toString());next.delete('page');
    for(const [key,value] of Object.entries(updates)){if(value)next.set(key,value);else next.delete(key);}
    router.replace('/admin/partner-materials'+(next.size?'?'+next:''),{scroll:false});
  }
  function changed(entry:Entry){refresh();setNotice({id:entry.partner_id,name:entry.partner_name});}
  const current=data.partners.find(p=>p.id===partnerId);
  const groups=[...contract.categories.map(g=>({id:g.id,name:g.name,ids:g.children.map(c=>c.id) as string[]})),{id:'unclassified',name:'待分类资料',ids:[] as string[]}];
  return <main className="page">
    <div className="page-heading-row"><div><p className="eyebrow">Partner Materials</p><h1>伙伴资料</h1><p className="lead">集中维护伙伴案例与资料，展示和画像更新由你决定。</p></div><button onClick={()=>setCreating(true)}>新增资料</button></div>
    {partnerId&&<div className={styles.context}><strong>当前伙伴：{current?.name||'加载中…'}</strong><div className={styles.contextActions}><Link href={`/admin/partners/${encodeURIComponent(partnerId)}`} className={`secondary-btn ${styles.contextAction}`}><UiIcon name="send" size={16} className={styles.backIcon}/><span>返回伙伴详情</span></Link><button className={`secondary-btn ${styles.contextAction}`} onClick={()=>filter({partner_id:null})}><UiIcon name="apps" size={16}/><span>查看全部伙伴资料</span></button></div></div>}
    <form className={styles.filters} onSubmit={e=>{e.preventDefault();filter({q:q.trim()});}}>
      <PartnerSelect caption="所属伙伴" label="筛选伙伴" partners={data.partners} value={partnerId} placeholder="全部伙伴" onChange={value=>filter({partner_id:value})}/>
      <label>一级分类<select aria-label="筛选一级分类" value={group} onChange={e=>filter({category_group:e.target.value,category_id:null})}><option value="">全部分类</option>{groups.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
      <label>二级分类<select aria-label="筛选二级分类" value={category} disabled={!group||group==='unclassified'} onChange={e=>filter({category_id:e.target.value})}><option value="">全部</option>{contract.categories.find(g=>g.id===group)?.children.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label className={styles.search}>名称搜索<div><input aria-label="资料名称" value={q} maxLength={200} placeholder="搜索资料名称" onChange={e=>setQ(e.target.value)}/><button className="secondary-btn" type="submit">搜索</button></div></label>
    </form>
    {notice&&<div role="status" className={styles.notice}><span>资料已保存，{notice.name}的画像待更新。</span><div className="table-actions"><Link href={`/admin/partners/${encodeURIComponent(notice.id)}#profile`} className="secondary-btn">前往更新画像</Link><button className="secondary-btn" onClick={()=>setNotice(null)}>暂不更新</button></div></div>}
    {error&&<div className="inline-error-actions"><p role="alert" className="error-text">{error}</p><button className="secondary-btn" onClick={refresh}>重试</button></div>}
    {loading&&<p className="muted" role="status">正在加载资料…</p>}
    {!error&&groups.map(g=>{const entries=data.items.filter(e=>g.id==='unclassified'?!e.category_id:g.ids.includes(e.category_id||''));if(!entries.length)return null;return <section key={g.id} className={styles.group} aria-label={g.name}><div className={styles.groupHeading}><h2>{g.name}</h2><span/></div><div className={styles.grid}>{entries.map(entry=><article key={entry.kind+entry.id} className={`ui-catalog-card ${styles.card}`} data-material-id={entry.id}>
      <div className={styles.cardTop}><span className={styles.tag}>{categoryName(entry.category_id)}</span><small>{entry.visible?'已展示':'未展示'}</small></div>
      <h3><button onClick={()=>setSelected(entry)}>{entry.title}</button></h3><p className={styles.partner}>{entry.partner_name}</p>
      <p className={styles.description}>{entry.description||'暂无简介'}</p><div className={styles.meta}><span>{entry.file_count} 个文件</span><span>{states[entry.processing_status]||entry.processing_status}</span></div>
      <div className={styles.cardBottom}><small>更新于 {new Date(entry.updated_at).toLocaleDateString('zh-CN')}</small><button className="card-entry-link" onClick={()=>setSelected(entry)}><CardEntryLabel>查看与管理</CardEntryLabel></button></div>
    </article>)}</div></section>;})}
    {!loading&&!error&&!data.total&&<section className="card"><p className="placeholder-text">暂无符合条件的资料。</p></section>}
    <Pagination page={page} pageSize={12} total={data.total} disabled={loading||!!error} onPageChange={n=>filter({page:String(n)})} label="伙伴资料分页"/>
    {creating&&<Panel title="新增资料" onClose={()=>setCreating(false)}><MaterialEditor partners={data.partners} partnerId={partnerId} onSaved={entry=>{setCreating(false);setSelected(entry);changed(entry);}}/></Panel>}
    {selected&&<MaterialDetail key={selected.kind+selected.id} entry={selected} partners={data.partners} onClose={()=>setSelected(null)} onChanged={changed} onVisibilityChange={refresh} onReplaced={entry=>{setSelected(entry);changed(entry);}}/>}
  </main>;
}
function Panel({title,onClose,children}:{title:string;onClose:()=>void;children:React.ReactNode}){
  return <div className={styles.overlay}><section role="dialog" aria-modal="true" aria-label={title} className={styles.panel}><header><h2>{title}</h2><button className="secondary-btn" onClick={onClose}>关闭</button></header><div className={styles.panelBody}>{children}</div></section></div>;
}
function MaterialDetail({entry,partners,onClose,onChanged,onVisibilityChange,onReplaced}:{entry:Entry;partners:Partner[];onClose:()=>void;onChanged:(e:Entry)=>void;onVisibilityChange:()=>void;onReplaced:(e:Entry)=>void}){
  const [editing,setEditing]=useState(false),[visible,setVisible]=useState(entry.visible),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const endpoint=entry.kind==='case'?`/cases/${entry.id}/deliverables`:`/partners/${entry.partner_id}/documents`;
  async function toggle(next:boolean){const previous=visible;setVisible(next);setBusy(true);setError('');try{await request(`/cases/${entry.id}/visibility`,'PATCH',{visible:next});onVisibilityChange();}catch(e){setVisible(previous);setError((e as Error).message);}finally{setBusy(false);}}
  async function remove(){if(!confirm('确定删除该资料及全部附件？'))return;setBusy(true);setError('');try{await request(entry.kind==='case'?`/cases/${entry.id}`:`${endpoint}/${entry.id}`,'DELETE');onChanged(entry);onClose();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <Panel title={entry.title} onClose={onClose}>
    <p className="muted">{entry.partner_name} · {categoryName(entry.category_id)}</p>
    <div className={styles.detailActions}>{entry.kind==='case'&&<label><input type="checkbox" checked={visible} disabled={busy} onChange={e=>void toggle(e.target.checked)}/> 展示</label>}<button className="secondary-btn" onClick={()=>setEditing(!editing)}>{editing?'取消编辑':entry.kind==='document'?'编辑与归类':'编辑资料'}</button><button className="secondary-btn danger-outline" disabled={busy} onClick={()=>void remove()}>删除资料</button></div>
    {error&&<p className="error-text" role="alert">{error}</p>}
    {editing?<MaterialEditor partners={partners} partnerId={entry.partner_id} entry={{...entry,visible}} onSaved={e=>{setEditing(false);onReplaced(e);}}/>:<p className="enablement-prose">{entry.description||'暂无简介'}</p>}
    {!editing&&<><p className="muted">{entry.kind==='case'?'开启展示后，普通用户可查看这条资料及其全部附件。':'这份旧资料尚未分类，补齐分类后可继续添加附件及设置展示。'}</p><MaterialFiles endpoint={endpoint} admin allowUpload={entry.kind==='case'} fileId={entry.kind==='document'?entry.id:undefined} onChange={()=>onChanged(entry)} onProcessed={()=>onChanged(entry)}/></>}
  </Panel>;
}
function MaterialEditor({partners,partnerId,entry,onSaved}:{partners:Partner[];partnerId:string;entry?:Entry;onSaved:(e:Entry)=>void}){
  const [partner,setPartner]=useState(partnerId),[title,setTitle]=useState(entry?.title||''),[category,setCategory]=useState(entry?.category_id||''),[description,setDescription]=useState(entry?.description||'');
  const [files,setFiles]=useState<File[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const savedId=useRef(entry?.kind==='case'?entry.id:null);
  async function submit(e:FormEvent){e.preventDefault();if(busy)return;setBusy(true);setError('');try{
    validateMaterials(files);const path=savedId.current?`/cases/${savedId.current}`:entry?.kind==='document'?`/admin/partner-materials/documents/${entry.id}/classify`:'/cases';
    const saved=await request(path,path==='/cases'?'POST':'PUT',{partner_id:partner,title,category_id:category,description:description||null,visible:entry?.visible||false});savedId.current=saved.id;
    for(let i=0;i<files.length;i++){await uploadMaterials(`/cases/${saved.id}/deliverables`,[files[i]]);setFiles(files.slice(i+1));}
    onSaved({...saved,kind:'case',partner_name:partners.find(p=>p.id===partner)?.name||'',file_count:entry?.file_count||0,processing_status:'processing',profile_needs_update:true});
  }catch(e){setError((savedId.current?'资料条目已保存；请检查文件后重试。':'')+(e as Error).message);}finally{setBusy(false);}}
  return <form className="form-grid compact-form" onSubmit={submit}>
    <PartnerSelect className="form-row" caption="关联伙伴" label="关联伙伴" required partners={partners} value={partner} onChange={setPartner}/>
    <label className="form-row">标题<input required maxLength={300} value={title} onChange={e=>setTitle(e.target.value)}/></label><div className="form-span-two"><CaseCategory value={category} onChange={setCategory}/></div>
    <label className="form-row form-span-two">简介（选填）<textarea rows={3} value={description} onChange={e=>setDescription(e.target.value)}/></label>
    <label className="form-row form-span-two">上传文件<input type="file" multiple accept={materialAccept} onChange={e=>{const list=Array.from(e.target.files||[]);try{validateMaterials(list);setFiles(list);setError('');}catch(error){setError((error as Error).message);e.target.value='';setFiles([]);}}}/><small>{contract.upload_notice}</small></label>
    {error&&<p className="error-text form-span-two" role="alert">{error}</p>}<div className="form-span-two"><button disabled={busy||!partner||!category}>{busy?'保存中…':'保存资料'}</button></div>
  </form>;
}
