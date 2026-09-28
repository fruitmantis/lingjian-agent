"use client";
import Link from "next/link";
import { Pagination } from "@/components/pagination";
import { useEffect, useState } from "react";
import { adminApiFetch as apiFetch } from "../../../components/auth-provider";
import { responseError } from "../../../lib/api-request";

type Issue = { id: string; created_at: string; submitter: string; summary: string; screenshot_count: number; status: "pending" | "resolved" };
export default function AdminFeedbackPage() {
  const [items, setItems] = useState<Issue[]>([]), [total, setTotal] = useState(0), [offset, setOffset] = useState(0);
  const [error, setError] = useState(""), [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true; setLoading(true); setError("");
    async function load() {
      try {
        const response = await apiFetch(`/admin/feedback?limit=30&offset=${offset}`, { cache: "no-store" });
        if (!response.ok) throw await responseError(response, "问题列表加载失败");
        const data = await response.json(); if (live) { setItems(data.items); setTotal(data.total); }
      } catch (reason) { if (live) setError((reason as Error).message); }
      finally { if (live) setLoading(false); }
    }
    void load(); return () => { live = false; };
  }, [offset]);
  return <div className="page feedback-admin"><h1>问题反馈</h1>
    {error && <p role="alert" className="feedback-error">{error}</p>}
    <div className="card">
      {loading ? <p role="status">正在加载…</p> : error ? null : !items.length ? <p className="muted">暂无问题反馈</p> : <>
        <div className="feedback-table-wrap"><table className="data-table"><thead><tr><th>提交时间</th><th>提交人</th><th>问题摘要</th><th>截图数量</th><th>状态</th></tr></thead>
          <tbody>{items.map(item => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString("zh-CN", { hour12: false })}</td><td>{item.submitter}</td>
            <td className="feedback-summary"><Link href={`/admin/feedback/${item.id}`}>{item.summary}</Link></td><td>{item.screenshot_count}</td>
            <td><span className={`feedback-status ${item.status}`}>{item.status === "pending" ? "待处理" : "已处理"}</span></td></tr>)}</tbody>
        </table></div>

      </>}
      {!loading && !error && <Pagination label="问题反馈分页" page={Math.floor(offset / 30) + 1} total={total} pageSize={30} onPageChange={next => setOffset((next - 1) * 30)}/>}
    </div>
  </div>;
}
