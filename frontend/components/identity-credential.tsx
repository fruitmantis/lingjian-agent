"use client";

import { useEffect, useRef, useState } from "react";
import { userApiFetch, useAuth } from "./auth-provider";
import { copyText } from "../lib/copy-text";

export function IdentityCredential({ onboarding = false, compact = false, onSwitch }: { onboarding?: boolean; compact?: boolean; onSwitch?: () => void }) {
  const [link, setLink] = useState("");
  const linkValue = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [manual, setManual] = useState(false);
  useEffect(() => {
    if (!manual || !linkValue.current) return;
    const selection = window.getSelection(), range = document.createRange();
    range.selectNodeContents(linkValue.current); selection?.removeAllRanges(); selection?.addRange(range); linkValue.current.focus();
  }, [manual]);
  useEffect(() => {
    let cancelled = false;
    setError(""); setLink("");
    void (async () => {
      try {
        const response = await userApiFetch("/auth/identity/key", { cache: "no-store" });
        if (!response.ok) throw new Error("登录链接暂时无法读取，请重试");
        const data = await response.json();
        if (!cancelled) { setLink(`${window.location.origin}/#k=${encodeURIComponent(data.key)}`); }
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "读取失败，请重试"); }
    })();
    return () => { cancelled = true; };
  }, [attempt]);
  async function copy() {
    if (await copyText(link, linkValue.current)) { setMessage("登录链接已复制"); setError(""); }
    else { setManual(true); setMessage(""); setError("复制失败，登录链接已选中，请按 Ctrl+C 手动复制。"); }
  }
  return <div className="identity-credential">
    {!compact && !onboarding && <p>使用登录链接，可在其他电脑或浏览器继续使用当前身份。</p>}
    {compact && <div className="identity-copy-heading"><h3>{onboarding ? "收藏链接，下次继续使用" : "换设备也能接着用"}</h3><p>{onboarding ? "下次通过此链接进入，即可找回身份和查询历史记录；无需找回可忽略。" : "保存这条链接，换电脑或浏览器后可继续使用。"}</p></div>}
    <div className={compact ? "identity-copy-strip" + (manual ? " identity-copy-manual" : "") : "identity-link-box"}>
      <div ref={linkValue} tabIndex={-1} className="identity-key-value" aria-label="当前登录链接" data-testid="identity-key">{link || "正在读取…"}</div>
      {compact ? <button type="button" aria-label={onboarding ? (message === "登录链接已复制" ? "已复制" : "复制登录链接") : undefined} disabled={!link} onClick={() => void copy()}>{message === "登录链接已复制" ? "已复制" : onboarding ? "复制" : "复制登录链接"}</button> : <button type="button" className="identity-link-copy" aria-label="复制登录链接" title="复制登录链接" disabled={!link} onClick={() => void copy()}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3"/></svg>
      </button>}
    </div>
    {message && <p role="status" className="success-text">{message}</p>}
    {error && <p role="alert" className="error-text">{error}<button className="text-btn" type="button" onClick={() => setAttempt(value => value + 1)}>重试</button></p>}
    {onboarding && compact && <p className="identity-link-private">请勿分享给他人 · 可保存到收藏夹或发给自己</p>}
    {!compact && <p className="identity-link-private">请勿分享给他人</p>}
    {!onboarding && !compact && onSwitch && <div className="identity-key-actions"><button type="button" className="secondary-btn" onClick={onSwitch}>切换身份</button></div>}
  </div>;
}

export function SaveIdentityDialog({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { user, refresh } = useAuth();
  const [employeeNumber, setEmployeeNumber] = useState(user?.employee_number || "");
  const [saving, setSaving] = useState(false), [error, setError] = useState("");
  useEffect(() => { dialog.current?.showModal(); dialog.current?.focus(); return () => { dialog.current?.close(); }; }, []);
  async function start() {
    if (saving) return;
    const number = employeeNumber.trim();
    if (!number) { onClose(); return; }
    setSaving(true); setError("");
    try {
      const response = await userApiFetch("/auth/me", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ employee_number: number }) });
      if (!response.ok) throw new Error("工号暂时无法保存，请重试，也可以清空后跳过。");
      await refresh(); onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "暂时无法保存"); }
    finally { setSaving(false); }
  }
  return <dialog ref={dialog} tabIndex={-1} className="identity-save-dialog identity-welcome-dialog" aria-labelledby="identity-save-title" onCancel={event => { if (saving) event.preventDefault(); else onClose(); }}>
    <WelcomeBrand />
    <section className="welcome-panel">
      <div className="welcome-inner">
        <div className="welcome-eyebrow">首次使用</div>
        <h2 id="identity-save-title">欢迎使用伴飞</h2>
        <p className="identity-welcome-subtitle">找到合适的伙伴，把合作推进下去</p>
        <div className="identity-employee-sentence"><label htmlFor="welcome-employee">请输入工号</label><input id="welcome-employee" aria-label="工号（可选）" placeholder="例如 a00123456" autoComplete="off" value={employeeNumber} onChange={event => setEmployeeNumber(event.target.value)} maxLength={64} disabled={saving}/></div>
        <p className="identity-employee-help">可跳过，之后在个人中心补充</p>
        {error && <p className="error-text" role="alert">{error}</p>}
        <div className="identity-welcome-link"><IdentityCredential onboarding compact /></div>
        <div className="identity-save-footer"><button type="button" disabled={saving} onClick={() => void start()}>{saving ? "正在保存…" : "开始使用伴飞"}</button></div>
      </div>
    </section>
  </dialog>;
}

export function WelcomeBrand() {
  return (
    <aside className="welcome-brand" aria-hidden="true">
      <svg className="welcome-paths" viewBox="0 0 440 220" fill="none">
        <path d="M-20,178 C80,178 152,148 254,118" stroke="#e7c2c7" strokeWidth="1.5"/>
        <path d="M-20,220 C104,220 178,168 254,118" stroke="#e7c2c7" strokeWidth="1.5"/>
        <circle cx="254" cy="118" r="5" fill="#dda3a9"/>
        <circle cx="94" cy="170" r="3.5" fill="#efd0d4"/>
        <circle cx="56" cy="210" r="2.5" fill="#efd0d4"/>
      </svg>
      <div className="welcome-logo"><span className="welcome-mark">◈</span><span className="welcome-wordmark">伴飞</span></div>
      <div className="welcome-brand-main">
        <h3>找伙伴，<br/>促发展</h3>
        <p>按项目需求，发现值得接洽的伙伴。<br/>结合已有基础，梳理发展方向与学习资源。</p>
      </div>
      <div className="welcome-brand-foot">内部试点 · 仅限公司内网访问</div>
    </aside>
  );
}

