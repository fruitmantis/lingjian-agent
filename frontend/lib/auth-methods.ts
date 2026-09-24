const labels = { password: "账号密码", key: "身份 Key", passkey: "本机身份", browser: "浏览器身份" } as const;
export type AuthMethod = keyof typeof labels;

export function formatAuthMethods(methods?: readonly AuthMethod[]): string {
  return [...new Set(methods ?? [])].map(method => labels[method]).filter(Boolean).join("、") || "未配置";
}

export function formatIdentityKeyHint(user: { role: string; auth_methods?: readonly AuthMethod[]; identity_key_hint?: string | null }): string {
  return user.role === "user" && user.auth_methods?.includes("key") ? user.identity_key_hint || "暂不可用" : "—";
}
