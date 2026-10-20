"use client";

import { useEffect, useRef, useState } from "react";
import { IdentityCredential } from "./identity-credential";

export function SwitchIdentityDialog({ initialTarget, onCancel, onSwitch, onCreate }: { initialTarget: string; onCancel: () => void; onSwitch: (source: string) => Promise<void>; onCreate: () => Promise<void> }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [target, setTarget] = useState(initialTarget), [busy, setBusy] = useState(false), [error, setError] = useState(""), [confirming, setConfirming] = useState(false);
  useEffect(() => { dialog.current?.showModal(); return () => { dialog.current?.close(); }; }, []);
  useEffect(() => { setTarget(initialTarget); setError(""); setConfirming(false); }, [initialTarget]);
  async function submit() {
    if (busy || !target.trim()) return;
    setBusy(true); setError("");
    try { await onSwitch(target); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "暂时无法切换，请重试。"); }
    finally { setBusy(false); }
  }
  async function create() {
    if (busy) return;
    setBusy(true); setError("");
    try { await onCreate(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "暂时无法新建身份，请重试。"); setConfirming(false); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="identity-save-dialog identity-switch-dialog" aria-labelledby="identity-switch-title" onCancel={event => { if (busy) event.preventDefault(); else onCancel(); }}>
    <div className="identity-dialog-heading"><h2 id="identity-switch-title">切换身份</h2><button className="identity-dialog-close" type="button" aria-label="关闭" disabled={busy} onClick={onCancel}>×</button></div>
    <p>先保存当前身份的登录链接，之后可以用它回来。</p>
    <IdentityCredential compact />
    {confirming ? <div className="identity-switch-confirm">
      <p>新建后，这台电脑只会保留新身份。原身份需要靠上方「复制」保存的登录链接找回。</p>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="identity-switch-actions"><button type="button" className="secondary-btn" disabled={busy} onClick={() => { setConfirming(false); setError(""); }}>取消</button><button type="button" disabled={busy} onClick={() => void create()}>{busy ? "正在新建…" : "确定新建"}</button></div>
    </div> : <>
      <form className="identity-switch-form" onSubmit={event => { event.preventDefault(); void submit(); }}>
        <label htmlFor="identity-switch-target">目标登录链接</label>
        <input id="identity-switch-target" value={target} onChange={event => setTarget(event.target.value)} placeholder="粘贴目标登录链接" autoComplete="off" spellCheck={false} maxLength={2048} disabled={busy}/>
        {error && <p className="error-text" role="alert">{error}</p>}
        <div className="identity-switch-actions"><button type="button" className="secondary-btn" disabled={busy} onClick={onCancel}>取消</button><button type="submit" disabled={busy || !target.trim()}>{busy ? "正在切换…" : "切换"}</button></div>
      </form>
      <div className="identity-switch-new"><button type="button" disabled={busy} onClick={() => { setConfirming(true); setError(""); }}>在这台电脑上新建身份</button></div>
    </>}
  </dialog>;
}
