export type ApiRequestInit = RequestInit & { timeoutMs?: number; modelCalls?: number };

export type ModelTimeoutSettings = { timeoutSeconds: number; timeoutRetries: number };

export function modelRequestBudgetMs(policy: ModelTimeoutSettings, calls = 1): number {
  return Math.ceil((calls * policy.timeoutSeconds * (policy.timeoutRetries + 1) + 30) * 1000);
}

function requestPath(input: RequestInfo | URL): string {
  const path = new URL(input instanceof Request ? input.url : String(input), "http://localhost").pathname;
  // Optional frontend proxy preserves the same backend request budgets.
  return path.replace(/^\/api(?=\/)/, "");
}

export function modelRequestCalls(input: RequestInfo | URL, method = "GET"): number {
  const path = requestPath(input);
  if (method.toUpperCase() === "POST") {
    // Matching: understanding + initial selection + detailed review; retries stay server-side.
    if (path === "/agent/match" || /^\/agent\/tasks\/[^/]+\/retry$/.test(path)) return 3;
    if (path === "/admin/capability-tags/suggestions/scan") return 10;
    if (/^\/partners\/[^/]+\/profile$/.test(path)) return 3;
    if (/^\/admin\/model-configs\/[^/]+\/test$/.test(path)) return 1;
  }
  return 0;
}

export async function fetchWithTimeout(input: RequestInfo | URL, init: ApiRequestInit = {}): Promise<Response> {
  const { timeoutMs, modelCalls, ...options } = init;
  let signal = options.signal;
  let sent = false;
  try {
    if (!signal) {
      const calls = modelCalls ?? modelRequestCalls(input, options.method);
      let budget = timeoutMs ?? 30_000;
      if (calls && timeoutMs === undefined) {
        const raw = input instanceof Request ? input.url : String(input);
        const url = new URL(raw, typeof location === "undefined" ? "http://localhost" : location.origin);
        url.pathname = (url.pathname.startsWith("/api/") ? "/api" : "") + "/model-timeout-settings";
        url.search = "";
        url.searchParams.set("agent_id",requestPath(input).startsWith("/agent/")?"partner_match":"processing");
        const policyResponse = await fetch(url, { headers: options.headers, credentials: options.credentials,
          cache: "no-store", signal: AbortSignal.timeout(30_000) });
        if (!policyResponse.ok) {
          const error = await responseError(policyResponse);
          return Response.json({ detail: error.message, submissionAccepted: false }, { status: error.status });
        }
        const policy: ModelTimeoutSettings = await policyResponse.json();
        if (!Number.isFinite(policy.timeoutSeconds) || policy.timeoutSeconds <= 0 || !Number.isSafeInteger(policy.timeoutRetries) || policy.timeoutRetries < 0) {
          throw new Error("Invalid model timeout policy");
        }
        budget = modelRequestBudgetMs(policy, calls);
      }
      signal = AbortSignal.timeout(budget);
    }
    sent = true;
    return await fetch(input, { ...options, signal });
  } catch (reason) {
    if (reason instanceof ApiResponseError) throw reason;
    if (!sent) throw new ApiResponseError("服务异常，请联系管理员。", 503, false);
    const timedOut = signal?.reason?.name === "TimeoutError" || (reason instanceof Error && reason.name === "TimeoutError");
    if (signal?.aborted && !timedOut) throw new Error("请求已取消");
    throw new Error("暂未确认结果，请刷新查看。");
  }
}

export class ApiResponseError extends Error {
  constructor(message: string, readonly status: number, readonly submissionAccepted?: boolean, readonly failureCode?: string) { super(message); }
}
export function submissionIsUncertain(error: unknown): boolean {
  if (!(error instanceof ApiResponseError)) return true;
  if (error.submissionAccepted === false) return false;
  if (error.failureCode) return error.failureCode === "persistence";
  return error.status >= 500 || error.status === 408;
}
export async function responseError(response: Response, fallback = "本次处理失败，请重试。"): Promise<ApiResponseError> {
  const data = await response.json().catch(() => ({}));
  const detail = typeof data?.detail === "string" ? data.detail : null;
  const message = response.status >= 500
    ? (detail === "本次处理失败，请重试。" ? detail : "服务异常，请联系管理员。")
    : response.status === 401 ? "登录已过期，请重新登录。"
    : detail || (response.status === 422 ? "输入参数无效，请检查数值范围和必填项" : fallback);
  return new ApiResponseError(message, response.status, typeof data?.submissionAccepted === "boolean" ? data.submissionAccepted : undefined, typeof data?.failureCode === "string" ? data.failureCode : undefined);
}
