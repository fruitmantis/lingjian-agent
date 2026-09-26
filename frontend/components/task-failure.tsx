"use client";
import Link from "next/link";
export type FailureDetail={stage:string;stageLabel:string;code:string;message:string;action:string};
const serviceCodes=new Set(["configuration","authentication","connection","provider","persistence"]);
export const uncertainResult="暂未确认结果，请刷新查看。";
export const serviceFailure="服务异常，请联系管理员。";
export function actionFailure(message:string,operation="处理"):string {
 return message==="本次处理失败，请重试。"?(operation==="建议"?"本次建议未生成，请重试。":`本次${operation}失败，请重试。`):message;
}
export function failureMessage(details?:FailureDetail[],operation="处理"):string {
 return details?.some(item=>serviceCodes.has(item.code))?serviceFailure:actionFailure("本次处理失败，请重试。",operation);
}
export function FailureReasons({details,href}:{details?:FailureDetail[];stages?:string|null;href?:string}){
 return <span className="task-failure-control"><span>{failureMessage(details)}</span>{href&&<Link href={href} className="task-failure-link">查看任务</Link>}</span>;
}
export function FailureNotice({details,message,operation,impact,partial,children}:{details?:FailureDetail[];message?:string;operation?:string;stages?:string|null;title?:string;impact?:string;partial:boolean;children?:React.ReactNode}){
 return <section className={`task-failure-notice ${partial?"notice-warning":"notice-error"}`} aria-label="任务未完成说明"><div className="task-failure-copy"><strong>{message||failureMessage(details,operation)}</strong>{impact&&<p className="muted">{impact}</p>}</div><div className="task-failure-actions">{children}</div></section>;
}
