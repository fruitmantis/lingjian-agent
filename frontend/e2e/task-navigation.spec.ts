import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const API = "http://127.0.0.1:18000";
type Task = { id: string; requirement: string; createdAt: string; taskStatus: string; recommendations: unknown[]; archivedAt: null; opportunity: null };
async function login(page: Page, request: APIRequestContext) {
  const response = await request.post(`${API}/auth/login`, { data: { username: "user_a", password: "ValidationPass123" } });
  expect(response.ok()).toBeTruthy();
  const session = await response.json();
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem("token", token); localStorage.setItem("user", JSON.stringify(user));
  }, { token: session.access_token, user: session.user });
  return { Authorization: `Bearer ${session.access_token}` };
}
function task(index: number): Task {
  return { id: `sidebar-${index}`, requirement: `导航验证任务 ${String(index).padStart(2, "0")}`, createdAt: new Date(Date.UTC(2026, 8, 5, 12, -index)).toISOString(), taskStatus: "ready", recommendations: [], archivedAt: null, opportunity: null };
}
async function fixture(page: Page, records: Task[]) {
  await page.route(/\/agent\/tasks\?/, async route => {
    const params = new URL(route.request().url()).searchParams;
    let items = [...records].sort((a, b) => b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id));
    const ids = params.getAll("ids");
    if (ids.length) items = items.filter(item => ids.includes(item.id));
    const before = params.get("beforeCreatedAt");
    if (before) items = items.filter(item => item.createdAt < before || item.createdAt === before && item.id < params.get("beforeId")!);
    await route.fulfill({ json: { items: items.slice(0, Number(params.get("pageSize") || 20)), total: items.length, page: 1, pageSize: 10, totalPages: Math.ceil(items.length / 10) } });
  });
  await page.route(/\/agent\/tasks\/[^/?]+$/, route => {
    const item = records.find(item => route.request().url().endsWith(`/${item.id}`));
    return route.fulfill({ status: item ? 200 : 404, json: item || { detail: "任务不存在" } });
  });
}
const rows = (page: Page) => page.locator(".sidebar-task-list > a.sidebar-task-item");
const refresh = (page: Page) => page.evaluate(() => window.dispatchEvent(new Event("lingjian:tasks-changed")));

