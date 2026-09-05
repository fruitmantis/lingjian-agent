export type ApiRequestInit = RequestInit & { timeoutMs?: number };

function requestPath(input: RequestInfo | URL): string {
  return new URL(input instanceof Request ? input.url : String(input), "http://localhost").pathname;
}

export function requestTimeoutMs(input: RequestInfo | URL, method = "GET"): number {
  const path = requestPath(input);
  if (method.toUpperCase() === "POST") {
    // Match: 180 + 30 + 30 + 60 seconds; scan: at most 10 × 30 seconds.
    if (path === "/agent/match" || /^\/agent\/tasks\/[^/]+\/retry$/.test(path)
      || path === "/admin/capability-tags/suggestions/scan") return 360_000;
    // Structured extraction + narrative: 60 + 90 seconds.
    if (/^\/partners\/[^/]+\/profile$/.test(path)) return 180_000;
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
    const path = requestPath(input);
    const taskRequest = options.method?.toUpperCase() === "POST"
      && (path === "/agent/match" || /^\/agent\/tasks\/[^/]+\/retry$/.test(path));
    if (taskRequest) {
      throw new Error(`${timedOut ? "等待匹配结果超时" : "匹配请求连接中断"}，请先到“我的任务”查看任务状态，再决定是否重新提交。`);
    }
    if (signal.aborted && !timedOut) throw new Error("请求已取消");
    const prefix = timedOut ? "请求等待超时" : "网络连接中断";
    const isWrite = !["GET", "HEAD"].includes((options.method ?? "GET").toUpperCase());
    throw new Error(`${prefix}，${isWrite ? "操作结果尚未确认，请刷新页面核实后再试。" : "请检查网络后重试。"}`);
  }
}

export async function responseError(response: Response, fallback = "操作失败"): Promise<Error> {
  const data = await response.json().catch(() => ({}));
  const detail = typeof data?.detail === "string" ? data.detail : null;
  return new Error(detail || (response.status === 422 ? "输入参数无效，请检查数值范围和必填项" : `${fallback}（HTTP ${response.status}）`));
}
