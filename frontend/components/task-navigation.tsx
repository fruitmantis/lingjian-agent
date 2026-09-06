"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { apiFetch, useAuth } from "./auth-provider";

export const TASKS_CHANGED = "lingjian:tasks-changed";
export const NEW_TASK = "lingjian:new-task";
export const taskLabels: Record<string, string> = {
  matching: "匹配中", enriching: "处理中", ready: "已完成", partial: "部分完成", failed: "失败",
  submitting: "提交中", unconfirmed: "提交未确认",
};
import {PlanStatus,type PlanPresentation} from "./plan-status";

export type NavigationTask = { planPresentation?: PlanPresentation | null; task_type?: string; id: string; requirement: string; createdAt: string; taskStatus: string; archivedAt?: string | null };
type PendingTask = NavigationTask & { taskStatus: "submitting" | "unconfirmed" };
export function tasksChanged(task?: NavigationTask) {
  window.dispatchEvent(new CustomEvent(TASKS_CHANGED, { detail: task }));
}
function newTaskId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // getRandomValues also works on internal HTTP origins without randomUUID.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
const NavigationContext = createContext<{
  pending: PendingTask[];
  submit: (requirement: string) => Promise<string>;
  confirm: (id: string) => Promise<void>;
} | null>(null);
export function useTaskNavigation() {
  const context = useContext(NavigationContext);
  if (!context) throw new Error("TaskNavigationProvider is required");
  return context;
}

export function TaskNavigationProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  // Remount on identity changes so late responses cannot populate another user's sidebar.
  return <UserTaskNavigation key={user?.id || "anonymous"} userId={user?.id}>{children}</UserTaskNavigation>;
}
function UserTaskNavigation({ userId, children }: { userId?: string; children: React.ReactNode }) {
  const [pending, setPending] = useState<PendingTask[]>([]);
  const alive = useRef(true);
  const key = userId ? `lingjian:pending-tasks:${userId}` : null;
  const pendingRef = useRef(pending);
  function update(next: PendingTask[]) {
    if (!alive.current) return;
    pendingRef.current = next;
    setPending(next);
    // Store identifiers only; requirements remain in memory and the authenticated backend.
    try { if (key) sessionStorage.setItem(key, JSON.stringify(next.map(({ id, createdAt }) => ({ id, createdAt })))); } catch { /* storage is optional */ }
  }
  async function check(id: string): Promise<boolean> {
    try {
      const response = await apiFetch(`/agent/tasks/${id}`, { cache: "no-store" });
      if (!response.ok) return false;
      const task = await response.json() as NavigationTask;
      if (!alive.current) return false;
      tasksChanged(task);
      update(pendingRef.current.filter(item => item.id !== id));
      return true;
    } catch { return false; }
  }
  useEffect(() => {
    alive.current = true;
    if (key) {
      try {
        const saved: unknown = JSON.parse(sessionStorage.getItem(key) || "[]");
        if (Array.isArray(saved)) {
          const restored: PendingTask[] = saved.filter(item => typeof item?.id === "string" && /^[a-f0-9-]{36}$/i.test(item.id) && typeof item.createdAt === "string")
            .map(item => ({ id: item.id, createdAt: item.createdAt, requirement: "待确认的提交", taskStatus: "unconfirmed" }));
          update(restored);
          restored.forEach(item => { void check(item.id); });
        }
      } catch { /* invalid session storage is ignored */ }
    }
    return () => { alive.current = false; };
  }, [key]);

  async function submit(requirement: string) {
    const id = newTaskId();
    const task: PendingTask = { id, requirement: requirement.trim(), createdAt: new Date().toISOString(), taskStatus: "submitting" };
    update([task, ...pendingRef.current]);
    let rejected = false;
    try {
      const response = await apiFetch("/agent/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requestId: id, requirement: task.requirement }) });
      if (!response.ok) {
        rejected = response.status >= 400 && response.status < 500 && response.status !== 408;
        throw new Error("任务提交失败，请检查输入或稍后重试。");
      }
      const result = await response.json();
      if (alive.current) {
        tasksChanged({ ...task, taskStatus: result.taskStatus });
        update(pendingRef.current.filter(item => item.id !== id));
      }
      return id;
    } catch (reason) {
      if (rejected) {
        update(pendingRef.current.filter(item => item.id !== id));
        throw reason;
      }
      if (await check(id)) return id;
      update(pendingRef.current.map(item => item.id === id ? { ...item, taskStatus: "unconfirmed" } : item));
      throw new Error("提交结果暂未确认，请在左侧核对原任务，避免重复提交。");
    }
  }
  return <NavigationContext.Provider value={{ pending, submit, confirm: async id => { await check(id); } }}>{children}</NavigationContext.Provider>;
}

const orderTasks = (items: NavigationTask[]) => [...new Map(items.map(item => [item.id, item])).values()]
  .sort((a, b) => b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id));
