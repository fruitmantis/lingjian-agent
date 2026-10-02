"use client";

import {useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode} from "react";
import {usePathname, useRouter, useSearchParams} from "next/navigation";
import {useTaskNavigation} from "./task-navigation";

type Box = {left:number;top:number;width:number;height:number};
const box = (element:Element):Box => {
  const {left,top,width,height}=element.getBoundingClientRect();
  return {left,top,width,height};
};
const pixels = (values:Record<string,number>) => Object.fromEntries(Object.entries(values).map(([key,value])=>[key,`${value}px`]));
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

type Arrival = {
  id:string; requirement:string; origin:string; phase:"waiting"|"moving"|"settled";
  frame:Box; text:CSSProperties; chrome:HTMLElement; target?:HTMLElement;
};

/** A one-navigation visual handoff, scoped to the existing user/task provider.
 * No snapshot, progress or business result is copied into this state. */
export function useTaskTransitionState() {
  const router=useRouter(),pathname=usePathname(),search=useSearchParams();
  const location=pathname+(search.size?`?${search}`:"");
  const [arrival,setArrival]=useState<Arrival|null>(null);
  const destination=arrival?`/tasks/${encodeURIComponent(arrival.id)}`:"";
  const active=arrival&&(location===arrival.origin||pathname===destination)?arrival:null;
  useLayoutEffect(()=>{if(arrival&&!active)setArrival(null);},[arrival,active]);
  function openCreatedTask(id:string,requirement:string,source:HTMLElement|null) {
    const input=source?.querySelector("textarea"),page=source?.closest<HTMLElement>(".unified-task-page");
    if(source&&input&&page&&source.isConnected) {
      const frame=box(source),inputBox=box(input),style=getComputedStyle(input);
      // Only outgoing page chrome is retained for its fade; it is inert and short-lived.
      const chrome=page.cloneNode(true) as HTMLElement;
      chrome.querySelectorAll("[data-task-composer]").forEach(node=>(node as HTMLElement).style.visibility="hidden");
      chrome.querySelectorAll("[id]").forEach(node=>node.removeAttribute("id"));
      chrome.setAttribute("aria-hidden","true");chrome.inert=true;
      const bounds=box(page);
      Object.assign(chrome.style,{position:"fixed",left:`${bounds.left}px`,top:`${bounds.top}px`,width:`${bounds.width}px`,margin:"0"});
      setArrival({id,requirement,origin:location,phase:"waiting",frame,chrome,text:{
        fontFamily:style.fontFamily,fontSize:style.fontSize,fontWeight:style.fontWeight,lineHeight:style.lineHeight,color:style.color,
        // Keep the textarea viewport until the detail card can take over.
        position:"relative",top:-input.scrollTop,
        clipPath:`inset(${input.scrollTop+inputBox.top-frame.top}px 0 calc(100% - ${input.scrollTop+inputBox.top-frame.top+inputBox.height}px) 0)`,
        paddingTop:inputBox.top-frame.top+parseFloat(style.paddingTop),
        paddingLeft:inputBox.left-frame.left+parseFloat(style.paddingLeft),
        paddingRight:frame.left+frame.width-inputBox.left-inputBox.width+parseFloat(style.paddingRight),
      }});
    }
    router.push(`/tasks/${encodeURIComponent(id)}`,{scroll:false});
  }
  function attachRequest(id:string,target:HTMLElement) {
    setArrival(current=>current?.id===id&&current.phase==="waiting"?{...current,target,phase:"moving"}:current);
  }
  function finishArrival(id:string) {
    setArrival(current=>current?.id===id?{...current,phase:"settled"}:current);
  }
  return {arrival:active,openCreatedTask,attachRequest,finishArrival};
}

