"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {apiFetch,useAuth} from "./auth-provider";
import type {AgentId} from "./agent-settings";
import {readModelDraft,saveModelDraft,clearModelDraft} from "../lib/model-draft";
import styles from "./model-menu.module.css";
export type ModelSelection={id:string|null;name:string|null};
type ModelOption={id:string;name:string;isDefault:boolean};
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
export function ModelMenu({choice,disabled=false}:{choice:ModelChoice;disabled?:boolean}){
 const box=useRef<HTMLDivElement>(null),button=useRef<HTMLButtonElement>(null);
 useEffect(()=>{if(!choice.open)return;function outside(e:PointerEvent){if(e.target instanceof Node&&!box.current?.contains(e.target))choice.setOpen(false);}document.addEventListener("pointerdown",outside);return()=>document.removeEventListener("pointerdown",outside);},[choice.open,choice.setOpen]);
 function close(){choice.setOpen(false);button.current?.focus();}
 return <div className={styles.wrap} ref={box} onKeyDown={e=>{if(e.key==="Escape"){e.preventDefault();close();}if(choice.open&&["ArrowDown","ArrowUp"].includes(e.key)){e.preventDefault();const items=[...box.current!.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')];const i=items.indexOf(document.activeElement as HTMLButtonElement),step=e.key==="ArrowDown"?1:-1,next=i<0?(step===1?0:items.length-1):(i+step+items.length)%items.length;items[next]?.focus();}}}>
  <button ref={button} type="button" className={styles.trigger} aria-label={`选择模型：${choice.name}`} aria-haspopup="menu" aria-expanded={choice.open} disabled={disabled} onClick={()=>{if(!choice.open)void choice.reload();choice.setOpen(!choice.open);}}><span className={styles.name}>{choice.name}</span><span aria-hidden="true">⌄</span></button>
  {choice.open&&<div className={styles.menu} role="menu" aria-label="选择模型"><p className={styles.caption}>选择模型</p>{choice.options.map(model=><button type="button" role="menuitemradio" aria-checked={choice.id===model.id} key={model.id} onClick={()=>{choice.choose(model.id);button.current?.focus();}}><span>{model.name}{model.isDefault&&<small>默认</small>}</span><span className={styles.check}>{choice.id===model.id?"✓":""}</span></button>)}{!choice.options.length&&<p className={styles.empty}>{choice.message||"正在读取可用模型…"}</p>}</div>}
 </div>;
}
export function ModelStamp({value}:{value?:ModelSelection|null}){return <span className={styles.stamp}>本次模型：{value?.name||"按当时配置执行"}</span>;}