test("submission appears before acknowledgement and survives navigation and reload", async ({ page, request }) => {
  const headers = await login(page, request);
  await page.setViewportSize({ width: 1440, height: 900 });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route(`${API}/agent/tasks`, async route => {
    await new Promise(resolve => setTimeout(resolve, 900));
    await route.continue();
  });
  await page.goto("/");
  await expect(page.locator("#history")).toHaveCount(0);
  const requirement = "SIDEBAR_SLOW 即时任务验证";
  await page.locator("#requirement").fill(requirement);
  const accepted = page.waitForResponse(response => response.url() === `${API}/agent/tasks` && response.request().method() === "POST");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page.locator(".pending-task")).toContainText("提交中");
  const response = await accepted;
  expect(response.status()).toBe(202);
  const { recordId } = await response.json();
  const link = page.locator(`.sidebar-task-list a[href="/tasks/${recordId}"]`);
  await expect(link).toContainText("匹配中");
  await expect(page.locator(".pending-task")).toHaveCount(0);
  await link.click();
  await expect(page.getByRole("heading", { name: "任务详情", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator(`a[aria-current="page"][href="/tasks/${recordId}"]`)).toBeVisible();
  await expect(page.getByRole("heading", { name: "需求画像", exact: true })).toBeVisible({ timeout: 25_000 });
  await expect(link).toContainText("已完成");
  expect((await (await request.get(`${API}/agent/tasks?keyword=${encodeURIComponent(requirement)}`, { headers })).json()).total).toBe(1);
  await page.getByRole("link", { name: "开启新任务", exact: true }).click();
  await expect(page.locator("#requirement")).toHaveValue("");
  await expect(link).toHaveCount(1);
  await expect(page.locator("#history")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("ten-row pages preserve scroll, selection and statuses when a new task arrives", async ({ page, request }) => {
  await login(page, request);
  await page.setViewportSize({ width: 1440, height: 900 });
  const records = Array.from({ length: 35 }, (_, i) => task(i + 1));
  await fixture(page, records);
  await page.goto("/");
  await expect(rows(page)).toHaveCount(10);
  const list = page.locator(".sidebar-task-list");
  await expect.poll(() => list.evaluate(el => el.scrollHeight > el.clientHeight)).toBeTruthy();
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(rows(page)).toHaveCount(20);
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(rows(page)).toHaveCount(30);
  const selected = page.locator('a[data-task-id="sidebar-18"]');
  await selected.click();
  await expect(selected).toHaveAttribute("aria-current", "page");
  await selected.scrollIntoViewIfNeeded();
  const before = await selected.evaluate(el => el.getBoundingClientRect().top);
  records.find(item => item.id === "sidebar-18")!.taskStatus = "partial";
  records.unshift(task(0));
  await refresh(page);
  await expect(rows(page)).toHaveCount(31);
  await expect(selected).toContainText("部分完成");
  expect(Math.abs(await selected.evaluate(el => el.getBoundingClientRect().top) - before)).toBeLessThan(3);
  await expect(selected).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(rows(page)).toHaveCount(36);
  await expect(page.getByRole("button", { name: "加载更多" })).toHaveCount(0);
  expect(new Set(await rows(page).evaluateAll(els => els.map(el => el.getAttribute("href")))).size).toBe(36);
  await mkdir("/tmp/lingjian-task-navigation", { recursive: true });
  await page.screenshot({ path: "/tmp/lingjian-task-navigation/sidebar-desktop.png" });
});

test("directly opened older task stays visible without changing the first page", async ({ page, request }) => {
  await login(page, request);
  const records = Array.from({ length: 35 }, (_, i) => task(i + 1));
  await fixture(page, records);
  await page.goto("/tasks/sidebar-35");
  await expect(rows(page)).toHaveCount(10);
  await expect(page.locator('.sidebar-selected-task a[aria-current="page"]')).toContainText("导航验证任务 35");
});

test("load-more failure retains existing rows and retry appends the next ten", async ({ page, request }) => {
  await login(page, request);
  const records = Array.from({ length: 25 }, (_, i) => task(i + 1));
  await fixture(page, records);
  let fail = true;
  await page.route(/\/agent\/tasks\?.*beforeCreatedAt/, route => fail ? route.abort("failed") : route.fallback());
  await page.goto("/");
  await expect(rows(page)).toHaveCount(10);
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".sidebar-task-list")).toContainText("已保留上次状态");
  await expect(rows(page)).toHaveCount(10);
  fail = false;
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(rows(page)).toHaveCount(20);
});

test("lost acknowledgement confirms the same ID without a second submission", async ({ page, request }) => {
  await login(page, request);
  const records: Task[] = [];
  await fixture(page, records);
  let attempts = 0;
  await page.route(`${API}/agent/tasks`, route => {
    attempts += 1;
    const body = route.request().postDataJSON();
    records.unshift({ ...task(0), id: body.requestId, requirement: body.requirement });
    return route.abort("failed");
  });
  await page.goto("/");
  await page.locator("#requirement").fill("确认原任务");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page.locator(".current-task-summary")).toContainText("已完成");
  await expect(rows(page)).toHaveCount(1);
  await expect(page.locator(".pending-task")).toHaveCount(0);
  expect(attempts).toBe(1);
});

test("unconfirmed submission survives reload and only queries its original ID", async ({ page, request }) => {
  await login(page, request);
  const records: Task[] = [];
  await fixture(page, records);
  let attempts = 0;
  let taskId = "";
  await page.route(`${API}/agent/tasks`, route => {
    attempts += 1; taskId = route.request().postDataJSON().requestId;
    return route.abort("failed");
  });
  await page.goto("/");
  await page.locator("#requirement").fill("暂未确认的任务");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page.locator(".pending-task")).toContainText("提交未确认");
  await page.reload();
  await expect(page.locator(".pending-task")).toContainText("待确认的提交");
  records.push({ ...task(0), id: taskId, taskStatus: "failed" });
  await page.getByRole("button", { name: "核对任务", exact: true }).click();
  await expect(page.locator(".pending-task")).toHaveCount(0);
  await expect(rows(page)).toContainText("失败");
  expect(attempts).toBe(1);
});

