"use client";
import {TaskResult} from "./task-transition";
import {useEffect,useState} from "react";

export type TaskProgressData={run_id:string;started_at:string;finished_at:string|null;stages:{key:string;label:string;status:string;started_at:string|null;finished_at:string|null}[]};
function elapsed(start:string,end:number){const seconds=Math.max(0,Math.floor((end-Date.parse(start))/1000));return seconds<60?`${seconds} 秒`:`${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;}
export function TaskProgress({value,taskId=""}:{value?:TaskProgressData|null;taskId?:string}){
 const [now,setNow]=useState(Date.now());
 useEffect(()=>{setNow(Date.now());if(!value||value.finished_at)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[value?.run_id,value?.finished_at]);
 if(!value)return null;
 const end=value.finished_at?Date.parse(value.finished_at):now;
 const running=value.stages.find(stage=>stage.status==="running"),failed=value.stages.find(stage=>stage.status==="failed");
 const summary=running?"进行中："+running.label:failed?"未完成："+failed.label:value.finished_at?"本次执行已结束":"等待处理";
 return <TaskResult id={taskId} progress className="task-progress" testId="task-progress" ariaLabel="任务执行进度">
  <div className="task-progress-heading"><div><h2>执行进度</h2><p className="task-progress-current" role="status">{summary}</p></div><span data-testid="task-elapsed">本次已用时间：{elapsed(value.started_at,end)}</span></div>
  <details className="task-progress-details"><summary>查看阶段记录</summary><ol>{value.stages.map(stage=><li key={stage.key} data-stage={stage.key} data-status={stage.status}>
   <span className="task-progress-dot" aria-hidden="true"/><span>{stage.label}</span>
   <small>{stage.status==="running"?`进行中 · ${elapsed(stage.started_at!,now)}`:stage.status==="completed"?`已完成${stage.started_at&&stage.finished_at?` · ${elapsed(stage.started_at,Date.parse(stage.finished_at))}`:""}`:stage.status==="failed"?`未完成${stage.started_at&&stage.finished_at?` · ${elapsed(stage.started_at,Date.parse(stage.finished_at))}`:""}`:stage.status==="skipped"?"本次未执行":"等待处理"}</small>
  </li>)}</ol></details>
 </TaskResult>;
}
