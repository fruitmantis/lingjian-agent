"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchWithTimeout, type ApiRequestInit } from "../lib/api-request";
import { SaveIdentityDialog } from "./identity-credential";
import { SwitchIdentityDialog } from "./identity-switch";
import { identityLock } from "../lib/identity-coordination";
import { LingjianMark } from "./ui-icons";

export type CurrentUser = {
  id: string; username: string; display_name: string | null; department: string | null;
  role: "admin" | "user"; status: "active" | "disabled"; must_change_password: boolean;
  employee_number?: string | null;
  identity_method?: "password" | "key";
  created_at: string; updated_at: string | null; last_login_at: string | null; locked_until: string | null;
};
export type AuthScope = "user" | "admin";
type AuthContextValue = { user: CurrentUser | null; loading: boolean; scope: AuthScope;
  refresh: () => Promise<void>; saveSession: (token: string, user: CurrentUser) => void; logout: () => Promise<void>; openIdentitySwitch: () => void; };
const AuthContext = createContext<AuthContextValue | null>(null);
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
export const PASSWORD_CHANGE_PATH = "/admin/change-password";
const SIGNED_OUT = "banfei:user:signed-out";
let userIdentitySwitching = false;
let userIdentitySwitchVersion = 0;
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
  const switchVersion = userIdentitySwitchVersion;
  const response = await fetchWithTimeout(`${apiBaseUrl}${path}`, {
    ...init, headers: { ...Object.fromEntries(new Headers(init.headers)), ...authHeaders(scope) },
  });
  // Only requests overlapping this tab's explicit switch defer to its identity check.
  const switchHandled = scope === "user" && (userIdentitySwitching || switchVersion !== userIdentitySwitchVersion);
  if (response.status === 401 && typeof window !== "undefined" && !switchHandled) {
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
function keyFromLoginLink(source: string): string {
  let key = source.trim();
  if (!key.startsWith("bf_")) {
    try {
      const link = new URL(key);
      if (!["http:", "https:"].includes(link.protocol)) throw new Error();
      key = new URLSearchParams(link.hash.slice(1)).get("k") || "";
    } catch { throw new Error("请输入有效的登录链接或已有 Key。"); }
  }
  if (!/^bf_[A-Za-z0-9_-]{43}$/.test(key)) throw new Error("请输入有效的登录链接或已有 Key。");
  return key;
}
async function keySession(key: string): Promise<IdentitySession> {
  let response: Response;
  try { response = await identityRequest("/key/login", { key }); }
  catch { throw new IdentityError("网络连接失败，登录结果暂未确认，请重试登录链接。", "network_error"); }
  return result(response);
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
  const [switchTarget, setSwitchTarget] = useState<string | null>(null);
  const [identityErrorCode, setIdentityErrorCode] = useState("");
  const [switchMessage, setSwitchMessage] = useState("");
  const reportIdentityError = useCallback((reason: unknown, fallback: string) => {
    setError(reason instanceof Error ? reason.message : fallback);
    setIdentityErrorCode(reason instanceof IdentityError ? reason.code : "");

  }, []);
  const saveSession = useCallback((token: string, nextUser: CurrentUser) => {
    storeSession(scope, token, nextUser);
    if (scope === "user") { localStorage.removeItem(SIGNED_OUT); sessionStorage.removeItem(SIGNED_OUT); }
    setError(""); setIdentityErrorCode(""); setUser(nextUser);
  }, [scope]);
  const adopt = useCallback((data: IdentitySession) => {
    saveSession(data.access_token, data.user);
    if (data.created) localStorage.setItem(`banfei:key-save:${data.user.id}`, "pending");
    setNotice(localStorage.getItem(`banfei:key-save:${data.user.id}`) === "pending");
  }, [saveSession]);
  const openIdentitySwitch = useCallback(() => {
    if (scope !== "user" || !user) return;
    localStorage.removeItem(`banfei:key-save:${user.id}`);
    setSwitchMessage(""); setNotice(false); setSwitchTarget("");
  }, [scope, user]);
  const logout = useCallback(async () => {
    if (scope === "user") { openIdentitySwitch(); return; }
    clearSession("admin"); setUser(null); setNotice(false); router.replace("/admin/login");
  }, [router, scope, openIdentitySwitch]);
  const refresh = useCallback(async () => {
    const response = await apiFetch("/auth/me", { cache: "no-store" }, scope);
    if (!response.ok) throw new Error("身份已失效");
    const next = await response.json() as CurrentUser;
    if (next.role !== scope) throw new Error("身份类型不匹配");
    setUser(next); localStorage.setItem(storageKey(scope, "user"), JSON.stringify(next));
  }, [scope]);
  useEffect(() => {
    let cancelled = false; let generation = 0;
    async function initialize() {
      const attempt = ++generation;
      const current = () => !cancelled && attempt === generation;
      const fragment = new URLSearchParams(window.location.hash.slice(1));
      const linked = scope === "user" && fragment.has("k");
      const cleanHash = () => window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
      setLoading(true);
      try {
        await identityLock(async () => {
          if (!current()) return;
          let restored: IdentitySession | null = null;
          const token = getToken(scope);
          if (token) {
            const response = await fetchWithTimeout(`${apiBaseUrl}/auth/me`, { headers: authHeaders(scope), cache: "no-store" });
            if (!current()) return;
            if (response.ok) {
              const next = await response.json() as CurrentUser;
              if (next.role === scope) restored = { access_token: token, user: next, created: false };
            } else if (response.status !== 401) throw new Error("暂时无法验证身份，请重试");
            if (!restored) clearSession(scope);
          }
          if (scope === "admin") { if (restored && current()) saveSession(restored.access_token, restored.user); return; }
          if (!restored) {
            const response = await identityRequest("/session");
            if (response.status !== 404) restored = await result(response);
          }
          if (!current()) return;
          if (linked) {
            setNotice(false); setError(""); setIdentityErrorCode("");
            const key = fragment.get("k") || "";
            if (restored) {
              saveSession(restored.access_token, restored.user);
              // Compare only the current owner's Key. Never log in to the target
              // before the user has saved/cancelled their current identity.
              let same = false;
              try {
                const own = await fetchWithTimeout(`${apiBaseUrl}/auth/identity/key`, { headers: authHeaders("user"), cache: "no-store" });
                same = own.ok && (await own.json()).key === key;
              } catch { /* A failed read must not trigger an unconfirmed switch. */ }
              if (!current()) return;
              localStorage.removeItem(`banfei:key-save:${restored.user.id}`);
              if (!same) setSwitchTarget(`${window.location.origin}/#k=${encodeURIComponent(key)}`);
              cleanHash();
              if (same) router.replace("/");
            } else {
              const data = await keySession(key);
              if (current()) {
                adopt(data); localStorage.removeItem(`banfei:key-save:${data.user.id}`); setNotice(false);
                cleanHash(); router.replace("/");
              }
            }
            return;
          }
          const explicitKey = window.location.pathname === "/login" && new URLSearchParams(window.location.search).get("method") === "key";
          if (restored) {
            adopt(restored);
            if (explicitKey) { setNotice(false); setSwitchTarget(""); }
            return;
          }
          if (window.location.pathname === "/login") return;
          // Only an explicit no-identity response permits first-time creation.
          // Network/service failures above never fall through to create a user.
          const created = await result(await identityRequest("/session", { create: true }));
          if (current()) adopt(created);
        });
      } catch (reason) {
        if (current()) reportIdentityError(reason, "暂时无法进入，请重试");
      } finally { if (current()) setLoading(false); }
    }
    const changed = () => { if (scope === "user" && new URLSearchParams(window.location.hash.slice(1)).has("k")) void initialize(); };
    window.addEventListener("hashchange", changed);
    void initialize();
    return () => { cancelled = true; window.removeEventListener("hashchange", changed); };
  }, [scope, adopt, saveSession, reportIdentityError, router]);
  useEffect(() => {
    if (scope !== "user") return;
    const changed = (event: StorageEvent) => {
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
    } else if (user && switchTarget === null && ["/login", "/change-password"].includes(pathname)) router.replace("/");
  }, [loading, pathname, router, scope, user, switchTarget]);
  async function loginWithKey(source: string) {
    if (busy) return;
    setBusy(true); setError(""); setIdentityErrorCode("");
    try {
      const key = keyFromLoginLink(source);
      await identityLock(async () => {
        const data = await keySession(key);
        setKeyInput(""); adopt(data); router.replace("/");
      });
    } catch (reason) { reportIdentityError(reason, "登录失败，请重试"); }
    finally { setBusy(false); }
  }
  async function switchIdentity(source: string) {
    const key = keyFromLoginLink(source);
    const previousUser = user, previousToken = getToken("user");
    const complete = (data: IdentitySession) => {
      adopt(data); localStorage.removeItem(`banfei:key-save:${data.user.id}`);
      setNotice(false); setSwitchTarget(null);
      window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
      router.replace("/");
    };
    setSwitchMessage("");
    userIdentitySwitching = true; userIdentitySwitchVersion++;
    try {
      await identityLock(async () => {
        try { complete(await keySession(key)); }
        catch (reason) {
          // The server may have committed before the response was lost. Probe
          // only the Cookie, without the now possibly revoked previous Bearer.
          let restored: IdentitySession | null = null;
          try {
            const response = await fetchWithTimeout(`${apiBaseUrl}/auth/identity/session`, {
              method: "POST", credentials: "include", cache: "no-store",
              headers: { "Content-Type": "application/json" }, body: JSON.stringify({ create: false }),
            });
            if (response.ok) restored = await result(response);
          } catch { /* Verify the previous token before claiming it still works. */ }
          if (restored && restored.user.id !== previousUser?.id) {
            complete(restored);
            setSwitchMessage(`切换已生效，当前身份：${restored.user.employee_number || restored.user.username}`);
            return;
          }
          let previous: CurrentUser | null = null, previousStatus = 0;
          try {
            const response = await fetchWithTimeout(`${apiBaseUrl}/auth/me`, {
              headers: previousToken ? { Authorization: `Bearer ${previousToken}` } : {}, cache: "no-store",
            });
            previousStatus = response.status;
            if (response.ok) previous = await response.json() as CurrentUser;
          } catch { /* An unavailable probe does not authorize a replacement identity. */ }
          if (previous?.id === previousUser?.id || restored?.user.id === previousUser?.id) {
            if (!previous && restored) saveSession(restored.access_token, restored.user);
            const detail = reason instanceof IdentityError && reason.code !== "network_error" ? ` ${reason.message}` : "";
            throw new Error("切换失败，你仍是原来的身份，请重试。" + detail);
          }
          if (previousStatus === 401) {
            clearSession("user"); setUser(null); setNotice(false); setSwitchTarget(null);
            setIdentityErrorCode(""); setError("登录已失效，请重新进入");
            window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
            router.replace("/login");
            return;
          }
          throw new Error("暂时无法确认切换结果，请重试。");
        }
      });
    } finally { userIdentitySwitching = false; userIdentitySwitchVersion++; }
  }
  function cancelIdentitySwitch() {
    setSwitchTarget(null);
    window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    if (window.location.pathname === "/login") router.replace("/");
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
  const value = useMemo(() => ({ user, loading, scope, refresh, saveSession, logout, openIdentitySwitch }), [user, loading, scope, refresh, saveSession, logout, openIdentitySwitch]);
  const deletedIdentity = identityErrorCode === "identity_deleted";
  if (loading) return <div className="auth-loading" role="status">正在准备伴飞...</div>;
  if (scope === "user" && !user) return <main className="password-change-page"><section className="login-card password-change-card identity-entry-card">
    <div className="login-brand-lockup"><LingjianMark /><span>伴飞 Agent</span></div>
    <h1>{deletedIdentity ? "原身份已删除" : "使用登录链接进入伴飞"}</h1>
    <p className="identity-entry-description">{deletedIdentity ? error : "粘贴登录链接或已有 Key，继续使用原身份和历史。"}</p>
    {deletedIdentity ? <div className="identity-entry-actions">
      <button type="button" className="login-submit" disabled={busy} onClick={() => void startNew()}>{busy ? "正在创建…" : "创建新身份"}</button>
      <button type="button" className="secondary-btn" disabled={busy} onClick={() => { setError(""); setIdentityErrorCode(""); }}>使用其他登录链接</button>
      <p className="meta-text">新身份不会恢复已删除的历史。</p>
    </div> : <form onSubmit={event => { event.preventDefault(); void loginWithKey(keyInput); }} className="partner-form">
      <label htmlFor="identity-key-input">登录链接或 Key</label>
      <input id="identity-key-input" type="text" autoComplete="off" spellCheck={false} autoCapitalize="none" value={keyInput} onChange={event => setKeyInput(event.target.value)} placeholder="粘贴登录链接或已有 Key" disabled={busy} required maxLength={2048} />
      {error && <p role="alert" className="error-text">{error}</p>}
      <button className="login-submit" disabled={busy}>{busy ? "正在进入…" : "登录原身份"}</button>
    </form>}
    {!deletedIdentity && identityErrorCode !== "identity_disabled" && <div className="identity-entry-new"><button type="button" className="secondary-btn" disabled={busy} onClick={() => void startNew()}>创建新身份</button></div>}
    <div className="identity-entry-footer"><a className="identity-entry-admin-link" href="/admin/login">管理员登录</a></div>
  </section></main>;
  if (scope === "admin" && ((!user && pathname !== "/admin/login") || (user?.must_change_password && pathname !== PASSWORD_CHANGE_PATH)
      || (user && !user.must_change_password && pathname === PASSWORD_CHANGE_PATH))) return <div className="auth-loading">正在进入管理后台...</div>;
  return <AuthContext.Provider value={value}>
    {switchMessage && <div className="identity-notice" role="status">{switchMessage}</div>}
    {error && <div className="identity-notice error-text" role="alert">{error}</div>}
    {children}
    {notice && user && scope === "user" && <SaveIdentityDialog onClose={dismissNotice} />}
    {switchTarget !== null && user && scope === "user" && <SwitchIdentityDialog initialTarget={switchTarget} onCancel={cancelIdentitySwitch} onSwitch={switchIdentity} />}
  </AuthContext.Provider>;
}
export function useAuth(): AuthContextValue { const value = useContext(AuthContext); if (!value) throw new Error("AuthProvider required"); return value; }
