import { expect, test, type Page, type APIRequestContext } from "@playwright/test";
import { fetchWithTimeout, requestTimeoutMs, responseError } from "../lib/api-request";

const API = "http://127.0.0.1:8100";

async function login(page: Page, request: APIRequestContext, username = "admin1") {
  const response = await request.post(`${API}/auth/login`, { data: { username, password: "ValidationPass123" } });
  expect(response.ok()).toBeTruthy();
  const session = await response.json();
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user));
  }, { token: session.access_token, user: session.user });
  return { Authorization: `Bearer ${session.access_token}` };
}

test("request budgets cover backend model steps and preserve short reads", () => {
  expect(requestTimeoutMs(`${API}/agent/match`, "POST")).toBe(360_000);
  expect(requestTimeoutMs(`${API}/agent/tasks/task-a-failed/retry`, "POST")).toBe(360_000);
  expect(requestTimeoutMs(`${API}/admin/capability-tags/suggestions/scan`, "POST")).toBe(360_000);
  expect(requestTimeoutMs(`${API}/partners/partner-1/profile`, "POST")).toBe(180_000);
  expect(requestTimeoutMs(`${API}/admin/model-configs/example/test`, "POST")).toBe(45_000);
  expect(requestTimeoutMs(`${API}/agent/tasks`, "GET")).toBe(30_000);
});

test("request wrapper preserves caller cancellation and batch timeout override", async () => {
  const originalFetch = globalThis.fetch;
  const originalTimeout = AbortSignal.timeout;
  const requestedTimeouts: number[] = [];
  const signals: (AbortSignal | null | undefined)[] = [];
  try {
    AbortSignal.timeout = ms => { requestedTimeouts.push(ms); return new AbortController().signal; };
    globalThis.fetch = async (_, init) => { signals.push(init?.signal); return new Response("{}"); };
    const controller = new AbortController();
    await fetchWithTimeout(`${API}/agent/tasks`, { signal: controller.signal });
    await fetchWithTimeout(`${API}/partners/batch-profile`, { method: "POST", timeoutMs: 390_000 });
    expect(signals[0]).toBe(controller.signal);
    expect(requestedTimeouts).toEqual([390_000]);
  } finally {
    globalThis.fetch = originalFetch;
    AbortSignal.timeout = originalTimeout;
  }
});

test("validation response is readable even when backend detail is a field-error array", async () => {
  const result = await responseError(new Response(JSON.stringify({ detail: [{ loc: ["body", "maxTokens"] }] }), { status: 422 }));
  expect(result.message).toContain("输入参数无效");
});

test("task processing can continue beyond the submission request budget", async ({ page, request }) => {
  test.setTimeout(75_000);
  await login(page, request, "user_a");
  let started = 0;
  let taskId = "";
  await page.route(`${API}/agent/tasks`, route => {
    taskId = route.request().postDataJSON().requestId;
    started = Date.now();
    return route.fulfill({ status: 202, json: { recordId: taskId, taskStatus: "matching" } });
  });
  await page.route(`${API}/agent/tasks/*`, route => route.fulfill({ json: { id: taskId, requirement: "慢响应验证", createdAt: new Date(started).toISOString(), recommendations: [], taskStatus: Date.now() - started > 31_000 ? "ready" : "matching" } }));
  await page.goto("/");
  await page.locator("#requirement").fill("慢响应验证：寻找制造业知识库伙伴");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page.locator("#requirement")).toHaveValue("");
  await expect(page.locator(".current-task-summary")).toContainText("已完成", { timeout: 40_000 });
  await expect(page.locator(".assistant-error")).toHaveCount(0);
});

test("submission timeout advises checking the original task without resubmission", async ({ page, request }) => {
  await login(page, request, "user_a");
  await page.addInitScript(() => {
    const timeout = AbortSignal.timeout.bind(AbortSignal);
    AbortSignal.timeout = ms => timeout(ms === 30_000 ? 200 : ms);
  });
  let attempts = 0;
  await page.route(`${API}/agent/tasks`, async route => {
    attempts += 1;
    await new Promise(resolve => setTimeout(resolve, 500));
    await route.fulfill({ status: 202, json: { recordId: route.request().postDataJSON().requestId, taskStatus: "matching" } });
  });
  await page.goto("/");
  await page.locator("#requirement").fill("超时验证：寻找制造业知识库伙伴");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page.locator(".assistant-error")).toContainText("提交结果暂未确认");
  await expect(page.getByRole("button", { name: "开始任务", exact: true })).toBeEnabled();
  await expect(page.locator("#requirement")).toHaveValue("超时验证：寻找制造业知识库伙伴");
  expect(attempts).toBe(1);
});