/** Lives beside routed content, so a slow detail read never removes the input. */
export function TaskTransitionLayer() {
  const {arrival,finishArrival}=useTaskNavigation();
  const chrome=useRef<HTMLDivElement>(null),frame=useRef<HTMLDivElement>(null),text=useRef<HTMLParagraphElement>(null),label=useRef<HTMLHeadingElement>(null);
  useLayoutEffect(()=>{
    if(!arrival||arrival.phase==="settled"||!chrome.current)return;
    const node=arrival.chrome;chrome.current.replaceChildren(node);
    const animation=node.animate([{opacity:1},{opacity:0}],{duration:reducedMotion()?0:180,fill:"forwards"});
    return ()=>{animation.cancel();node.remove();};
  },[arrival?.id]);
  useLayoutEffect(()=>{
    if(arrival?.phase!=="moving"||!arrival.target||!frame.current||!text.current||!label.current)return;
    const target=arrival.target,paragraph=target.querySelector("p")!,heading=target.querySelector("h2")!;
    const end=box(target),copy=box(paragraph),title=box(heading),style=getComputedStyle(target);
    const options={duration:reducedMotion()?0:280,easing:"cubic-bezier(.22,.7,.25,1)",fill:"forwards" as FillMode};
    const animations=[
      frame.current.animate([pixels(arrival.frame),{...pixels(end),background:style.backgroundColor,borderColor:style.borderColor,borderWidth:style.borderTopWidth,borderRadius:style.borderRadius,boxShadow:"none"}],options),
      text.current.animate([{...pixels({top:Number(arrival.text.top),paddingTop:Number(arrival.text.paddingTop),paddingLeft:Number(arrival.text.paddingLeft),paddingRight:Number(arrival.text.paddingRight)}),clipPath:arrival.text.clipPath},{...pixels({top:0,paddingTop:copy.top-end.top,paddingLeft:copy.left-end.left,paddingRight:end.left+end.width-copy.left-copy.width}),clipPath:"inset(0px 0px 0px 0px)"}],options),
      label.current.animate([{opacity:0},{opacity:1}],{...options,duration:reducedMotion()?0:180,delay:reducedMotion()?0:100}),
    ];
    Object.assign(label.current.style,{left:`${title.left-end.left}px`,top:`${title.top-end.top}px`});
    let live=true;
    const finish=()=>{if(live)finishArrival(arrival.id);};
    void animations[0].finished.then(finish).catch(()=>{});
    window.addEventListener("resize",finish);window.addEventListener("scroll",finish,{passive:true});
    return ()=>{live=false;animations.forEach(a=>a.cancel());window.removeEventListener("resize",finish);window.removeEventListener("scroll",finish);};
  },[arrival?.id,arrival?.phase]);
  if(!arrival||arrival.phase==="settled")return null;
  return <div className="task-transition-layer" data-testid="task-transition" data-phase={arrival.phase}>
    <div ref={chrome} aria-hidden="true"/>
    <div ref={frame} className="task-transition-frame" style={arrival.frame}>
      <h2 ref={label}>本次需求</h2>
      <p ref={text} style={arrival.text}>{arrival.requirement}</p>
    </div>
  </div>;
}

export function TaskRequest({id,children,className="",testId}:{id:string;children:ReactNode;className?:string;testId?:string}) {
  const {arrival,attachRequest}=useTaskNavigation();
  const ref=useRef<HTMLElement>(null);
  useLayoutEffect(()=>{if(ref.current)attachRequest(id,ref.current);},[id]);
  return <section ref={ref} className={`card task-request task-request-compact ${className}`} data-testid={testId}
    style={arrival?.id===id&&arrival.phase!=="settled"?{visibility:"hidden"}:undefined}>
    <h2>本次需求</h2><p className="requirement-block">{children}</p>
  </section>;
}

/** Mount once per persisted section: polling must not replay or move old content. */
export function TaskResult({id,children,className="",testId,progress=false,ariaLabel,as:Element="section"}:{id:string;children:ReactNode;className?:string;testId?:string;progress?:boolean;ariaLabel?:string;as?:"section"|"article"}) {
  const {arrival}=useTaskNavigation();
  const ref=useRef<HTMLElement>(null);
  const fresh=arrival?.id===id;
  const waiting=fresh&&arrival.phase!=="settled";
  useLayoutEffect(()=>{
    if(waiting||!ref.current)return;
    if(!fresh||reducedMotion())return;
    const animation=ref.current.animate(progress?[{opacity:0,transform:"translateY(6px)"},{opacity:1,transform:"translateY(0)"}]:[{opacity:0},{opacity:1}],{duration:180,easing:"ease-out"});
    return ()=>animation.cancel();
  },[waiting,fresh]);
  return <Element ref={ref} className={className} data-testid={testId} aria-label={ariaLabel} style={waiting?{opacity:0}:undefined}>{children}</Element>;
}

/** A failed detail read must release the handoff and keep its real submitted text. */
export function TaskArrivalReadError({id,keepInput=true}:{id:string;keepInput?:boolean}) {
  const {arrival,finishArrival}=useTaskNavigation();
  useLayoutEffect(()=>{finishArrival(id);},[id]);
  return keepInput&&arrival?.id===id?<TaskRequest id={id}>{arrival.requirement}</TaskRequest>:null;
}
