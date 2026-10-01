"use client";

import { useEffect, useRef, useState } from "react";
import { userApiFetch } from "./auth-provider";
import { copyText } from "../lib/copy-text";

export function IdentityCredential() {
  const [key, setKey] = useState("");
  const keyValue = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setError(""); setKey("");
    void (async () => {
      try {
        const response = await userApiFetch("/auth/identity/key", { cache: "no-store" });
        if (!response.ok) throw new Error("身份凭据暂时无法读取，请重试");
        const data = await response.json();
        if (!cancelled) setKey(data.key);
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "读取失败，请重试"); }
    })();
    return () => { cancelled = true; };
  }, [attempt]);
  async function copy() {
    if (await copyText(key, keyValue.current)) { setMessage("Key 已复制"); setError(""); }
    else { setMessage(""); setError("复制失败，Key 已选中，请按 Ctrl+C 手动复制；下载仍可使用。"); }
  }
  function download() {
    const content = `伴飞 Agent 身份凭据\n\n身份 Key：\n${key}\n\n在伴飞身份入口输入此 Key 或导入此文件，可恢复原身份和全部历史。\n请妥善保存，勿分享给他人。\n`;
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "伴飞-身份凭据.txt";
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage("已开始下载凭据");
  }
  return <div className="identity-credential">
    <p>换浏览器、换电脑或清除浏览器数据后，使用此 Key 可继续访问原来的历史。请妥善保存，勿分享给他人。</p>
    <div ref={keyValue} tabIndex={-1} className="identity-key-value" aria-label="当前身份 Key" data-testid="identity-key">{key || "正在读取…"}</div>
    <div className="identity-key-actions">
      <button type="button" disabled={!key} onClick={() => void copy()}>复制 Key</button>
      <button type="button" className="secondary-btn" disabled={!key} onClick={download}>下载凭据 .txt</button>
    </div>
    {message && <p role="status" className="success-text">{message}</p>}
    {error && <p role="alert" className="error-text">{error}<button className="text-btn" type="button" onClick={() => setAttempt(value => value + 1)}>重试</button></p>}
  </div>;
}

export function SaveIdentityDialog({ onClose, onLogin }: { onClose: () => void; onLogin: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); return () => { dialog.current?.close(); }; }, []);
  return <dialog ref={dialog} className="identity-save-dialog" aria-labelledby="identity-save-title" onCancel={onClose}>
    <div className="identity-dialog-heading"><h2 id="identity-save-title">保存你的身份 Key</h2><button type="button" className="identity-dialog-close" aria-label="关闭" onClick={onClose}>×</button></div>
    <p className="identity-dialog-intro">已为你建立身份，当前浏览器会自动登录。</p>
    <IdentityCredential />
    <div className="identity-save-footer"><button type="button" className="secondary-btn" onClick={onClose}>稍后保存</button><button type="button" className="identity-key-login-link" onClick={onLogin}>已有 Key？登录原身份</button></div>
  </dialog>;
}