const listUrl = "/agent/tasks?status=active&pageSize=10";
async function readPage(url: string): Promise<{ items: NavigationTask[]; total: number }> {
  const response = await apiFetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("任务列表暂未更新");
  return response.json();
}

export function TaskSidebar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const selectedId = pathname.match(/^\/tasks\/([^/]+)$/)?.[1] || (pathname === "/" ? searchParams.get("task") || undefined : undefined);
  return <UserTaskSidebar key={user?.id} pathname={pathname} selectedId={selectedId} />;
}
function UserTaskSidebar({ pathname, selectedId }: { pathname: string; selectedId?: string }) {
  const { pending, confirm } = useTaskNavigation();
  const [items, setItems] = useState<NavigationTask[]>([]);
  const [selected, setSelected] = useState<NavigationTask | null>(null);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState<string | null>(null);
  const state = useRef({ items: [] as NavigationTask[], cursor: null as NavigationTask | null, initialized: false, busy: false });
  const alive = useRef(true);
  const scroll = useRef<HTMLDivElement>(null);
  const anchor = useRef<{ id: string; offset: number } | null>(null);

  function commit(next: NavigationTask[]) {
    if (!alive.current) return;
    const container = scroll.current;
    if (container && container.scrollTop > 0) {
      const top = container.getBoundingClientRect().top;
      const first = Array.from(container.querySelectorAll<HTMLElement>("[data-task-id]")).find(el => el.getBoundingClientRect().bottom > top);
      if (first) anchor.current = { id: first.dataset.taskId!, offset: first.getBoundingClientRect().top - top };
    }
    state.current.items = orderTasks(next);
    setItems(state.current.items);
  }
  useLayoutEffect(() => {
    const container = scroll.current;
    const saved = anchor.current;
    if (container && saved) {
      const element = Array.from(container.querySelectorAll<HTMLElement>("[data-task-id]")).find(el => el.dataset.taskId === saved.id);
      if (element) container.scrollTop += element.getBoundingClientRect().top - container.getBoundingClientRect().top - saved.offset;
    }
    anchor.current = null;
  }, [items]);

  async function refresh(append = false) {
    if (state.current.busy || !alive.current) return;
    state.current.busy = true;
    setBusy(true);
    try {
      const initial = !state.current.initialized;
      const cursor = state.current.cursor;
      const query = append && cursor ? `&${new URLSearchParams({ beforeCreatedAt: cursor.createdAt, beforeId: cursor.id })}` : "";
      const data = await readPage(listUrl + query);
      if (!alive.current) return;
      if (initial || append) {
        // Cursor changes only when loading older records, never on status refreshes.
        state.current.cursor = data.items.at(-1) || cursor;
        state.current.initialized = true;
        setMore(data.total > data.items.length);
        commit([...state.current.items, ...data.items]);
      } else {
        const headIds = new Set(data.items.map(item => item.id));
        const olderIds = state.current.items.filter(item => !headIds.has(item.id)).map(item => item.id);
        const older: NavigationTask[] = [];
        for (let index = 0; index < olderIds.length; index += 100) {
          const params = new URLSearchParams({ status: "active", pageSize: "100" });
          olderIds.slice(index, index + 100).forEach(id => params.append("ids", id));
          older.push(...(await readPage(`/agent/tasks?${params}`)).items);
        }
        if (!alive.current) return;
        // Preserve submissions confirmed while the refresh request was in flight.
        const queried = new Set([...headIds, ...olderIds]);
        const added = state.current.items.filter(item => !queried.has(item.id));
        commit([...older, ...data.items, ...added]);
        if (!state.current.cursor && data.items.length) state.current.cursor = data.items.at(-1)!;
        setMore(data.total > state.current.items.length);
      }
      setError("");
    } catch { if (alive.current) setError("任务列表暂未更新，已保留上次状态。"); }
    finally { state.current.busy = false; if (alive.current) setBusy(false); }
  }
  useEffect(() => {
    alive.current = true;
    void refresh();
    const changed = (event: Event) => {
      const task = (event as CustomEvent<NavigationTask | undefined>).detail;
      if (task) commit(task.archivedAt ? state.current.items.filter(item => item.id !== task.id) : [...state.current.items.filter(item => item.id !== task.id), task]);
      void refresh();
    };
    const visible = () => { if (!document.hidden) void refresh(); };
    const timer = window.setInterval(visible, 4000);
    window.addEventListener(TASKS_CHANGED, changed);
    document.addEventListener("visibilitychange", visible);
    return () => { alive.current = false; clearInterval(timer); window.removeEventListener(TASKS_CHANGED, changed); document.removeEventListener("visibilitychange", visible); };
  }, []);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    setSelected(null);
    async function readSelected() {
      if (!selectedId) return;
      try {
        const response = await apiFetch(`/agent/tasks/${selectedId}`, { cache: "no-store" });
        if (response.ok) {
          const data = await response.json();
          if (!cancelled) {
            setSelected(data);
            if (["matching", "enriching"].includes(data.taskStatus)) timer = setTimeout(readSelected, 4000);
          }
        }
      } catch { if (!cancelled) timer = setTimeout(readSelected, 4000); }
    }
    void readSelected();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [selectedId]);

  function row(task: NavigationTask) {
    return <Link key={task.id} href={`/tasks/${task.id}`} data-task-id={task.id} className={`sidebar-task-item ${selectedId === task.id ? "active" : ""}`} aria-current={selectedId === task.id ? "page" : undefined} title={task.requirement}>
      <strong>{task.requirement}</strong><span>{task.task_type === "development_plan" && task.planPresentation ? <PlanStatus value={task.planPresentation}/> : <em className={`task-state task-${task.taskStatus}`}>{task.task_type === "development_plan" && ["matching","enriching"].includes(task.taskStatus) ? "生成中" : taskLabels[task.taskStatus] || "状态待确认"}</em>}<time>{new Date(task.createdAt).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })}</time></span>
    </Link>;
  }
  return <div className="sidebar-task-section">
    <Link href="/tasks" className={`sidebar-all-tasks ${pathname === "/tasks" ? "active" : ""}`} aria-current={pathname === "/tasks" ? "page" : undefined}>全部任务<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg></Link>
    <div className="sidebar-task-list" ref={scroll} aria-label="最近任务">
      {pending.filter(task => !items.some(item => item.id === task.id)).map(task => <div key={task.id} className="sidebar-task-item pending-task" data-task-id={task.id}>
        <strong title={task.requirement}>{task.requirement}</strong><span><em>{taskLabels[task.taskStatus]}</em>{task.taskStatus === "unconfirmed" && <button type="button" className="sidebar-check-task" disabled={checking === task.id} onClick={async () => { setChecking(task.id); await confirm(task.id); setChecking(null); }}>{checking === task.id ? "核对中" : "核对任务"}</button>}</span>
      </div>)}
      {selected && !items.some(item => item.id === selected.id) && <div className="sidebar-selected-task"><small>当前查看</small>{row(selected)}</div>}
      {items.map(row)}
      {!items.length && !pending.length && !error && <p className="sidebar-task-empty">{busy ? "加载中…" : "暂无任务"}</p>}
      {error && <div className="sidebar-task-empty" role="status">{error}<button type="button" className="sidebar-load-more" disabled={busy} onClick={() => void refresh()}>重新加载</button></div>}
      {more && <button type="button" className="sidebar-load-more" disabled={busy} onClick={() => void refresh(true)}>{busy ? "加载中…" : "加载更多"}</button>}
    </div>
  </div>;
}
