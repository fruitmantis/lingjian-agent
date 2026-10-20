"use client";

import { useEffect, useRef, useState } from "react";
import { IdentityCredential } from "./identity-credential";

export function SwitchIdentityDialog({ initialTarget, onCancel, onSwitch }: { initialTarget: string; onCancel: () => void; onSwitch: (source: string) => Promise<void> }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [target, setTarget] = useState(initialTarget), [busy, setBusy] = useState(false), [error, setError] = useState("");
  useEffect(() => { dialog.current?.showModal(); return () => { dialog.current?.close(); }; }, []);
  useEffect(() => { setTarget(initialTarget); setError(""); }, [initialTarget]);
  async function submit() {
    if (busy || !target.trim()) return;
    setBusy(true); setError("");
    try { await onSwitch(target); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "暂时无法切换，请重试。"); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="identity-save-dialog identity-switch-dialog" aria-labelledby="identity-switch-title" onCancel={event => { if (busy) event.preventDefault(); else onCancel(); }}>
    <div className="identity-dialog-heading"><h2 id="identity-switch-title">切换身份</h2><button className="identity-dialog-close" type="button" aria-label="关闭" disabled={busy} onClick={onCancel}>×</button></div>
    <p>先保存当前身份的登录链接，之后可以用它回来。</p>
    <IdentityCredential compact />
    <form className="identity-switch-form" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <label htmlFor="identity-switch-target">目标登录链接</label>
      <input id="identity-switch-target" value={target} onChange={event => setTarget(event.target.value)} placeholder="粘贴目标登录链接，也支持已有 Key" autoComplete="off" spellCheck={false} maxLength={2048} disabled={busy}/>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="identity-switch-actions"><button type="button" className="secondary-btn" disabled={busy} onClick={onCancel}>取消</button><button type="submit" disabled={busy || !target.trim()}>{busy ? "正在切换…" : "切换"}</button></div>
    </form>
  </dialog>;
}
