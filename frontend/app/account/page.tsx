"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, CurrentUser, useAuth } from "../../components/auth-provider";

export default function AccountPage() {
  const { user, refresh, saveSession, logout } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setDisplayName(user?.display_name || ""); }, [user]);

  async function saveProfile(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(null); setMessage(null);
    try {
      const response = await apiFetch("/auth/me", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: displayName }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "保存失败");
      await refresh(); setMessage("个人信息已更新");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); } finally { setSaving(false); }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(null); setMessage(null);
    if (newPassword !== confirmPassword) { setError("两次输入的新密码不一致"); setSaving(false); return; }
    try {
      const response = await apiFetch("/auth/change-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "密码修改失败");
      saveSession(data.access_token, data.user as CurrentUser);
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword(""); setMessage("密码已修改，其他登录状态已失效");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "密码修改失败"); } finally { setSaving(false); }
  }

  async function logoutAll() {
    setError(null);
    try {
      const response = await apiFetch("/auth/logout-all", { method: "POST" });
      if (!response.ok) throw new Error("注销全部登录状态失败");
      logout();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "注销全部登录状态失败");
    }
  }

  return (
    <main className="page">
      <p className="eyebrow">Account</p>
      <h1>个人中心</h1>
      <p className="lead">{user?.must_change_password ? "当前使用的是临时密码，请先设置新密码。" : "查看账号信息并维护个人登录安全。"}</p>
      {user?.must_change_password && <div className="notice-warning">首次登录必须修改临时密码，完成后才能使用其他功能。</div>}
      <div className="content-grid-two">
        <section className="card">
          <h2>账号信息</h2>
          <dl className="detail-list">
            <div><dt>用户名</dt><dd>{user?.username}</dd></div>
            <div><dt>部门</dt><dd>{user?.department || "未设置"}</dd></div>
            <div><dt>角色</dt><dd>{user?.role === "admin" ? "管理员" : "普通用户"}</dd></div>
            <div><dt>状态</dt><dd>正常</dd></div>
            <div><dt>最近登录</dt><dd>{user?.last_login_at ? new Date(user.last_login_at).toLocaleString("zh-CN") : "暂无"}</dd></div>
          </dl>
          <form onSubmit={saveProfile} className="partner-form compact-form">
            <div className="form-row"><label htmlFor="displayName">显示名称</label><input id="displayName" value={displayName} onChange={event => setDisplayName(event.target.value)} required /></div>
            <button disabled={saving}>保存个人信息</button>
          </form>
        </section>
        <section className="card">
          <h2>修改密码</h2>
          <form onSubmit={changePassword} className="partner-form">
            <div className="form-row"><label htmlFor="currentPassword">当前密码</label><input id="currentPassword" type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} required /></div>
            <div className="form-row"><label htmlFor="newPassword">新密码</label><input id="newPassword" type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} minLength={8} required /><small>8～64 位，必须同时包含字母和数字</small></div>
            <div className="form-row"><label htmlFor="confirmPassword">确认新密码</label><input id="confirmPassword" type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} minLength={8} required /></div>
            <button disabled={saving}>修改密码</button>
          </form>
          {!user?.must_change_password && <button type="button" className="secondary-btn danger-outline" onClick={logoutAll}>注销全部登录状态</button>}
        </section>
      </div>
      {message && <p className="success-text">{message}</p>}
      {error && <p className="error-text">{error}</p>}
    </main>
  );
}
