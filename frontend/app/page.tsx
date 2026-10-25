"use client";
import {ModelMenu,useModelChoice} from "@/components/model-menu";
import {readModelDraft,saveModelDraft,clearModelDraft} from "@/lib/model-draft";
import {useAuth} from "@/components/auth-provider";
import composerStyles from "@/components/task-composer.module.css";
import {useAgent} from "@/components/agent-settings";
import {useComposerShortcuts,COMPOSER_KEY_HINT} from "@/lib/composer-shortcuts";

import { DevelopmentEntry } from "@/components/enablement-workspace";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, useEffect, useLayoutEffect, useRef, useCallback, type RefObject } from "react";
import { HOME_SCENES, type HomeScene, type HomeTaskMode } from "@/lib/scenes";
import { NEW_TASK, useTaskNavigation } from "@/components/task-navigation";
import { UiIcon, type IconName } from "@/components/ui-icons";

const homeSceneIcons: Record<string, IconName> = {
  "home-ai-project": "users",
  "home-industry": "building",
  "home-capability": "puzzle",
  "home-development": "trend",
  "home-gap": "search",
  "home-project-readiness": "toolbox",
};

function ProjectMatchTask({active,requirement,setRequirement,inputRef,onBusyChange}:{
  active:boolean;requirement:string;setRequirement:(value:string)=>void;
  inputRef:RefObject<HTMLTextAreaElement|null>;onBusyChange:(busy:boolean)=>void;
}) {
  const agent=useAgent("partner_match"),searchParams=useSearchParams(),router=useRouter();
  const {submit,openCreatedTask,pending}=useTaskNavigation();
  const model=useModelChoice("partner_match");
  const [loading,setLoading]=useState(false),[error,setError]=useState<string|null>(null);
  const submitting=useRef(false),generation=useRef(0),lastPrompt=useRef<string|null>(null);
  const requirementInput=inputRef,taskStatus=loading?"submitting":"";
  const sameDraftPending=pending.some(task=>task.requirement===requirement);
  const composerKeys=useComposerShortcuts();
  useEffect(()=>{onBusyChange(loading);return()=>onBusyChange(false);},[loading,onBusyChange]);
  useEffect(()=>{
    const id=searchParams.get("task");
    if(id){router.replace(`/tasks/${encodeURIComponent(id)}`);return;}
    if(searchParams.get("view")==="history"){router.replace("/tasks");return;}
    const prompt=searchParams.get("prompt");
    if(!prompt)lastPrompt.current=null;
    if(prompt&&prompt!==lastPrompt.current){lastPrompt.current=prompt;setRequirement(prompt);}
    if(!active){generation.current++;submitting.current=false;setLoading(false);}
  },[searchParams,router,setRequirement,active]);
  useEffect(()=>{
    const reset=()=>{generation.current++;submitting.current=false;setLoading(false);setError(null);setRequirement("");requirementInput.current?.focus();};
    window.addEventListener(NEW_TASK,reset);
    return()=>{generation.current++;window.removeEventListener(NEW_TASK,reset);};
  },[setRequirement,requirementInput]);
  function handleMatch(event:React.FormEvent){event.preventDefault();void handleMatchDirect(requirement);}
  async function handleMatchDirect(text:string){
    if(submitting.current||loading||pending.some(task=>task.requirement===text)||!text.trim()||!model.canSubmit)return;
    submitting.current=true;const current=++generation.current;setLoading(true);setError(null);
    try{const id=await submit(text,model.id);if(current===generation.current)openCreatedTask(id,text,requirementInput.current?.closest("form")||null);}
    catch(reason){if(current===generation.current){setError(reason instanceof Error?reason.message:"任务提交失败");setLoading(false);}}
    finally{if(current===generation.current)submitting.current=false;}
  }
  return <div hidden={!active} role="tabpanel" id="match-panel" aria-labelledby="match-tab">
    <section className="assistant-hero"><p className="assistant-subtitle">{agent.description}</p>
      {!agent.enabled&&<p className="notice-neutral" role="status">该智能体已停用，历史任务仍可查看。</p>}
        <form onSubmit={handleMatch} className={`assistant-composer ${composerStyles.matching}`} data-task-composer>
          <label htmlFor="requirement" className={composerStyles.field}>描述项目背景和伙伴需求
          <textarea
            ref={requirementInput}
            {...composerKeys(setRequirement,()=>void handleMatchDirect(requirement),agent.enabled&&model.canSubmit&&!loading&&!sameDraftPending&&!!requirement.trim())}
            id="requirement"
            aria-label="输入项目需求"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            required
            readOnly={loading}
            rows={4}
            maxLength={2000}
            placeholder="例如：寻找有金融行业数据库迁移经验、能够完成实施交付的伙伴…"
          />
          </label>
          <div className={composerStyles.actions}>
            <div className={composerStyles.actionRow}>
              <span className={`assistant-counter ${composerStyles.counter}`}>{requirement.length}/2000</span>
              <ModelMenu choice={model} disabled={loading||sameDraftPending}/>
              <button type="submit" disabled={!agent.enabled || !model.canSubmit || loading || sameDraftPending || !requirement.trim()} className={composerStyles.submit} aria-label={loading ? (taskStatus === "submitting" ? "提交中" : "分析中") : "开始"}>
                {loading ? <span className="assistant-loading-dot" /> : <UiIcon name="send" size={18} />}<span>{loading ? (taskStatus === "submitting" ? "提交中" : "分析中") : "开始"}</span>
              </button>
            </div>
            <p className={`muted ${composerStyles.hint}`} data-testid="composer-shortcut-hint">{COMPOSER_KEY_HINT}</p>
          </div>
          {model.message&&<p className="muted" role="status">{model.message}</p>}
        </form>
    </section>{error&&<p className="error-text assistant-error">{error}</p>}
  </div>;
}

