"use client";
import Link from "next/link";
export type FailureDetail={stage:string;stageLabel:string;code:string;message:string;action:string;modelRelated?:boolean};
const serviceCodes=new Set(["configuration","authentication","connection","provider","persistence"]);
export const uncertainResult="暂未确认结果，请刷新查看。";
export const serviceFailure="服务异常，请联系管理员。";
export function actionFailure(message:string,operation="处理"):string {
 return message==="本次处理失败，请重试。"?(operation==="建议"?"本次建议未生成，请重试。":`本次${operation}失败，请重试。`):message;
}
export function failureMessage(details?:FailureDetail[],operation="处理"):string {
 const model=details?.find(item=>item.modelRelated);
 const messages:Record<string,string>={timeout:"模型响应超时。本次分析未完成，你可以返回切换模型后重新提交。",rate_limit:"模型服务请求受限。可以稍后重试，或返回切换模型。",connection:"暂时无法连接模型服务，可以重试或返回切换模型。",provider:"模型服务返回异常，可以重试或返回切换模型。",configuration:"当前模型暂不可用。请切换模型，或联系管理员。",context_capacity:"该模型尚未配置总上下文容量，请管理员填写后重试，或返回切换模型。",authentication:"当前模型暂不可用。请切换模型，或联系管理员。",invalid_result:"模型返回内容未能完成解析。可以重试或切换模型。"};
 if(model&&messages[model.code])return messages[model.code];
 if(details?.some(item=>item.code==="persistence"))return "结果保存失败，已有内容已保留。";
 if(details?.some(item=>item.code==="run_timeout"))return "本次处理超过任务执行时限，已中断。";
 if(details?.some(item=>item.code==="interrupted"))return "本次处理已中断，已有内容已保留。";
 return details?.some(item=>serviceCodes.has(item.code))?serviceFailure:actionFailure("本次处理失败，请重试。",operation);
}
export function FailureReasons({details,href}:{details?:FailureDetail[];stages?:string|null;href?:string}){
 return <span className="task-failure-control"><span>{failureMessage(details)}</span>{href&&<Link href={href} className="task-failure-link">查看任务</Link>}</span>;
}
export function FailureNotice({details,message,title,operation,impact,partial,children}:{details?:FailureDetail[];message?:string;operation?:string;stages?:string|null;title?:string;impact?:string;partial:boolean;children?:React.ReactNode}){
 return <section className={`task-failure-notice ${partial?"notice-warning":"notice-error"}`} aria-label="任务未完成说明"><div className="task-failure-copy"><strong>{message||title||failureMessage(details,operation)}</strong>{!message&&title&&details?.some(d=>d.modelRelated||["persistence","run_timeout","interrupted"].includes(d.code))&&<p>{failureMessage(details,operation)}</p>}{impact&&<p className="muted">{impact}</p>}</div><div className="task-failure-actions">{children}</div></section>;
}
