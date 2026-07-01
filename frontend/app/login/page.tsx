"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
      if (!res.ok) { const errData = await res.json().catch(() => ({})); throw new Error(errData.detail || `HTTP ${res.status}`); }
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
      router.push("/");
    } catch (e) { setError(e instanceof Error ? e.message : "登录失败"); } finally { setLoading(false); }
  }

  return (
    <main className="page" style={{ maxWidth: "440px", marginTop: "80px" }}>
      <div className="card" style={{ padding: "40px" }}>
        <p className="eyebrow">Login</p>
        <h1 style={{ fontSize: "28px" }}>登录灵鉴 Agent</h1>
        <p className="lead" style={{ fontSize: "14px", marginTop: "8px" }}>请输入用户名和密码登录系统</p>
        <form onSubmit={handleLogin} className="partner-form" style={{ marginTop: "24px" }}>
          <div className="form-row"><label htmlFor="username">用户名</label><input id="username" type="text" value={username} onChange={(e) => setUsername(e.target.value)} required placeholder="用户名" /></div>
          <div className="form-row"><label htmlFor="password">密码</label><input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="密码" /></div>
          <button type="submit" disabled={loading} style={{ width: "100%", marginTop: "8px" }}>{loading ? "登录中..." : "登录"}</button>
        </form>
        {error && <p className="error-text" style={{ marginTop: "12px" }}>{error}</p>}
        <p style={{ marginTop: "16px", fontSize: "13px", color: "var(--muted)" }}>默认管理员：admin / admin123</p>
      </div>
    </main>
  );
}