for (const width of [1024, 768]) {
  test(`task access stays visible at ${width}px and empty new task creates no record`, async ({ page, request }) => {
    await login(page, request);
    await page.setViewportSize({ width, height: 768 });
    const records = Array.from({ length: 15 }, (_, i) => task(i + 1));
    await fixture(page, records);
    let creates = 0;
    page.on("request", request => { if (request.url() === `${API}/agent/tasks` && request.method() === "POST") creates += 1; });
    await page.goto("/");
    await page.getByRole("link", { name: "开启新任务", exact: true }).click();
    await expect(page.getByRole("link", { name: "全部任务", exact: false }).first()).toBeVisible();
    await expect(page.locator("#requirement")).toHaveValue("");
    expect(creates).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    await mkdir("/tmp/lingjian-task-navigation", { recursive: true });
    await page.screenshot({ path: `/tmp/lingjian-task-navigation/sidebar-${width}.png`, fullPage: true });
  });
}

test("starting a blank task during submission keeps the previous job in navigation", async ({ page, request }) => {
  await login(page, request);
  await page.addInitScript(() => Object.defineProperty(Crypto.prototype, "randomUUID", { value: undefined, configurable: true }));
  const records: Task[] = [];
  await fixture(page, records);
  let release!: () => void;
  const acknowledgement = new Promise<void>(resolve => { release = resolve; });
  let taskId = "";
  await page.route(`${API}/agent/tasks`, async route => {
    const body = route.request().postDataJSON(); taskId = body.requestId;
    await acknowledgement;
    records.push({ ...task(0), id: taskId, requirement: body.requirement, taskStatus: "matching" });
    await route.fulfill({ status: 202, json: { recordId: taskId, taskStatus: "matching" } });
  });
  await page.goto("/");
  await page.locator("#requirement").fill("保留后台任务");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page.locator(".pending-task")).toContainText("提交中");
  await page.getByRole("link", { name: "开启新任务", exact: true }).click();
  await expect(page.locator("#requirement")).toHaveValue("");
  expect(taskId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  release();
  await expect(rows(page)).toContainText("匹配中");
  await expect(page.locator(".current-task-summary")).toHaveCount(0);
  await expect(page).toHaveURL(/\/$/);
  await rows(page).click();
  await expect(page.getByText("正在匹配伙伴，状态会自动更新。", { exact: true })).toBeVisible();
  records[0].taskStatus = "failed";
  await expect(page.getByRole("button", { name: "重试任务", exact: true })).toBeVisible();
});

test("detail polling preserves unsaved opportunity fields", async ({ page, request }) => {
  await login(page, request);
  const records = [task(1)];
  await fixture(page, records);
  let status = "enriching";
  await page.route(`${API}/agent/tasks/sidebar-1`, route => route.fulfill({ json: {
    ...records[0], taskStatus: status,
    opportunity: { id: "synthetic-opportunity", customerName: "原客户", projectName: "原项目", completenessScore: 20, followUpQuestions: "[]" },
  } }));
  await page.goto("/tasks/sidebar-1");
  const field = page.locator("form input").first();
  await expect(field).toHaveValue("原客户");
  await field.fill("尚未保存的新客户");
  status = "ready";
  await expect(page.locator(".task-status-notice")).toHaveCount(0);
  await expect(field).toHaveValue("尚未保存的新客户");
});
