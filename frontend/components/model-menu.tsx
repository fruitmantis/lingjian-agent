"use client";
import {useCallback,useEffect,useLayoutEffect,useRef,useState} from "react";
import {apiFetch,useAuth} from "./auth-provider";
import type {AgentId} from "./agent-settings";
import {readModelDraft,saveModelDraft,clearModelDraft} from "../lib/model-draft";
import styles from "./model-menu.module.css";
export type ModelSelection={id:string|null;name:string|null};
type ModelOption={id:string;name:string;isDefault:boolean;providerId?:string;providerName?:string};
type Options={models:ModelOption[];defaultModelConfigId:string|null;agentEnabled:boolean;unavailableReason:string|null};
export function useModelChoice(agent:AgentId,scope="draft",preferred?:string|null,ready=true){
 const {user}=useAuth();const [options,setOptions]=useState<Options|null>(null),[id,setId]=useState<string|null>(null),[open,setOpen]=useState(false),[hydrated,setHydrated]=useState(""),[error,setError]=useState("");
 const userId=user?.id,owner=`${user?.id}:${agent}:${scope}`;
 useEffect(()=>{if(!userId)return;const saved=readModelDraft(userId,agent,scope);setId(saved.modelConfigId??null);setOpen(saved.openMenu===true);setHydrated(owner);},[userId,agent,scope]);
 useEffect(()=>{if(userId&&hydrated===owner&&open)saveModelDraft(userId,agent,{openMenu:false},scope);},[userId,agent,scope,hydrated,owner,open]);
 const reload=useCallback(async()=>{if(!userId)return;try{const r=await apiFetch(`/agents/${agent}/models`,{cache:"no-store"});if(!r.ok)throw new Error("暂时无法读取可用模型，请重试。");setOptions(await r.json());setError("");}catch(e){setError(e instanceof Error?e.message:"模型读取失败");}},[agent,userId]);
 useEffect(()=>{setOptions(null);void reload();},[reload]);
 useEffect(()=>{if(hydrated===owner&&ready&&options&&id===null)setId(preferred||options.defaultModelConfigId||"");},[hydrated,ready,options,id,preferred]);
 useEffect(()=>{if(userId&&hydrated===owner&&id!==null)saveModelDraft(userId,agent,{modelConfigId:id},scope);},[userId,agent,scope,hydrated,id]);
 useEffect(()=>{if(scope!=="draft")return;const reset=()=>{if(userId)clearModelDraft(userId,agent);setId(null);setOpen(false);};window.addEventListener("lingjian:new-task",reset);return()=>window.removeEventListener("lingjian:new-task",reset);},[userId,agent,scope]);
 const selected=options?.models.find(m=>m.id===id);
 const message=error||options?.unavailableReason||(options&&id!==null&&!selected?"所选模型当前不可用，请重新选择。":"");
 return {id:id||undefined,name:selected?.name|| (id?"所选模型不可用":"选择模型"),options:options?.models||[],open,setOpen,choose:(next:string)=>{setId(next);setOpen(false);},reload,message,canSubmit:!!(ready&&hydrated===owner&&selected&&options?.agentEnabled&&!error)};
}
export type ModelChoice=ReturnType<typeof useModelChoice>;
type ProviderChoice={id:string;name:string;models:ModelOption[]};
type MenuFocus="first"|"last"|"model"|{providerId:string};
function ModelMenuPanel({choice,trigger,initialFocus}:{choice:ModelChoice;trigger:()=>HTMLButtonElement|null;initialFocus:{current:"first"|"last"|null}}){
 const menu=useRef<HTMLDivElement>(null),back=useRef<HTMLButtonElement>(null);
 const [provider,setProvider]=useState<{id:string;name:string}|null>(null);
 const nextFocus=useRef<MenuFocus|null>(initialFocus.current);
 // The previous API has no provider relation. Keep its flat choices until the backend is updated.
 const hasProviders=choice.options.every(model=>typeof model.providerId==="string"&&!!model.providerId&&typeof model.providerName==="string"&&!!model.providerName);
 const groups=new Map<string,ProviderChoice>();
 if(hasProviders)for(const model of choice.options){
  const id=model.providerId!,existing=groups.get(id);
  if(existing)existing.models.push(model);
  else groups.set(id,{id,name:model.providerName!,models:[model]});
 }
 const models=provider?choice.options.filter(model=>model.providerId===provider.id):choice.options;
 const selected=choice.options.find(model=>model.id===choice.id);
 useLayoutEffect(()=>{
  const element=menu.current;if(!element)return;
  function fit(){
   element!.style.setProperty("--menu-shift","0px");
   const bounds=element!.getBoundingClientRect();
   const rightAligned=window.innerWidth-16-bounds.width;
   const left=window.innerWidth<=600?Math.max(16,rightAligned):Math.max(16,Math.min(bounds.left,rightAligned));
   element!.style.setProperty("--menu-shift",(left-bounds.left)+"px");
  }
  fit();window.addEventListener("resize",fit);
  const focus=nextFocus.current;nextFocus.current=null;initialFocus.current=null;
  const items=[...element.querySelectorAll<HTMLButtonElement>('[role="menuitem"],[role="menuitemradio"]')];
  let target:HTMLButtonElement|undefined;
  if(focus==="model")target=element.querySelector<HTMLButtonElement>('[role="menuitemradio"]')||back.current||undefined;
  else if(focus==="first")target=items[0];
  else if(focus==="last")target=items.at(-1);
  else if(focus)target=items.find(item=>item.dataset.providerId===focus.providerId)||items[0];
  else if(provider&&!models.length)target=back.current||undefined;
  if(focus||target)(target||element).focus();
  return()=>window.removeEventListener("resize",fit);
 },[provider,choice.options]);
 function enter(value:ProviderChoice){nextFocus.current="model";setProvider({id:value.id,name:value.name});}
 function goBack(){if(provider){nextFocus.current={providerId:provider.id};setProvider(null);}}
 function select(model:ModelOption){choice.choose(model.id);trigger()?.focus();}
 const modelRows=models.map(model=><button type="button" role="menuitemradio" tabIndex={-1} aria-checked={choice.id===model.id} key={model.id} onClick={()=>select(model)}>
  <span className={styles.label}>{model.name}{model.isDefault&&<small>默认</small>}</span><span className={styles.check} aria-hidden="true">{choice.id===model.id?"✓":""}</span>
 </button>);
 return <div className={styles.menu} ref={menu} role="menu" aria-label="选择模型" tabIndex={-1} onKeyDown={event=>{if(event.key==="ArrowLeft"&&provider){event.preventDefault();goBack();}}}>
  {provider?<button ref={back} type="button" role="menuitem" tabIndex={-1} aria-label="返回供应商" className={styles.back} onClick={goBack}><span className={styles.chevron} aria-hidden="true">‹</span><span className={styles.label}>{provider.name}</span></button>:<p className={styles.caption}>{hasProviders?"选择供应商":"选择模型"}</p>}
  <div className={styles.list}>
   {!provider&&hasProviders?[...groups.values()].map(value=><button type="button" role="menuitem" tabIndex={-1} aria-haspopup="menu" data-provider-id={value.id} key={value.id} onClick={()=>enter(value)} onKeyDown={event=>{if(event.key==="ArrowRight"){event.preventDefault();enter(value);}}}>
    <span className={styles.label}>{value.name}</span><span className={styles.meta}>{value.models.some(model=>model.isDefault)&&<small>含默认模型</small>}{selected?.providerId===value.id&&<small className={styles.current}>当前</small>}<span className={styles.chevron} aria-hidden="true">›</span></span>
   </button>):modelRows}
   {!(provider?models.length:choice.options.length)&&<p className={styles.empty}>{provider?"该供应商暂无可选模型。":choice.message||"正在读取可用模型…"}</p>}
  </div>
 </div>;
}
export function ModelMenu({choice,disabled=false}:{choice:ModelChoice;disabled?:boolean}){
 const box=useRef<HTMLDivElement>(null),button=useRef<HTMLButtonElement>(null),initialFocus=useRef<"first"|"last"|null>(null);
 useEffect(()=>{
  if(!choice.open)return;
  function outside(event:PointerEvent){if(event.target instanceof Node&&!box.current?.contains(event.target))choice.setOpen(false);}
  function escape(event:KeyboardEvent){if(event.key==="Escape"){event.preventDefault();choice.setOpen(false);button.current?.focus();}}
  document.addEventListener("pointerdown",outside);document.addEventListener("keydown",escape);
  return()=>{document.removeEventListener("pointerdown",outside);document.removeEventListener("keydown",escape);};
 },[choice.open,choice.setOpen]);
 function open(focus:"first"|"last"|null=null){initialFocus.current=focus;void choice.reload();choice.setOpen(true);}
 return <div className={styles.wrap} ref={box} onKeyDown={event=>{
  if(event.key==="Tab"&&choice.open){choice.setOpen(false);button.current?.focus();return;}
  if(!["ArrowDown","ArrowUp"].includes(event.key)||disabled)return;
  event.preventDefault();
  if(!choice.open){open(event.key==="ArrowDown"?"first":"last");return;}
  const items=[...box.current!.querySelectorAll<HTMLButtonElement>('[role="menuitem"],[role="menuitemradio"]')];
  const index=items.indexOf(document.activeElement as HTMLButtonElement),step=event.key==="ArrowDown"?1:-1;
  const next=index<0?(step===1?0:items.length-1):(index+step+items.length)%items.length;
  items[next]?.focus();
 }}>
  <button ref={button} type="button" className={styles.trigger} aria-label={"选择模型："+choice.name} aria-haspopup="menu" aria-expanded={choice.open} disabled={disabled} onClick={()=>choice.open?choice.setOpen(false):open()}><span className={styles.name}>{choice.name}</span><span aria-hidden="true">⌄</span></button>
  {choice.open&&<ModelMenuPanel choice={choice} trigger={()=>button.current} initialFocus={initialFocus}/>}
 </div>;
}
export function ModelStamp({value}:{value?:ModelSelection|null}){return <span className={styles.stamp}>本次模型：{value?.name||"按当时配置执行"}</span>;}
