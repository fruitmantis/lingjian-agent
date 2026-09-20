"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchWithTimeout, type ApiRequestInit } from "../lib/api-request";

export type CurrentUser = {
  id: string;
  username: string;
  display_name: string | null;
  department: string | null;
  role: "admin" | "user";
  status: "active" | "disabled";
  must_change_password: boolean;
  created_at: string;
  updated_at: string | null;
  last_login_at: string | null;
  locked_until: string | null;
};

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
  saveSession: (token: string, user: CurrentUser) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const publicPaths = new Set(["/login"]);
export const PASSWORD_CHANGE_PATH = "/change-password";

export function getToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem("token");
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch(path: string, init: ApiRequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetchWithTimeout(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });
  if (response.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.assign("/login");
  }
  return response;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setUser(null);
    router.replace("/login");
  }, [router]);

  const saveSession = useCallback((token: string, nextUser: CurrentUser) => {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(nextUser));
    setUser(nextUser);
  }, []);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      if (!publicPaths.has(pathname)) router.replace("/login");
      return;
    }
    try {
      const response = await apiFetch("/auth/me", { cache: "no-store" });
      if (!response.ok) throw new Error("unauthorized");
      const nextUser = await response.json() as CurrentUser;
      localStorage.setItem("user", JSON.stringify(nextUser));
      setUser(nextUser);
      if (nextUser.must_change_password) {
        if (pathname !== PASSWORD_CHANGE_PATH) router.replace(PASSWORD_CHANGE_PATH);
      } else if (pathname.startsWith("/admin") && nextUser.role !== "admin") router.replace("/403");
      else if (pathname === "/login" || pathname === PASSWORD_CHANGE_PATH) router.replace("/");
    } catch {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      setUser(null);
      if (!publicPaths.has(pathname)) router.replace("/login");
    } finally {
      setLoading(false);
    }
  }, [pathname, router]);

  useEffect(() => { void refresh(); }, [refresh]);

  const value = useMemo(() => ({ user, loading, refresh, saveSession, logout }), [user, loading, refresh, saveSession, logout]);
  // Do not mount business pages while a password change or redirect is required.
  const changingPassword = !!user?.must_change_password;
  const redirecting = (changingPassword && pathname !== PASSWORD_CHANGE_PATH)
    || (pathname === PASSWORD_CHANGE_PATH && !changingPassword);
  if ((loading && !publicPaths.has(pathname)) || (!user && !publicPaths.has(pathname)) || redirecting) {
    return <div className="auth-loading" role="status">正在验证登录状态...</div>;
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
