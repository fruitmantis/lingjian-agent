import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile } from "node:fs/promises";

const API = "http://127.0.0.1:8100";
const screenshotRoot = "/tmp/lingjian-enablement-batch3/screenshots";

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

async function databaseHash() {
  return createHash("sha256").update(await readFile("/tmp/lingjian-enablement-e2e/app.db")).digest("hex");
}

test("system refresh preserves the database and explains unverified model status", async ({ page, request }) => {
  await login(page, request);
  const before = await databaseHash();
  const pageErrors: string[] = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.goto("/admin/system");
  await expect(page.getByRole("heading", { name: "部分运行状态尚未验证" })).toBeVisible();
  await expect(page.getByText("本页不执行写入测试")).toBeVisible();
  await expect(page.getByText("本页不调用模型；可在模型配置页手动测试连接")).toBeVisible();
  await page.getByRole("button", { name: "刷新状态", exact: true }).click();
  await expect(page.getByRole("heading", { name: "部分运行状态尚未验证" })).toBeVisible();
  expect(await databaseHash()).toBe(before);
  expect(pageErrors).toEqual([]);
});

test("new match and task details display verified evidence and explicit gaps", async ({ page, request }) => {
  const headers = await login(page, request, "user_a");
  await page.goto("/");
  await page.locator("#requirement").fill("第三批验证：寻找制造业知识库项目伙伴");
  const result = page.waitForResponse(response => response.url() === `${API}/agent/tasks` && response.request().method() === "POST");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  const response = await result;
  expect(response.ok()).toBeTruthy();
  const accepted = await response.json();
  await expect.poll(async () => (await (await request.get(`${API}/agent/tasks/${accepted.recordId}`, { headers })).json()).taskStatus).toBe("ready");
  const data = { ...(await (await request.get(`${API}/agent/tasks/${accepted.recordId}`, { headers })).json()), recordId: accepted.recordId };
  expect(data.recommendations).toHaveLength(1);
  expect(data.recommendations[0].evidenceCases).toBe("制造知识库案例");
  // The fake model claims an unregistered deliverable; it must not appear as evidence.
  expect(data.recommendations[0].evidenceDeliverables).toBe("未提供可核实的支撑交付物");
  expect(data.recommendations[0].riskNotes).toContain("缺少可核实的支撑交付物");
  await expect(page.getByText("未提供可核实的支撑交付物", { exact: true }).first()).toBeVisible();
  await page.goto(`/tasks/${data.recordId}`);
  await expect(page.getByText("未提供可核实的支撑交付物", { exact: true })).toBeVisible();
  await expect(page.locator("main").last()).not.toContainText("方案文档");
  await expect(page.getByText("计划时间？", { exact: true })).toBeVisible();
  await expect(page.getByText("供给充足", { exact: true }).first()).toBeVisible();
  await expect(page.getByText('["计划时间？"]', { exact: true })).toHaveCount(0);
  await mkdir(screenshotRoot, { recursive: true });
  await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
  await page.screenshot({ path: `${screenshotRoot}/verified-task.png`, fullPage: true });
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 1024, height: 768 }]) {
  test(`system and model pages remain readable at ${viewport.width}`, async ({ page, request }) => {
    await page.setViewportSize(viewport);
    await login(page, request);
    const pageErrors: string[] = [];
    page.on("pageerror", error => pageErrors.push(error.message));
    await mkdir(screenshotRoot, { recursive: true });
    for (const [name, route, heading] of [
      ["system", "/admin/system", "部分运行状态尚未验证"],
      ["models", "/admin/models", "业务场景模型配置"],
    ]) {
      await page.goto(route);
      await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
      await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
      await page.screenshot({ path: `${screenshotRoot}/${name}-${viewport.width}.png`, fullPage: true });
    }
    expect(pageErrors).toEqual([]);
  });
}