export default function HomePage() {
  const matchAgent=useAgent("partner_match"),developmentAgent=useAgent("partner_development");
  const search=useSearchParams();
  const {user}=useAuth();
  const [draftOwner,setDraftOwner]=useState("");
  const development=search.get("mode")==="development";
  const [drafts,setDrafts]=useState({match:"",development:""});
  const [busy,setBusy]=useState({match:false,development:false});
  useEffect(()=>{
    if(!user)return;
    const match=readModelDraft(user.id,"partner_match"),dev=readModelDraft(user.id,"partner_development");
    setDrafts({match:match.text||"",development:dev.text||""});setDraftOwner(user.id);
    if(search.get("mode")==="development"&&dev.context&&!search.get("partner_id")){
      const params=new URLSearchParams(search);for(const [key,value] of Object.entries(dev.context))if(value)params.set(key,value);
      window.history.replaceState(null,"",`/?${params}`);
    }
  },[user?.id]);
  useEffect(()=>{
    if(!user||draftOwner!==user.id)return;
    saveModelDraft(user.id,"partner_match",{text:drafts.match});
    const context=Object.fromEntries(["partner_id","task_id","case_id","case_version"].flatMap(key=>search.get(key)?[[key,search.get(key)!]]:[]));
    saveModelDraft(user.id,"partner_development",{text:drafts.development,...(search.get("mode")==="development"?{context}:{})});
  },[drafts,draftOwner,user?.id,search]);

  const [focusRequest,setFocusRequest]=useState<{mode:HomeTaskMode;sequence:number}|null>(null);
  const matchInput=useRef<HTMLTextAreaElement>(null),developmentInput=useRef<HTMLTextAreaElement>(null);
  const changeMatch=useCallback((value:string)=>setDrafts(current=>({...current,match:value})),[]);
  const changeDevelopment=useCallback((value:string)=>setDrafts(current=>({...current,development:value})),[]);
  const matchBusy=useCallback((value:boolean)=>setBusy(current=>current.match===value?current:{...current,match:value}),[]);
  const developmentBusy=useCallback((value:boolean)=>setBusy(current=>current.development===value?current:{...current,development:value}),[]);
  useEffect(()=>{
    const reset=()=>{if(user){clearModelDraft(user.id,"partner_match");clearModelDraft(user.id,"partner_development");}setDrafts({match:"",development:""});setFocusRequest(null);};
    window.addEventListener(NEW_TASK,reset);
    return()=>window.removeEventListener(NEW_TASK,reset);
  },[user?.id]);
  function selectMode(mode:HomeTaskMode) {
    const next=new URLSearchParams(search);
    if(mode==="development")next.set("mode","development");else next.delete("mode");
    next.delete("scene");next.delete("prompt");
    // Native history updates the existing page and retains authorized source context.
    window.history.replaceState(null,"",`/${next.size?`?${next}`:""}`);
  }
  function useScene(scene:HomeScene) {
    if(busy.match||busy.development)return;
    const current=drafts[scene.mode];
    const unchangedTemplate=HOME_SCENES.some(item=>item.mode===scene.mode&&item.prompt===current);
    if(current.trim()&&!unchangedTemplate&&!window.confirm("已有未提交内容，要替换成这个场景模板吗？"))return;
    setDrafts(value=>({...value,[scene.mode]:scene.prompt}));
    selectMode(scene.mode);
    setFocusRequest(value=>({mode:scene.mode,sequence:(value?.sequence||0)+1}));
  }
  useLayoutEffect(()=>{
    if(!focusRequest||(focusRequest.mode==="development")!==development)return;
    const input=focusRequest.mode==="development"?developmentInput.current:matchInput.current;
    if(!input)return;
    input.focus();
    const start=input.value.indexOf("【"),end=input.value.indexOf("】",start);
    if(start>=0&&end>start)input.setSelectionRange(start,end+1);
  },[focusRequest,development]);
  const currentDraft=development?drafts.development:drafts.match;
  return <div className={`page assistant-page unified-task-page${development?" development-task-page":""}`}>
    <header className="unified-task-heading"><div className="assistant-title"><h1>开启新任务</h1></div>
      <nav className="enablement-tabs task-mode-tabs" role="tablist" aria-label="任务模式">
        <button type="button" id="match-tab" role="tab" aria-selected={!development} aria-controls="match-panel" onClick={()=>selectMode("match")} className={!development?"active":""}><UiIcon name={matchAgent.icon} size={18}/>找伙伴</button>
        <button type="button" id="development-tab" role="tab" aria-selected={development} aria-controls="development-panel" onClick={()=>selectMode("development")} className={development?"active":""}><UiIcon name={developmentAgent.icon} size={18}/>促发展</button>
      </nav>
    </header>
    <ProjectMatchTask active={!development} requirement={drafts.match} setRequirement={changeMatch} inputRef={matchInput} onBusyChange={matchBusy}/>
    {development&&<div role="tabpanel" id="development-panel" aria-labelledby="development-tab"><DevelopmentEntry direction={drafts.development} onDirectionChange={changeDevelopment} inputRef={developmentInput} onBusyChange={developmentBusy}/></div>}
    {!search.get("task")&&<section className="home-scenes" aria-label="需求场景">
      {/【[^】]+】/.test(currentDraft)&&<p className="home-template-hint" role="status">请将【】中的提示替换为实际需求，也可以直接改写。</p>}
      <div className="home-scene-buttons">
        {HOME_SCENES.map(scene=><button type="button" className="home-scene-button" key={scene.id} disabled={busy.match||busy.development} onClick={()=>useScene(scene)}><UiIcon name={homeSceneIcons[scene.id]} size={18} className="home-scene-icon"/><span>{scene.name}</span></button>)}
      </div>
    </section>}
  </div>;
}
