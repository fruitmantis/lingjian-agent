"use client";

import Link from "next/link";
import {PlanStatus,type PlanPresentation} from "./plan-status";
import { useEffect, useState } from "react";
import { apiFetch } from "./auth-provider";

import { tasksChanged } from "./task-navigation";

type TaskStatus = "matching" | "enriching" | "ready" | "partial" | "failed";
type Task = {
  planPresentation?: PlanPresentation | null;
  id: string; requirement: string; topPartner: string; partnerCount: number; createdAt: string;
  archivedAt: string | null; ownerName: string | null; department: string | null; completenessScore: number | null;
  task_type: string; taskStatus: TaskStatus; lastErrorStage: string | null;
};
type TaskPage = { items: Task[]; page: number; pageSize: number; total: number; totalPages: number };

const statusLabels: Record<TaskStatus, string> = {
  matching: "匹配中", enriching: "处理中", ready: "已完成", partial: "部分完成", failed: "失败",
};
const errorStageLabels: Record<string, string> = {
  partner_match: "伙伴匹配", partner_data: "伙伴数据读取", demand_profile: "需求画像",
  project_opportunity: "项目机会", recommendation_data: "推荐结果", persistence: "结果保存", interrupted: "异常中断",
};

function errorStageText(value: string | null): string | undefined {
  if (!value) return undefined;
  return value.split(",").map(stage => errorStageLabels[stage] || "后续处理").join("、");
}

export default function TaskList({ admin = false }: { admin?: boolean }) {
  const [items, setItems] = useState<Task[]>([]);
  const [archived, setArchived] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [owner, setOwner] = useState("");
  const [taskType, setTaskType] = useState("");
  const [taskStatus, setTaskStatus] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(nextPage = page) {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({
        status: archived ? "archived" : "active",
        page: String(nextPage),
        pageSize: "20",
      });
      if (keyword.trim()) params.set("keyword", keyword.trim());
      if (taskType) params.set("task_type", taskType);
      if (taskStatus) params.set("taskStatus", taskStatus);
      if (admin && owner.trim()) params.set("owner", owner.trim());
      const response = await apiFetch(`${admin ? "/admin/tasks" : "/agent/tasks"}?${params}`, { cache: "no-store" });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "任务加载失败");
      const data = await response.json() as TaskPage;
      setItems(data.items); setPage(data.page); setTotal(data.total); setTotalPages(data.totalPages);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(1); }, [archived]);

  async function toggleArchive(task: Task) {
    setError(null);
    try {
      const action = task.archivedAt ? "restore" : "archive";
      const response = await apiFetch(`/agent/tasks/${task.id}/${action}`, { method: "PATCH" });
      if (response.ok) {
        tasksChanged();
        void load(items.length === 1 && page > 1 ? page - 1 : page);
      } else {
        setError((await response.json().catch(() => ({}))).detail || "操作失败");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    }
  }

  async function retry(task: Task) {
    if (!confirm("将重新执行该任务未完成的处理步骤，确定继续？")) return;
    setRetryingId(task.id); setError(null);
    try {
      const response = await apiFetch(`/agent/tasks/${task.id}/retry`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "重试失败");
      await load(page);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "重试失败";
      await load(page);
      setError(message);
    } finally {
      setRetryingId(null); tasksChanged();
    }
  }

  return (
    <>
      <section className="card toolbar-card">
        <div className="task-tabs"><button className={!archived ? "active" : ""} onClick={() => setArchived(false)}>进行中</button><button className={archived ? "active" : ""} onClick={() => setArchived(true)}>已归档</button></div>
        <form onSubmit={event => { event.preventDefault(); void load(1); }} className="inline-search task-search">
          <input value={keyword} onChange={event => setKeyword(event.target.value)} placeholder="搜索需求内容" />
          {admin && <input value={owner} onChange={event => setOwner(event.target.value)} placeholder="创建人 / 部门" />}
          <select value={taskType} onChange={event => setTaskType(event.target.value)} aria-label="任务类型"><option value="">全部类型</option><option value="partner_match">伙伴匹配</option><option value="development_plan">发展方案</option></select>
          <select value={taskStatus} onChange={event => setTaskStatus(event.target.value)} aria-label="任务状态">
            <option value="">全部状态</option>
            {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <button>搜索</button>
        </form>
      </section>
      <section className="card">
        {error && <div className="inline-error-actions"><p className="error-text">{error}</p><button className="secondary-btn" onClick={() => void load(page)}>重试</button></div>}
        {loading ? <p>加载中...</p> : items.length === 0 ? <div className="empty-state"><h2>{archived ? "暂无已归档任务" : "暂无任务"}</h2><p>{taskType === "development_plan" ? "暂无发展方案，请前往伙伴服务能力发展中心创建。" : admin ? "当前筛选条件下没有任务。" : "前往开启新任务，完成第一次伙伴匹配。"}</p>{!admin && taskType !== "development_plan" && <Link href="/" className="btn-primary-lg">开启新任务</Link>}</div> : (
          <>
            <div className="table-wrap"><table className="data-table"><thead><tr><th>需求摘要</th><th>任务类型</th>{admin && <><th>创建人</th><th>部门</th></>}<th>状态</th><th>首选伙伴</th><th>推荐数</th><th>机会完整度</th><th>创建时间</th><th>操作</th></tr></thead><tbody>
              {items.map(item => <tr key={item.id}><td className="task-requirement">{item.requirement}</td><td>{item.task_type === "development_plan" ? "发展方案" : "伙伴匹配"}</td>{admin && <><td>{item.ownerName || "-"}</td><td>{item.department || "-"}</td></>}<td>{item.task_type === "development_plan" && item.planPresentation ? <PlanStatus value={item.planPresentation}/> : <span className={`status-badge task-${item.taskStatus}`} title={errorStageText(item.lastErrorStage)}>{item.task_type === "development_plan" && ["matching","enriching"].includes(item.taskStatus) ? "生成中" : statusLabels[item.taskStatus]}</span>}</td><td>{item.topPartner}</td><td>{item.partnerCount}</td><td>{item.completenessScore == null ? "-" : `${item.completenessScore}%`}</td><td>{new Date(item.createdAt).toLocaleString("zh-CN")}</td><td><div className="table-actions"><Link href={`/tasks/${item.id}${admin ? "?from=admin" : ""}`} className="secondary-btn">详情</Link>{item.task_type !== "development_plan" && (item.taskStatus === "partial" || item.taskStatus === "failed") && <button className="secondary-btn" disabled={retryingId === item.id} onClick={() => void retry(item)}>{retryingId === item.id ? "重试中..." : "重试"}</button>}<button className="secondary-btn" onClick={() => void toggleArchive(item)}>{item.archivedAt ? "恢复" : "归档"}</button></div></td></tr>)}
            </tbody></table></div>
            <div className="pagination"><span>共 {total} 条</span><button className="secondary-btn" disabled={page <= 1} onClick={() => void load(page - 1)}>上一页</button><span>第 {page} / {Math.max(1, totalPages)} 页</span><button className="secondary-btn" disabled={page >= totalPages} onClick={() => void load(page + 1)}>下一页</button></div>
          </>
        )}
      </section>
    </>
  );
}