test("partner save, upload, profile and case failures release busy state", async ({ page, request }) => {
  await login(page, request);
  const pageErrors: string[] = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.route(`${API}/**`, route => ["POST", "PUT"].includes(route.request().method()) ? route.abort("failed") : route.continue());
  await page.goto("/admin/partners/partner-1");
  const save = page.getByRole("button", { name: "保存伙伴信息", exact: true });
  await save.click();
  await expect(page.locator(".error-text")).toContainText("网络连接中断");
  await expect(save).toBeEnabled();
  await page.locator('input[type="file"]').first().setInputFiles({ name: "synthetic.pdf", mimeType: "application/pdf", buffer: Buffer.from("synthetic isolated upload") });
  await expect(save).toBeEnabled();
  await page.getByRole("button", { name: "重新生成", exact: true }).click();
  await expect(save).toBeEnabled();
  const caseForm = page.locator("form").filter({ has: page.getByRole("button", { name: "新增案例", exact: true }) });
  await caseForm.locator("input").first().fill("保留输入的案例");
  await caseForm.getByRole("button", { name: "新增案例", exact: true }).click();
  await expect(save).toBeEnabled();
  await expect(caseForm.locator("input").first()).toHaveValue("保留输入的案例");
  expect(pageErrors).toEqual([]);
  await page.unroute(`${API}/**`);
  await save.click();
  await expect(page.locator(".error-text")).toHaveCount(0);
});

test("model mutation failures keep the form and restore controls", async ({ page, request }) => {
  const headers = await login(page, request);
  const added = await request.post(`${API}/admin/model-configs`, { headers, data: { name: "batch2-extra", modelName: "synthetic-extra", apiKey: "synthetic-only" } });
  expect(added.ok()).toBeTruthy();
  await page.route(`${API}/admin/model-configs/**`, route => route.request().method() === "GET" ? route.continue() : route.fulfill({ status: 400, json: { detail: "模拟配置保存失败" } }));
  await page.goto("/admin/models");
  const row = page.locator("tbody tr").filter({ hasText: "batch2-extra" });
  await row.getByRole("button", { name: "停用", exact: true }).click();
  await expect(page.locator(".error-text[role=alert]")).toContainText("模拟配置保存失败");
  await expect(row.getByRole("button", { name: "停用", exact: true })).toBeEnabled();
  await row.getByRole("button", { name: "设默认", exact: true }).click();
  await expect(row.getByRole("button", { name: "设默认", exact: true })).toBeEnabled();
  const configId = (await added.json()).id;
  await page.locator("select").first().selectOption(configId);
  await expect(page.locator("select").first()).toHaveValue("");
  await expect(page.locator("select").first()).toBeEnabled();
  await row.getByRole("button", { name: "编辑", exact: true }).click();
  const editingRow = page.locator("tbody tr").filter({ has: page.locator('input[type="number"]') });
  await editingRow.locator('input[type="number"]').fill("384000");
  await editingRow.getByRole("button", { name: "✓", exact: true }).click();
  await expect(editingRow.locator('input[type="number"]')).toHaveValue("384000");
  await expect(editingRow.getByRole("button", { name: "✓", exact: true })).toBeEnabled();
});

test("user creation and status network errors are caught and inputs retained", async ({ page, request }) => {
  await login(page, request);
  const pageErrors: string[] = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.route(/\/admin\/users(?:\/|$|\?)/, route => route.request().method() === "GET" ? route.continue() : route.abort("failed"));
  await page.goto("/admin/users");
  const create = page.getByRole("button", { name: "创建用户并生成临时密码", exact: true });
  const form = page.locator("form").filter({ has: create });
  await form.locator("input").nth(0).fill("batch2_new_user");
  await form.locator("input").nth(1).fill("模拟用户");
  await create.click();
  await expect(page.locator(".error-text")).toContainText("网络连接中断");
  await expect(create).toBeEnabled();
  await expect(form.locator("input").nth(0)).toHaveValue("batch2_new_user");
  const row = page.locator("tbody tr").filter({ hasText: "user_a" });
  page.once("dialog", dialog => dialog.accept());
  await row.getByRole("button", { name: "停用", exact: true }).click();
  await expect(row.getByRole("button", { name: "停用", exact: true })).toBeEnabled();
  expect(pageErrors).toEqual([]);
});

test("task archive and retry network errors remain actionable", async ({ page, request }) => {
  await login(page, request, "user_a");
  await page.route(`${API}/agent/tasks/**`, route => route.request().method() === "GET" ? route.continue() : route.abort("failed"));
  await page.goto("/tasks");
  const row = page.locator("tbody tr").filter({ hasText: "A-failed" });
  await row.getByRole("button", { name: "归档", exact: true }).click();
  await expect(page.locator(".error-text")).toContainText("网络连接中断");
  page.once("dialog", dialog => dialog.accept());
  await row.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.locator(".error-text")).toContainText("请先到“我的任务”查看任务状态");
  await expect(row.getByRole("button", { name: "重试", exact: true })).toBeEnabled();
});

test("manual tag scan error clears scanning state", async ({ page, request }) => {
  await login(page, request);
  await page.route(`${API}/admin/capability-tags/suggestions/scan`, route => route.abort("failed"));
  await page.goto("/admin/tags");
  await page.getByRole("button", { name: "标签建议", exact: false }).click();
  await page.getByRole("button", { name: "扫描需求", exact: true }).click();
  await expect(page.locator(".error-text")).toContainText("网络连接中断");
  await expect(page.getByRole("button", { name: "扫描需求", exact: true })).toBeEnabled();
});
