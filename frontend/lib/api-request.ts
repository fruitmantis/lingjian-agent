export type ApiRequestInit = RequestInit & { timeoutMs?: number };

function requestPath(input: RequestInfo | URL): string {
  const path = new URL(input instanceof Request ? input.url : String(input), "http://localhost").pathname;
  // Optional frontend proxy preserves the same backend request budgets.
  return path.replace(/^\/api(?=\/)/, "");
}

export function requestTimeoutMs(input: RequestInfo | URL, method = "GET"): number {
  const path = requestPath(input);
  if (method.toUpperCase() === "POST") {
    // Match: 180 + 30 + 30 + 60 seconds; scan: at most 10 × 30 seconds.
    if (path === "/agent/match" || /^\/agent\/tasks\/[^/]+\/retry$/.test(path)
      || path === "/admin/capability-tags/suggestions/scan") return 360_000;
    // Structured extraction + narrative: 60 + 90 seconds.
    if (/^\/partners\/[^/]+\/profile$/.test(path)) return 180_000;
    // Development conversation: scope check + one model call (up to 180 seconds).
    if (/^\/development\/plans\/[^/]+\/conversation$/.test(path)) return 240_000;
    if (/^\/admin\/model-configs\/[^/]+\/test$/.test(path)) return 45_000;
  }
  return 30_000;
}

export async function fetchWithTimeout(input: RequestInfo | URL, init: ApiRequestInit = {}): Promise<Response> {
  const { timeoutMs, ...options } = init;
  const signal = options.signal ?? AbortSignal.timeout(timeoutMs ?? requestTimeoutMs(input, options.method));
  try {
    return await fetch(input, { ...options, signal });
  } catch (reason) {
    const timedOut = signal.reason?.name === "TimeoutError" || (reason instanceof Error && reason.name === "TimeoutError");
    if (signal.aborted && !timedOut) throw new Error("请求已取消");
    throw new Error("暂未确认结果，请刷新查看。");
  }
}

export class ApiResponseError extends Error {
  constructor(message: string, readonly status: number, readonly submissionAccepted?: boolean) { super(message); }
}
export async function responseError(response: Response, fallback = "本次处理失败，请重试。"): Promise<ApiResponseError> {
  const data = await response.json().catch(() => ({}));
  const detail = typeof data?.detail === "string" ? data.detail : null;
  const message = response.status >= 500
    ? (detail === "本次处理失败，请重试。" ? detail : "服务异常，请联系管理员。")
    : response.status === 401 ? "登录已过期，请重新登录。"
    : detail || (response.status === 422 ? "输入参数无效，请检查数值范围和必填项" : fallback);
  return new ApiResponseError(message, response.status, typeof data?.submissionAccepted === "boolean" ? data.submissionAccepted : undefined);
}
