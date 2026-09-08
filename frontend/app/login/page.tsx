"use client";

import { LingjianMark } from "../../components/ui-icons";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { CurrentUser, useAuth } from "../../components/auth-provider";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type LoginMode = "login" | "apply";

export default function LoginPage() {
  const router = useRouter();
  const { saveSession } = useAuth();
  const [mode, setMode] = useState<LoginMode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [application, setApplication] = useState({
    username: "", display_name: "", department: "", employee_id: "", email: "", reason: "", password: "", confirmPassword: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function switchMode(nextMode: LoginMode) {
    setMode(nextMode);
    setError(null);
    setSuccess(null);
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setLoading(true); setError(null); setSuccess(null);
    try {
      const response = await fetch(`${apiBaseUrl}/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }),
        signal: AbortSignal.timeout(30_000),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `登录失败（${response.status}）`);
      }
      const data = await response.json();
      saveSession(data.access_token, data.user as CurrentUser);
      router.push(data.user.must_change_password ? "/account?changePassword=1" : "/");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  async function submitApplication(event: FormEvent) {
    event.preventDefault();
    setError(null); setSuccess(null);
    if (application.password !== application.confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/auth/user-applications`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: application.username,
          display_name: application.display_name,
          department: application.department,
          employee_id: application.employee_id.trim(),
          email: application.email.trim(),
          reason: application.reason || null,
          password: application.password,
        }),
        signal: AbortSignal.timeout(30_000),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请检查填写的信息，确保工号、邮箱和其他必填项有效");
      setSuccess("账号申请已提交。管理员批准后，可使用申请时设置的密码首次登录，并按提示完成一次密码更新。");
      setApplication({ username: "", display_name: "", department: "", employee_id: "", email: "", reason: "", password: "", confirmPassword: "" });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "申请提交失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-brand-panel">
        <div className="login-brand-content">
          <div className="login-brand-lockup"><LingjianMark/><h1>伴飞 Agent</h1></div>
          <p>面向公司内部人员的伙伴能力洞察与项目需求匹配助手。</p>
          <div className="login-feature-list">
            <span>伙伴能力与案例查询</span>
            <span>项目需求智能匹配</span>
            <span>个人任务持续跟进</span>
          </div>
        </div>
      </section>
      <section className="login-form-panel">
        <div className={`login-card ${mode === "apply" ? "application-card" : ""}`}>
          {mode === "login" ? (
            <>
              <div className="login-heading"><h2>欢迎回来</h2></div>
              <form onSubmit={handleLogin} className="partner-form">
                <div className="form-row"><label htmlFor="username">用户名</label><input id="username" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required placeholder="请输入用户名" /></div>
                <div className="form-row"><label htmlFor="password">密码</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required placeholder="请输入密码" /></div>
                <button type="submit" className="login-submit" disabled={loading}>{loading ? "登录中..." : "登录"}</button>
              </form>
              <p className="login-help">还没有账号？<button type="button" onClick={() => switchMode("apply")}>注册</button></p>
            </>
          ) : (
            <>
              <div className="login-heading"><h2>注册</h2><p>填写基本信息并设置首次登录密码，审批通过后需更新密码</p></div>
              <form onSubmit={submitApplication} className="form-grid application-form">
                <div className="form-row"><label htmlFor="applyName">姓名</label><input id="applyName" value={application.display_name} onChange={event => setApplication(current => ({ ...current, display_name: event.target.value }))} required maxLength={100} placeholder="请输入姓名" /></div>
                <div className="form-row"><label htmlFor="applyEmployeeId">工号</label><input id="applyEmployeeId" value={application.employee_id} onChange={event => setApplication(current => ({ ...current, employee_id: event.target.value }))} required maxLength={50} placeholder="请输入工号" /></div>
                <div className="form-row"><label htmlFor="applyDepartment">部门</label><input id="applyDepartment" value={application.department} onChange={event => setApplication(current => ({ ...current, department: event.target.value }))} required maxLength={100} placeholder="请输入部门" /></div>
                <div className="form-row"><label htmlFor="applyEmail">邮箱</label><input id="applyEmail" type="email" value={application.email} onChange={event => setApplication(current => ({ ...current, email: event.target.value }))} required maxLength={100} placeholder="请输入邮箱" /></div>
                <div className="form-row"><label htmlFor="applyUsername">用户名</label><input id="applyUsername" value={application.username} onChange={event => setApplication(current => ({ ...current, username: event.target.value }))} required pattern="[A-Za-z0-9._-]+" maxLength={50} placeholder="字母、数字、点、横线" /></div>
                <div className="form-row"><label htmlFor="applyPassword">密码</label><input id="applyPassword" type="password" autoComplete="new-password" value={application.password} onChange={event => setApplication(current => ({ ...current, password: event.target.value }))} required minLength={8} maxLength={64} placeholder="8～64 位，含字母和数字" /></div>
                <div className="form-row"><label htmlFor="applyConfirmPassword">确认密码</label><input id="applyConfirmPassword" type="password" autoComplete="new-password" value={application.confirmPassword} onChange={event => setApplication(current => ({ ...current, confirmPassword: event.target.value }))} required minLength={8} maxLength={64} placeholder="再次输入密码" /></div>
                <div className="form-row form-span-two"><label htmlFor="applyReason">申请说明（选填）</label><textarea id="applyReason" rows={3} value={application.reason} onChange={event => setApplication(current => ({ ...current, reason: event.target.value }))} maxLength={500} placeholder="可填写使用场景或所属项目" /></div>
                <div className="form-span-two"><button type="submit" className="login-submit" disabled={loading}>{loading ? "提交中..." : "提交"}</button></div>
              </form>
              <p className="application-note">申请仅面向公司内部人员。密码只会以不可逆哈希保存，管理员无法查看。</p>
              <p className="login-help">已有账号？<button type="button" onClick={() => switchMode("login")}>返回登录</button></p>
            </>
          )}

          {success && <div className="login-message success-text">{success}</div>}
          {error && <div className="login-message error-text">{error}</div>}
        </div>
      </section>
    </main>
  );
}
