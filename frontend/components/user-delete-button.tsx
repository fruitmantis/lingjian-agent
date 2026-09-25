"use client";

import { useState } from "react";
import { adminApiFetch } from "./auth-provider";

type Preview = { allowed: boolean; reason: string; confirmationToken: string | null };

export function UserDeleteButton({ userId, onDeleted }: { userId: string; onDeleted: () => void }) {
  const [confirmationToken, setConfirmationToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function inspect() {
    setBusy(true); setError("");
    try {
      const response = await adminApiFetch(`/admin/users/${userId}/deletion-preview`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "暂时无法删除，请重试");
      const preview: Preview = data;
      if (!preview.allowed || !preview.confirmationToken) throw new Error(preview.reason || "暂时无法删除，请重试");
      setConfirmationToken(preview.confirmationToken);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "暂时无法删除，请重试"); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!confirmationToken || busy) return;
    setBusy(true); setError("");
    try {
      const response = await adminApiFetch(`/admin/users/${userId}`, { method: "DELETE",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmationToken }) });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(typeof data.detail === "string" ? data.detail : "删除失败，请重试");
      }
      onDeleted();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "删除失败，请重试"); }
    finally { setConfirmationToken(null); setBusy(false); }
  }
  return <>
    <button type="button" className="secondary-btn danger-outline" disabled={busy} onClick={() => void inspect()}>删除</button>
    {error && <span className="error-text" role="alert">{error}</span>}
    {confirmationToken && <div className="modal-backdrop"><section className="card modal-card user-delete-dialog" role="dialog" aria-modal="true" aria-label="删除账号" aria-describedby={`delete-account-${userId}`}>
      <p id={`delete-account-${userId}`}>删除后，该账号及身份 Key 将无法使用，历史业务数据仍保留。确定删除？</p>
      <div className="modal-actions">
        <button type="button" className="secondary-btn" disabled={busy} onClick={() => setConfirmationToken(null)}>取消</button>
        <button type="button" disabled={busy} onClick={() => void remove()}>删除账号</button>
      </div>
    </section></div>}
  </>;
}
