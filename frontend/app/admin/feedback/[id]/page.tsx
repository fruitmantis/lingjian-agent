"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "../../../../components/auth-provider";
import { responseError } from "../../../../lib/api-request";

type Attachment = { id: string; filename: string };
type Issue = { id: string; created_at: string; submitter: string; description: string; status: "pending" | "resolved"; attachments: Attachment[] };
function Screenshot({ issueId, attachment }: { issueId: string; attachment: Attachment }) {
  const [url, setUrl] = useState(""), [error, setError] = useState("");
  useEffect(() => {
    let live = true, objectUrl = ""; setUrl(""); setError("");
    async function load() {
      try {
        const response = await apiFetch(`/admin/feedback/${issueId}/attachments/${attachment.id}`, { cache: "no-store" });
        if (!response.ok) throw await responseError(response, "截图加载失败");
        const blob = await response.blob(); if (!live) return;
        objectUrl = URL.createObjectURL(blob); setUrl(objectUrl);
      } catch (reason) { if (live) setError((reason as Error).message); }
    }
    void load(); return () => { live = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [issueId, attachment.id]);
  return <figure className="feedback-thumbnail">{error ? <p role="alert">{error}</p> : url ? <a href={url} target="_blank" rel="noopener noreferrer" aria-label={`查看原图：${attachment.filename}`}>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={url} alt={attachment.filename} />
  </a> : <p>正在加载截图…</p>}<figcaption>{attachment.filename}{url && <span className="muted">点击查看原图</span>}</figcaption></figure>;
}
export default function FeedbackDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [issue, setIssue] = useState<Issue | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let live = true;
    async function load() {
      try {
        const response = await apiFetch(`/admin/feedback/${id}`, { cache: "no-store" });
        if (!response.ok) throw await responseError(response, "问题加载失败");
        const data = await response.json(); if (live) setIssue(data);
      } catch (reason) { if (live) setError((reason as Error).message); }
    }
    void load(); return () => { live = false; };
  }, [id]);
  async function toggle() {
    if (!issue || busy) return;
    const status = issue.status === "pending" ? "resolved" : "pending";
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await apiFetch(`/admin/feedback/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
      if (!response.ok) throw await responseError(response, "状态更新失败");
      setIssue({ ...issue, status }); setNotice("状态已更新");
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="feedback-page"><Link href="/admin/feedback">← 返回问题清单</Link><h1>问题详情</h1>
    {error && <p role="alert" className="feedback-error">{error}</p>}
    {!issue ? !error && <p role="status">正在加载…</p> : <section className="card feedback-form">
      <div className="feedback-detail-heading"><p className="muted">{issue.submitter} · {new Date(issue.created_at).toLocaleString("zh-CN", { hour12: false })}</p>
        <span className={`feedback-status ${issue.status}`}>{issue.status === "pending" ? "待处理" : "已处理"}</span></div>
      <p className="feedback-description">{issue.description}</p>
      <div className="feedback-images">{issue.attachments.map(attachment => <Screenshot key={attachment.id} issueId={id} attachment={attachment} />)}</div>
      {notice && <p role="status">{notice}</p>}
      <div><button disabled={busy} onClick={() => void toggle()}>{busy ? "正在更新…" : issue.status === "pending" ? "标记为已处理" : "恢复为待处理"}</button></div>
    </section>}
  </div>;
}
