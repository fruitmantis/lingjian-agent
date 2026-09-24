"use client";

import { useState } from "react";
import { adminApiFetch } from "./auth-provider";

type Count = { key: string; label: string; count: number };
type Preview = {
  userId: string; displayName: string; allowed: boolean; reason: string; retentionDays: number;
  lastActiveAt: string | null; eligibleAfter: string | null; privateData: Count[];
  publicReferences: Count[]; credentialCount: number; retainedAuditCount: number;
  confirmationToken: string | null;
};

export function UserDeleteButton({ userId, onDeleted }: { userId: string; onDeleted: () => void }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  async function inspect() {
    setOpen(true); setBusy(true); setError(""); setPreview(null);
    try {
      const response = await adminApiFetch(`/admin/users/${userId}/deletion-preview`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "关联数据加载失败");
      setPreview(data);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "关联数据加载失败"); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!preview?.allowed || !preview.confirmationToken || busy) return;
    setBusy(true); setError("");
    try {
      const response = await adminApiFetch(`/admin/users/${userId}`, { method: "DELETE",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmationToken: preview.confirmationToken }) });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setPreview(null);
        throw new Error(typeof data.detail === "string" ? data.detail : "删除失败，请重新查看关联数据");
      }
      setOpen(false); setPreview(null); onDeleted();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "删除失败"); }
    finally { setBusy(false); }
  }
  return <>
    <button type="button" className="secondary-btn danger-outline" disabled={busy} onClick={() => void inspect()}>删除</button>
    {open && <div className="modal-backdrop"><section className="card modal-card user-delete-dialog" role="dialog" aria-modal="true" aria-label="删除普通用户">
      <h2>删除普通用户</h2>
      {busy && !preview && <p role="status">正在检查关联数据…</p>}
      {preview && <>
        <p><strong>{preview.displayName}</strong></p>
        <p className="meta-text">最后使用：{preview.lastActiveAt ? new Date(preview.lastActiveAt).toLocaleString("zh-CN") : "未知"}</p>
        <dl className="detail-list">
          <div><dt>身份凭据</dt><dd>{preview.credentialCount} 条</dd></div>
          {preview.privateData.length ? preview.privateData.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.count} 条</dd></div>) : <div><dt>个人业务历史</dt><dd>0 条</dd></div>}
          {preview.publicReferences.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.count} 条（阻止删除）</dd></div>)}
          <div><dt>保留认证审计</dt><dd>{preview.retainedAuditCount} 条</dd></div>
        </dl>
        <p>{preview.reason}</p>
        {preview.allowed ? <p className="error-text">删除后无法恢复，该身份原有凭据将失效。</p> : preview.eligibleAfter && <p className="meta-text">若不再使用，最早可清理时间：{new Date(preview.eligibleAfter).toLocaleString("zh-CN")}。公共引用仍会阻止删除。</p>}
      </>}
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="modal-actions">
        <button type="button" className="secondary-btn" disabled={busy} onClick={() => setOpen(false)}>取消</button>
        {!preview && !busy && <button type="button" className="secondary-btn" onClick={() => void inspect()}>重新检查</button>}
        {preview?.allowed && <button type="button" disabled={busy} onClick={() => void remove()}>{busy ? "删除中…" : "确认永久删除"}</button>}
      </div>
    </section></div>}
  </>;
}
