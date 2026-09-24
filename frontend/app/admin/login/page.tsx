"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth, PASSWORD_CHANGE_PATH } from "../../../components/auth-provider";
import { LingjianMark } from "../../../components/ui-icons";
export default function AdminLogin() {
  const { saveSession } = useAuth(); const router = useRouter();
  const [username, setUsername] = useState(""); const [password, setPassword] = useState("");
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function login(event: FormEvent) { event.preventDefault(); if (busy) return; setBusy(true); setError("");
    try { const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/auth/admin/login`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }), signal: AbortSignal.timeout(30000) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "登录失败");
      saveSession(data.access_token, data.user); router.replace(data.user.must_change_password ? PASSWORD_CHANGE_PATH : "/admin");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "登录失败"); } finally { setBusy(false); }
  }
  return <main className="password-change-page"><section className="login-card password-change-card">
    <div className="login-brand-lockup"><LingjianMark /><span>伴飞 Agent</span></div><h1>管理员登录</h1>
    <form onSubmit={login} className="partner-form"><div className="form-row"><label htmlFor="username">用户名</label><input id="username" autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} /></div>
      <div className="form-row"><label htmlFor="password">密码</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></div>
      {error && <p role="alert" className="error-text">{error}</p>}<button className="login-submit" disabled={busy}>{busy ? "登录中…" : "登录"}</button></form>
    <a className="admin-login-return" href="/">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m10 6-6 6 6 6M4 12h16" />
      </svg>
      <span>返回伴飞</span>
    </a>
  </section></main>;
}
