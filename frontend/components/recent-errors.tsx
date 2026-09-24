"use client";
import {useEffect,useState} from "react";
import {adminApiFetch} from "./auth-provider";
import {responseError} from "../lib/api-request";
import styles from "./recent-errors.module.css";

type ErrorEntry={id:string;time:string;request_id:string;task_id:string|null;run_id:string|null;stage:string;exception_type:string;message:string;model:string|null;http_status:number|null;response_excerpt:string|null;traceback:string};
const stages:Record<string,string>={partner_match:"伙伴匹配",partner_data:"伙伴数据读取",demand_profile:"需求画像",project_opportunity:"项目机会",tag_suggestion:"标签建议",configuration:"模型配置",analysis:"方向分析",retrieval:"资源检索",generation:"建议生成",conversation:"继续问伴飞",persistence:"结果保存",interrupted:"执行中断",run_timeout:"执行时限",model_test:"模型连接测试",submission:"任务提交"};
function errorText(item:ErrorEntry){
 return [`时间：${item.time}`,`错误 ID：${item.id}`,`任务 ID：${item.task_id||"—"}`,`请求 ID：${item.request_id}`,`运行 ID：${item.run_id||"—"}`,`失败环节：${stages[item.stage]||item.stage}`,`异常类型：${item.exception_type}`,`实际原因：${item.message}`,`模型：${item.model||"—"}`,`HTTP 状态码：${item.http_status??"未收到响应 / 不适用"}`,`返回片段：\n${item.response_excerpt||"—"}`,`堆栈：\n${item.traceback||"—"}`].join("\n");
}
export function RecentErrors(){
 const [items,setItems]=useState<ErrorEntry[]>([]),[busy,setBusy]=useState(true),[error,setError]=useState(""),[copy,setCopy]=useState("");
 async function load(){setBusy(true);setError("");try{const response=await adminApiFetch("/admin/system/errors?limit=50",{cache:"no-store"});if(!response.ok)throw await responseError(response);setItems((await response.json()).items);}catch(reason){setError(reason instanceof Error?reason.message:"最近错误暂不可读取。");}finally{setBusy(false);}}
 useEffect(()=>{void load();},[]);
 async function copyDetails(item:ErrorEntry){try{await navigator.clipboard.writeText(errorText(item));setCopy(`已复制错误详情：${item.id}`);}catch{setCopy("复制失败，请选中下方详情手动复制。");}}
 return <section className={`card ${styles.panel}`} aria-label="最近错误"><div className={styles.heading}><div><h2>最近错误</h2><p className="muted">按时间倒序显示最近 50 条记录；重试成功后仍保留。详情已脱敏。</p></div><button className="secondary-btn" disabled={busy} onClick={()=>void load()}>{busy?"读取中…":"刷新错误"}</button></div>
 {error&&<p role="alert" className="error-text">{error}</p>}{copy&&<p role="status" className="muted">{copy}</p>}
 {!busy&&!error&&!items.length&&<p className="placeholder-text">暂无已记录的错误。启用记录前的历史失败无法补充真实原因。</p>}
 <div className={styles.list}>{items.map(item=><details key={item.id} className={styles.entry}><summary><time dateTime={item.time}>{new Date(item.time).toLocaleString("zh-CN")}</time><span className={styles.stage}>{stages[item.stage]||item.stage}</span><span className={styles.reason}>{item.message}</span></summary><div className={styles.detail}><div className={styles.actions}><span className="muted">{item.task_id?`任务 ${item.task_id}`:`请求 ${item.request_id}`}</span><button type="button" className="secondary-btn" onClick={()=>void copyDetails(item)}>复制错误详情</button></div><pre tabIndex={0} aria-label="错误完整详情">{errorText(item)}</pre></div></details>)}</div></section>;
}
