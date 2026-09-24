"use client";
import Link from "next/link";
export type FailureDetail={stage:string;stageLabel:string;code:string;message:string;action:string};
const serviceCodes=new Set(["configuration","authentication","connection","provider","persistence"]);
export function failureMessage(details?:FailureDetail[]):string {
 return details?.some(item=>serviceCodes.has(item.code))?"服务异常，请联系管理员。":"本次处理失败，请重试。";
}
export function FailureReasons({details,href}:{details?:FailureDetail[];stages?:string|null;href?:string}){
 return <span className="task-failure-control"><span>{failureMessage(details)}</span>{href&&<Link href={href} className="task-failure-link">查看任务</Link>}</span>;
}
export function FailureNotice({details,impact,partial,children}:{details?:FailureDetail[];stages?:string|null;title:string;impact:string;partial:boolean;children?:React.ReactNode}){
 return <section className={`task-failure-notice ${partial?"notice-warning":"notice-error"}`} aria-label="任务未完成说明"><div className="task-failure-copy"><strong>{failureMessage(details)}</strong><p className="muted">{impact}</p></div><div className="task-failure-actions">{children}</div></section>;
}
