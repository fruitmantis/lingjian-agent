"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { adminApiFetch as apiFetch, useAuth, type CurrentUser } from "../../../components/auth-provider";
import { LingjianMark } from "../../../components/ui-icons";
import { responseError } from "../../../lib/api-request";

export default function ChangePasswordPage() {
  const { user, saveSession, logout } = useAuth();
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    setError("");
    if (newPassword !== confirmation) { setError("两次输入的新密码不一致"); return; }
    submitting.current = true; setSaving(true);
    try {
      const response = await apiFetch("/auth/change-password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (!response.ok) throw await responseError(response, "密码修改失败");
      const data = await response.json() as { access_token: string; user: CurrentUser };
      saveSession(data.access_token, data.user);
      setCurrentPassword(""); setNewPassword(""); setConfirmation("");
      router.replace("/admin");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "密码修改失败，请重试"); }
    finally { submitting.current = false; setSaving(false); }
  }

  return <main className="password-change-page">
    <section className="login-card password-change-card" aria-labelledby="password-change-title">
      <div className="login-brand-lockup"><LingjianMark /><span>伴飞 Agent</span></div>
      <div className="login-heading"><h1 id="password-change-title">请先修改密码</h1>
        <p>首次登录或密码重置后，需要设置新密码才能继续使用伴飞。</p>
      </div>
      <p className="password-change-account">当前账号：{user?.username}</p>
      <form onSubmit={submit} className="partner-form">
        <div className="form-row"><label htmlFor="current-password">当前密码</label>
          <input id="current-password" type="password" autoComplete="current-password" autoFocus required disabled={saving}
            value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} placeholder="请输入本次登录使用的密码" />
        </div>
        <div className="form-row"><label htmlFor="new-password">新密码</label>
          <input id="new-password" type="password" autoComplete="new-password" required minLength={8} maxLength={64} disabled={saving}
            value={newPassword} onChange={event => setNewPassword(event.target.value)} aria-describedby="password-requirements" />
          <small id="password-requirements">8～64 位，必须同时包含字母和数字，且与当前密码不同。</small>
        </div>
        <div className="form-row"><label htmlFor="confirm-password">确认新密码</label>
          <input id="confirm-password" type="password" autoComplete="new-password" required minLength={8} maxLength={64} disabled={saving}
            value={confirmation} onChange={event => setConfirmation(event.target.value)} />
        </div>
        {error && <p role="alert" className="error-text">{error}</p>}
        <button type="submit" className="login-submit" disabled={saving}>{saving ? "正在修改…" : "修改密码并进入"}</button>
        <button type="button" className="secondary-btn" onClick={logout} disabled={saving}>退出登录</button>
      </form>
    </section>
  </main>;
}
