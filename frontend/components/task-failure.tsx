"use client";
import {useId,useRef} from "react";
import Link from "next/link";
export type FailureDetail={stage:string;stageLabel:string;code:string;message:string;action:string};
const labels:Record<string,string>={partner_match:"伙伴匹配",partner_data:"伙伴数据读取",demand_profile:"需求画像",project_opportunity:"项目机会",persistence:"结果保存",interrupted:"执行中断"};
export function failureItems(details?:FailureDetail[],stages?:string|null):FailureDetail[]{
 const stageList=stages?.split(",").filter(Boolean)||[];
 return details?.length?details:(stageList.length?stageList:["unknown"]).map(stage=>({stage,stageLabel:labels[stage]||"处理环节",code:"unknown",message:"具体原因未记录",action:"重试或联系管理员"}));
}
export function FailureReasons({details,stages,href}:{details?:FailureDetail[];stages?:string|null;href?:string}){
 const id=useId(),panel=useRef<HTMLDivElement>(null);
 return <span className="task-failure-control"><button type="button" className="task-failure-link" aria-controls={id} aria-haspopup="dialog" onClick={event=>{const p=panel.current;if(!p)return;const rect=event.currentTarget.getBoundingClientRect();p.style.left=`${Math.max(12,Math.min(rect.left,window.innerWidth-348))}px`;p.style.top=`${Math.max(12,Math.min(rect.bottom+8,window.innerHeight-280))}px`;p.showPopover();}}>查看原因</button><div id={id} ref={panel} popover="auto" role="dialog" aria-label="任务失败原因" className="task-failure-popover"><strong>未完成原因</strong><ul>{failureItems(details,stages).map((item,index)=><li key={index}><strong>{item.stageLabel}</strong><p>{item.message}</p><small>{item.action}</small></li>)}</ul>{href&&<Link href={href} className="task-failure-link">进入任务详情 →</Link>}<button type="button" className="task-failure-link" onClick={()=>panel.current?.hidePopover()}>关闭</button></div></span>;
}
export function FailureNotice({details,stages,title,impact,partial,children}:{details?:FailureDetail[];stages?:string|null;title:string;impact:string;partial:boolean;children?:React.ReactNode}){
 const items=failureItems(details,stages);
 return <section className={`task-failure-notice ${partial?"notice-warning":"notice-error"}`} aria-label="任务未完成说明"><div className="task-failure-copy"><strong>{title}</strong><p>{items.length===1?`${items[0].stageLabel}未完成。原因：${items[0].message}`:`未完成环节：${items.map(i=>i.stageLabel).join("、")}。`}</p><p className="muted">{impact}</p></div><div className="task-failure-actions">{children}<FailureReasons details={items}/></div></section>;
}
