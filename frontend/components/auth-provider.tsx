"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchWithTimeout, type ApiRequestInit } from "../lib/api-request";
import { readIdentityKeyFile } from "../lib/identity-key-file";
import { SaveIdentityDialog } from "./identity-credential";
import { identityLock } from "../lib/identity-coordination";
import { LingjianMark } from "./ui-icons";

export type CurrentUser = {
  id: string; username: string; display_name: string | null; department: string | null;
  role: "admin" | "user"; status: "active" | "disabled"; must_change_password: boolean;
  identity_method?: "password" | "key";
  created_at: string; updated_at: string | null; last_login_at: string | null; locked_until: string | null;
};
export type AuthScope = "user" | "admin";
type AuthContextValue = { user: CurrentUser | null; loading: boolean; scope: AuthScope;
  refresh: () => Promise<void>; saveSession: (token: string, user: CurrentUser) => void; logout: () => Promise<void>; };
const AuthContext = createContext<AuthContextValue | null>(null);
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
export const PASSWORD_CHANGE_PATH = "/admin/change-password";
const SIGNED_OUT = "banfei:user:signed-out";
const storageKey = (scope: AuthScope, name: string) => `banfei:${scope}:${name}`;
const currentScope = (): AuthScope => typeof window !== "undefined" && window.location.pathname.startsWith("/admin") ? "admin" : "user";
export function getToken(scope: AuthScope = currentScope()): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(storageKey(scope, "token"));
}
export function authHeaders(scope: AuthScope = currentScope()): Record<string, string> {
  const token = getToken(scope); return token ? { Authorization: `Bearer ${token}` } : {};
}
function clearSession(scope: AuthScope) {
  localStorage.removeItem(storageKey(scope, "token")); localStorage.removeItem(storageKey(scope, "user"));
}
function storeSession(scope: AuthScope, token: string, user: CurrentUser) {
  if (user.role !== scope) throw new Error("身份类型不匹配，请重新进入");
  localStorage.setItem(storageKey(scope, "token"), token); localStorage.setItem(storageKey(scope, "user"), JSON.stringify(user));
}
export async function apiFetch(path: string, init: ApiRequestInit = {}, scope: AuthScope = currentScope()): Promise<Response> {
  const response = await fetchWithTimeout(`${apiBaseUrl}${path}`, {
    ...init, headers: { ...Object.fromEntries(new Headers(init.headers)), ...authHeaders(scope) },
  });
  if (response.status === 401 && typeof window !== "undefined") {
    clearSession(scope);
    if (scope === currentScope() && window.location.pathname !== (scope === "admin" ? "/admin/login" : "/login")) {
      window.location.assign(scope === "admin" ? "/admin/login" : "/login");
    }
  }
  return response;
}
export const adminApiFetch = (path: string, init: ApiRequestInit = {}) => apiFetch(path, init, "admin");
export const userApiFetch = (path: string, init: ApiRequestInit = {}) => apiFetch(path, init, "user");
export async function identityRequest(path: string, body: object = {}) {
  return fetchWithTimeout(`${apiBaseUrl}/auth/identity${path}`, { method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json", ...authHeaders("user") }, body: JSON.stringify(body) });
}
type IdentitySession = { access_token: string; user: CurrentUser; created: boolean };
class IdentityError extends Error {
  constructor(message: string, readonly code: string, readonly browserIdentityAvailable?: boolean) { super(message); }
}
async function result(response: Response): Promise<IdentitySession> {
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    if (detail && typeof detail === "object" && typeof detail.code === "string" && typeof detail.message === "string") {
      throw new IdentityError(detail.message, detail.code, typeof detail.browser_identity_available === "boolean" ? detail.browser_identity_available : undefined);
    }
    throw new Error(typeof detail === "string" ? detail : "暂时无法进入，请重试");
  }
  return data;
}
let browserCreation: Promise<IdentitySession> | null = null;
function createBrowser() {
  if (!browserCreation) browserCreation = (async () => {
    if (localStorage.getItem(SIGNED_OUT)) throw new Error("已退出，请使用身份 Key 登录或选择创建新身份");
    const existing = await identityRequest("/session");
    if (existing.ok) return result(existing);
    if (existing.status !== 404) return result(existing);
    const created = await result(await identityRequest("/session", { create: true }));
    // Keep the existing save reminder even if the initiating view unmounts before adopt().
    if (created.created) localStorage.setItem(`banfei:key-save:${created.user.id}`, "pending");
    return created;
  })().finally(() => { browserCreation = null; });
  return browserCreation;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const scope = pathname.startsWith("/admin") ? "admin" : "user";
  return <ScopedAuth key={scope} scope={scope}>{children}</ScopedAuth>;
}
function ScopedAuth({ children, scope }: { children: React.ReactNode; scope: AuthScope }) {
  const pathname = usePathname(); const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(false); const [keyInput, setKeyInput] = useState("");
  const [signedOut, setSignedOut] = useState(false);
  const [remembered, setRemembered] = useState(false);
  const [keyEntry, setKeyEntry] = useState(false);
  const [identityErrorCode, setIdentityErrorCode] = useState("");
  const reportIdentityError = useCallback((reason: unknown, fallback: string) => {
    setError(reason instanceof Error ? reason.message : fallback);
    setIdentityErrorCode(reason instanceof IdentityError ? reason.code : "");
    if (reason instanceof IdentityError && ["identity_deleted", "unknown_key"].includes(reason.code) && reason.browserIdentityAvailable !== undefined) {
      // Only show the return action when the server verified a usable Cookie;
      // never erase another browser identity/token because an entered Key failed.
      setRemembered(reason.browserIdentityAvailable);
    }
  }, []);
  const keyFileInput = useRef<HTMLInputElement>(null);
  const saveSession = useCallback((token: string, nextUser: CurrentUser) => {
    storeSession(scope, token, nextUser);
    if (scope === "user") { localStorage.removeItem(SIGNED_OUT); sessionStorage.removeItem(SIGNED_OUT); }
    setError(""); setIdentityErrorCode(""); setSignedOut(false); setUser(nextUser);
  }, [scope]);
  const adopt = useCallback((data: IdentitySession) => {
    saveSession(data.access_token, data.user);
    if (data.created) localStorage.setItem(`banfei:key-save:${data.user.id}`, "pending");
    setNotice(localStorage.getItem(`banfei:key-save:${data.user.id}`) === "pending");
  }, [saveSession]);
  const logout = useCallback(async () => {
    try {
      if (scope === "user") await identityLock(async () => {
        const response = await identityRequest("/logout");
        if (!response.ok) throw new Error("暂时无法退出，请重试");
        const state = await response.json();
        localStorage.setItem(SIGNED_OUT, state.remembered ? "remembered" : "1");
        clearSession("user"); setUser(null); setNotice(false);
      });
      else clearSession("admin");
      setUser(null); setNotice(false);
      if (scope === "admin") router.replace("/admin/login"); else window.location.assign("/login");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "退出失败，请重试"); }
  }, [router, scope]);
  const refresh = useCallback(async () => {
    const response = await apiFetch("/auth/me", { cache: "no-store" }, scope);
    if (!response.ok) throw new Error("身份已失效");
    const next = await response.json() as CurrentUser;
    if (next.role !== scope) throw new Error("身份类型不匹配");
    setUser(next); localStorage.setItem(storageKey(scope, "user"), JSON.stringify(next));
  }, [scope]);
  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      try {
        // A normal /login visit can restore this browser. Only a deliberate Key
        // switch or logout suppresses automatic entry; neither creates a user.
        const explicitKey = window.location.pathname === "/login" && new URLSearchParams(window.location.search).get("method") === "key";
        const exited = localStorage.getItem(SIGNED_OUT);
        if (scope === "user" && (explicitKey || exited)) {
          if (!cancelled) {
            setSignedOut(Boolean(exited)); setRemembered(exited === "remembered"); setKeyEntry(explicitKey);
          }
          return;
        }
        await identityLock(async () => {
        const token = getToken(scope);
        if (token) {
          const response = await fetchWithTimeout(`${apiBaseUrl}/auth/me`, { headers: authHeaders(scope), cache: "no-store" });
          if (response.ok) {
            const next = await response.json() as CurrentUser;
            if (next.role === scope) {
              if (!cancelled && (scope === "admin" || !localStorage.getItem(SIGNED_OUT))) { setUser(next); setNotice(scope === "user" && localStorage.getItem(`banfei:key-save:${next.id}`) === "pending"); }
              return;
            }
          } else if (response.status !== 401) throw new Error("暂时无法验证身份，请重试");
          clearSession(scope);
        }
        if (scope === "admin") return;
        if (window.location.pathname === "/login") {
          const restored = await identityRequest("/session");
          if (restored.status === 404) return;
          const data = await result(restored);
          if (!cancelled && !localStorage.getItem(SIGNED_OUT)) adopt(data);
        } else {
          const data = await createBrowser();
          if (!cancelled && !localStorage.getItem(SIGNED_OUT)) adopt(data);
        }
        });
      } catch (reason) {
        if (!cancelled) reportIdentityError(reason, "暂时无法进入，请重试");
      } finally { if (!cancelled) setLoading(false); }
    }
    void initialize(); return () => { cancelled = true; };
  }, [scope, adopt, reportIdentityError]);
  useEffect(() => {
    if (scope !== "user") return;
    const changed = (event: StorageEvent) => {
      if (event.key === SIGNED_OUT && event.newValue) window.location.assign("/login");
      if (event.key === storageKey("user", "user") && event.oldValue && event.newValue
        && JSON.parse(event.oldValue).id !== JSON.parse(event.newValue).id) window.location.reload();
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, [scope]);
  useEffect(() => {
    if (loading) return;
    if (scope === "admin") {
      if (!user && pathname !== "/admin/login") router.replace("/admin/login");
      else if (user?.must_change_password && pathname !== PASSWORD_CHANGE_PATH) router.replace(PASSWORD_CHANGE_PATH);
      else if (user && !user.must_change_password && ["/admin/login", PASSWORD_CHANGE_PATH].includes(pathname)) router.replace("/admin");
    } else if (user && ["/login", "/change-password"].includes(pathname)) router.replace("/");
  }, [loading, pathname, router, scope, user]);
  async function loginWithKey(source: string | File) {
    if (busy) return;
    setBusy(true); setError(""); setIdentityErrorCode("");
    try {
      const key = typeof source === "string" ? source : await readIdentityKeyFile(source);
      await identityLock(async () => {
        const data = await result(await identityRequest("/key/login", { key }));
        setKeyInput(""); adopt(data); router.replace("/");
      });
    } catch (reason) { reportIdentityError(reason, "登录失败，请重试"); }
    finally { setBusy(false); }
  }
  async function continueRemembered() {
    if (busy) return; setBusy(true); setError(""); setIdentityErrorCode("");
    try {
      await identityLock(async () => {
        const response = await identityRequest("/session");
        if (response.status === 401 || response.status === 404) {
          setRemembered(false); localStorage.setItem(SIGNED_OUT, "1");
        }
        const data = await result(response);
        adopt(data); router.replace("/");
      });
    } catch (reason) { reportIdentityError(reason, "暂时无法继续，请重试"); }
    finally { setBusy(false); }
  }
  async function startNew() {
    if (busy) return; setBusy(true);
    if (identityErrorCode !== "identity_deleted") setError("");
    try {
      // Explicit creation after logout. Never called by a Key login error.
      await identityLock(async () => {
        const data = await result(await identityRequest("/session", { create: true, replace: true }));
        adopt(data); router.replace("/");
      });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "暂时无法进入，请重试"); }
    finally { setBusy(false); }
  }
  function dismissNotice() {
    if (user) localStorage.removeItem(`banfei:key-save:${user.id}`);
    setNotice(false);
  }
  const value = useMemo(() => ({ user, loading, scope, refresh, saveSession, logout }), [user, loading, scope, refresh, saveSession, logout]);
  const deletedIdentity = identityErrorCode === "identity_deleted";
  if (loading) return <div className="auth-loading" role="status">正在准备伴飞...</div>;
  if (scope === "user" && !user) return <main className="password-change-page"><section className="login-card password-change-card identity-entry-card">
    <div className="login-brand-lockup"><LingjianMark /><span>伴飞 Agent</span></div>
    <h1>{deletedIdentity ? "原身份已删除" : signedOut ? "已退出伴飞" : "使用身份 Key 登录"}</h1>
    <p className="identity-entry-description">{deletedIdentity ? error : remembered && !keyEntry ? "此浏览器已记住你的身份，继续即可回到原来的任务和历史。" : "粘贴 Key 或导入已保存的凭据文件，即可继续使用原身份和全部历史。"}</p>
    {deletedIdentity ? <div className="identity-entry-actions">
      <button type="button" className="login-submit" disabled={busy} onClick={() => void startNew()}>{busy ? "正在创建…" : "创建新身份"}</button>
      <button type="button" className="secondary-btn" disabled={busy} onClick={() => { setKeyEntry(true); setError(""); setIdentityErrorCode(""); }}>使用其他 Key 登录</button>
      {remembered && <button type="button" className="secondary-btn" disabled={busy} onClick={() => { setKeyEntry(false); setError(""); setIdentityErrorCode(""); }}>返回当前浏览器身份</button>}
      <p className="meta-text">新身份会生成新的 Key，不会恢复已删除的身份。</p>
    </div> : remembered && !keyEntry ? <div className="identity-entry-actions">
      {error && <p role="alert" className="error-text">{error}</p>}
      <button type="button" className="login-submit" disabled={busy} onClick={() => void continueRemembered()}>{busy ? "正在进入…" : "继续使用当前身份"}</button>
      <button type="button" className="secondary-btn" disabled={busy} onClick={() => { setKeyEntry(true); setError(""); setIdentityErrorCode(""); }}>使用其他 Key 登录</button>
    </div> : <form onSubmit={event => { event.preventDefault(); void loginWithKey(keyInput); }} className="partner-form">
      <label htmlFor="identity-key-input">身份 Key</label>
      <input id="identity-key-input" type="password" autoComplete="off" spellCheck={false} autoCapitalize="none" value={keyInput} onChange={event => setKeyInput(event.target.value)} placeholder="粘贴你的身份 Key" disabled={busy} required maxLength={256} />
      {error && <p role="alert" className="error-text">{error}</p>}
      <button className="login-submit" disabled={busy}>{busy ? "正在进入…" : "登录原身份"}</button>
      <div className="identity-file-import">
        <div className="identity-import-divider" aria-hidden="true"><span>或</span></div>
        <input ref={keyFileInput} type="file" accept=".txt,text/plain" hidden disabled={busy} aria-label="选择身份凭据文件" onChange={event => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) void loginWithKey(file);
        }} />
        <button type="button" className="secondary-btn" disabled={busy} onClick={() => keyFileInput.current?.click()}>导入凭据 .txt 登录</button>
        <p>选择之前下载的身份凭据文件，即可登录原身份。</p>
      </div>
    </form>}
    {!deletedIdentity && !remembered && identityErrorCode !== "identity_disabled" && <div className="identity-entry-new"><p>第一次使用？创建新身份后会生成新的 Key。</p><button type="button" className="secondary-btn" disabled={busy} onClick={() => void startNew()}>创建新身份</button></div>}
    {!deletedIdentity && remembered && keyEntry && <div className="identity-entry-new"><button type="button" className="secondary-btn" disabled={busy} onClick={() => { setKeyEntry(false); setError(""); setIdentityErrorCode(""); }}>返回当前浏览器身份</button></div>}
    <div className="identity-entry-footer"><a className="identity-entry-admin-link" href="/admin/login">管理员登录</a></div>
  </section></main>;
  if (scope === "admin" && ((!user && pathname !== "/admin/login") || (user?.must_change_password && pathname !== PASSWORD_CHANGE_PATH)
      || (user && !user.must_change_password && pathname === PASSWORD_CHANGE_PATH))) return <div className="auth-loading">正在进入管理后台...</div>;
  return <AuthContext.Provider value={value}>
    {error && <div className="identity-notice error-text" role="alert">{error}</div>}
    {children}
    {notice && user && scope === "user" && <SaveIdentityDialog onClose={dismissNotice} onLogin={() => { dismissNotice(); window.location.assign("/login?method=key"); }} />}
  </AuthContext.Provider>;
}
export function useAuth(): AuthContextValue { const value = useContext(AuthContext); if (!value) throw new Error("AuthProvider required"); return value; }
