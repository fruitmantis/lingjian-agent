import {fixtureLogin} from "./identity-fixture";
import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const API_BASE = "http://localhost:8000";
const DEFAULT_PASSWORD = "ValidationPass123";

type LoginResult = { access_token: string; user: Record<string, unknown> };

async function apiLogin(request: APIRequestContext, username: string, password = DEFAULT_PASSWORD): Promise<LoginResult> {
  const response = await fixtureLogin(request, username, password);
  expect(response.ok(), `API login failed for ${username}: ${response.status()}`).toBeTruthy();
  return await response.json() as LoginResult;
}

async function loginInBrowser(page: Page, username: string, password = DEFAULT_PASSWORD) {
  if (username.startsWith("user_")) {
    const session = await apiLogin(page.request, username, password);
    await page.addInitScript(s => { localStorage.setItem("banfei:user:token", s.access_token); localStorage.setItem("banfei:user:user", JSON.stringify(s.user)); }, session);
    await page.goto("/"); return;
  }
  await page.goto("/admin/login"); await page.locator("#username").fill(username); await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click(); await expect(page).not.toHaveURL(/\/login$/);
}

async function loggedPage(browser: Browser, request: APIRequestContext, username: string, password = DEFAULT_PASSWORD) {
  const session = await apiLogin(request, username, password);
  const context = await browser.newContext();
  await context.addInitScript(({ token, user }) => {
    localStorage.setItem(`banfei:${user.role}:token`, token); localStorage.setItem(`banfei:${user.role}:user`, JSON.stringify(user));
  }, { token: session.access_token, user: session.user });
  return { context, page: await context.newPage(), session };
}

test.describe.configure({ mode: "serial" });

test("E2E-001 ordinary entry has no password or application", async ({ page }) => {
  await page.goto("/"); await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.locator("#username, #applyName")).toHaveCount(0);
  await page.getByRole("button", {name:"稍后保存"}).click();
  await page.goto("/account"); await expect(page.getByRole("heading", {name:"修改密码"})).toHaveCount(0);
});

test("E2E-002 administrator forced password flow has its own route", async ({ page, request }) => {
  const admin = await apiLogin(request, "admin1");
  const created = await (await request.post(API_BASE+"/admin/users", {headers:{Authorization:`Bearer ${admin.access_token}`}, data:{username:"release_admin",display_name:"发布验证",role:"admin"}})).json();
  await loginInBrowser(page, created.user.username, created.temporaryPassword);
  await expect(page).toHaveURL(/\/admin\/change-password$/);
  await page.getByLabel("当前密码",{exact:true}).fill(created.temporaryPassword);
  await page.getByLabel("新密码",{exact:true}).fill("ReleaseAdmin123");
  await page.getByLabel("确认新密码",{exact:true}).fill("ReleaseAdmin123");
  await page.getByRole("button",{name:"修改密码并进入"}).click();await expect(page).toHaveURL(/\/admin$/);
});

test("E2E-003 ordinary users retain owner isolation", async ({ browser, request }) => {
  const a = await loggedPage(browser,request,"user_a"); const b = await loggedPage(browser,request,"user_b");
  try {
    await a.page.goto("/tasks");await expect(a.page.getByRole("cell",{name:"A-ready",exact:true})).toBeVisible();await expect(a.page.getByRole("cell",{name:"B-ready",exact:true})).toHaveCount(0);
    expect((await request.get(API_BASE+"/agent/tasks/task-b-ready",{headers:{Authorization:`Bearer ${a.session.access_token}`}})).status()).toBe(404);
    await a.page.goto("/admin/tasks");await expect(a.page).toHaveURL(/\/admin\/login$/);
    await b.page.goto("/tasks");await expect(b.page.getByRole("cell",{name:"B-ready",exact:true})).toBeVisible();
  } finally {await a.context.close();await b.context.close();}
});

test("E2E-004 admin task detail stays in admin scope", async ({ page }) => {
  await loginInBrowser(page,"admin1");await page.goto("/admin/tasks");
  const row=page.locator("tbody tr").filter({hasText:"A-ready"});await row.getByRole("link",{name:"详情",exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/tasks\/task-a-ready/);await expect(page.locator(".admin-layout")).toBeVisible();
  await page.goto("/admin/users");await expect(page.getByRole("heading",{name:"用户管理"})).toBeVisible();await expect(page.getByRole("button",{name:"账号申请"})).toHaveCount(0);
});

test("E2E-005 disabled local identity and changed admin password invalidate tokens", async ({ request }) => {
  const admin=await apiLogin(request,"admin1");
  const ordinary=await (await request.post(API_BASE+"/auth/identity/session",{headers:{Origin:"http://localhost:3000"},data:{create:true}})).json();
  expect((await request.patch(API_BASE+`/admin/users/${ordinary.user.id}/status`,{headers:{Authorization:`Bearer ${admin.access_token}`},data:{status:"disabled"}})).ok()).toBeTruthy();
  expect((await request.get(API_BASE+"/auth/me",{headers:{Authorization:`Bearer ${ordinary.access_token}`}})).status()).toBe(401);
  await request.patch(API_BASE+`/admin/users/${ordinary.user.id}/status`,{headers:{Authorization:`Bearer ${admin.access_token}`},data:{status:"active"}});
  const second=await apiLogin(request,"admin2");
  const changed=await request.post(API_BASE+"/auth/change-password",{headers:{Authorization:`Bearer ${second.access_token}`},data:{current_password:DEFAULT_PASSWORD,new_password:"ChangedAdmin123"}});
  expect(changed.ok()).toBeTruthy();expect((await request.get(API_BASE+"/auth/me",{headers:{Authorization:`Bearer ${second.access_token}`}})).status()).toBe(401);
  await request.post(API_BASE+"/auth/change-password",{headers:{Authorization:`Bearer ${(await changed.json()).access_token}`},data:{current_password:"ChangedAdmin123",new_password:DEFAULT_PASSWORD}});
});

test("E2E-006 failed tasks retry while completed tasks return conflict", async ({ page, request }) => {
  await loginInBrowser(page, "user_b", "ChangedPass456");
  await page.goto("/tasks");
  const failedRow = page.locator("tbody tr").filter({ hasText: "B-failed" });
  await expect(failedRow).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await failedRow.getByRole("button", { name: "重试", exact: true }).click();
  await expect(failedRow.getByText("已完成", { exact: true })).toBeVisible();

  const session = await apiLogin(request, "user_b", "ChangedPass456");
  const conflict = await request.post(`${API_BASE}/agent/tasks/task-b-ready/retry`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  expect(conflict.status()).toBe(409);
});

test("E2E-007 API failures, not-found, forbidden, and network timeout are controlled", async ({ browser, request }) => {
  const pageErrors: string[] = [];
  const user = await loggedPage(browser, request, "user_a");
  user.page.on("pageerror", error => pageErrors.push(error.message));
  await user.page.route("**/agent/tasks?**", route => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "验证用服务异常" }) }));
  await user.page.goto("/tasks");
  await expect(user.page.getByText("验证用服务异常")).toBeVisible();
  await expect(user.page.getByText("加载中...")).toHaveCount(0);
  await user.page.unroute("**/agent/tasks?**");
  await user.page.goto("/tasks/not-found-validation-task");
  await expect(user.page.getByRole("heading", { name: "无法查看任务" })).toBeVisible();
  await user.context.close();

  const admin = await loggedPage(browser, request, "admin1");
  admin.page.on("pageerror", error => pageErrors.push(error.message));
  await admin.page.route("**/partners?include_disabled=true", route => route.abort("timedout"));
  await admin.page.goto("/admin/partners");
  await expect(admin.page.getByText(/伙伴加载失败|网络连接中断/)).toBeVisible();
  await expect(admin.page.getByText("加载中...")).toHaveCount(0);
  await admin.context.close();
  expect(pageErrors).toEqual([]);
});

test("E2E-009 workbench and key admin pages handle upstream and backend outages", async ({ browser, request }) => {
  const pageErrors: string[] = [];
  const user = await loggedPage(browser, request, "user_a");
  user.page.on("pageerror", error => pageErrors.push(error.message));
  await user.page.route("**/agent/tasks", route => route.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ detail: "上游模型服务不可用" }) }));
  await user.page.goto("/");
  await user.page.locator("#requirement").fill("验证 502 错误处理");
  await user.page.getByRole("button", { name: /开始匹配/ }).click();
  await expect(user.page.locator(".assistant-error")).toContainText("提交结果暂未确认");
  await expect(user.page.getByRole("button", { name: /开始匹配/ })).toBeEnabled();
  await user.context.close();

  const adminUsers = await loggedPage(browser, request, "admin1");
  adminUsers.page.on("pageerror", error => pageErrors.push(error.message));
  await adminUsers.page.route(/^http:\/\/localhost:8000\/admin\/users\?/, route => route.abort("connectionrefused"));
  await adminUsers.page.goto("/admin/users");
  await expect(adminUsers.page.getByText(/用户加载失败|网络连接中断/)).toBeVisible();
  await expect(adminUsers.page.getByText("加载中...")).toHaveCount(0);
  await adminUsers.context.close();

  const models = await loggedPage(browser, request, "admin1");
  models.page.on("pageerror", error => pageErrors.push(error.message));
  await models.page.route("**/admin/model-configs**", route => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "验证用模型配置异常" }) }));
  await models.page.goto("/admin/models");
  await expect(models.page.getByText("模型配置加载失败")).toBeVisible();
  await expect(models.page.getByRole("button", { name: "重试" })).toBeVisible();
  await models.context.close();

  const overview = await loggedPage(browser, request, "admin1");
  overview.page.on("pageerror", error => pageErrors.push(error.message));
  await overview.page.route("**/admin/dashboard", route => route.fulfill({ status: 502, contentType: "application/json", body: "{}" }));
  await overview.page.goto("/admin");
  await expect(overview.page.getByText("概览加载失败")).toBeVisible();
  await overview.context.close();

  const opportunities = await loggedPage(browser, request, "admin1");
  opportunities.page.on("pageerror", error => pageErrors.push(error.message));
  await opportunities.page.route("**/admin/demand-profiles", route => route.abort("failed"));
  await opportunities.page.goto("/admin/opportunities");
  await expect(opportunities.page.getByText(/网络连接中断|需求画像加载失败/)).toBeVisible();
  await expect(opportunities.page.getByText("加载中...")).toHaveCount(0);
  await opportunities.context.close();
  expect(pageErrors).toEqual([]);
});

for (const viewport of [
  { width: 1920, height: 1080 }, { width: 1440, height: 900 },
  { width: 1366, height: 768 }, { width: 1024, height: 768 },
]) {
  test(`E2E-008-${viewport.width} key pages render without page-level overflow`, async ({ browser, request }) => {
    const screenshotRoot = process.env.VALIDATION_SCREENSHOT_DIR || path.resolve(process.cwd(), "../.isolation/evidence/regression");
    await mkdir(screenshotRoot, { recursive: true });
    const routes = [
      { name: "login", url: "/login", user: null },
      { name: "user-home", url: "/", user: "user_a" },
      { name: "user-scenes", url: "/scenes", user: "user_a" },
      { name: "user-tasks", url: "/tasks", user: "user_a" },
      { name: "user-task-detail", url: "/tasks/task-a-ready", user: "user_a" },
      { name: "admin-home", url: "/admin", user: "admin1" },
      { name: "admin-users", url: "/admin/users", user: "admin1" },
      { name: "admin-partners", url: "/admin/partners", user: "admin1" },
    ];
    const sessions = new Map<string, LoginResult>();
    sessions.set("user_a", await apiLogin(request, "user_a"));
    sessions.set("admin1", await apiLogin(request, "admin1"));
    for (const route of routes) {
      const context = await browser.newContext({ viewport });
      if (route.user) {
        const session = sessions.get(route.user)!;
        await context.addInitScript(({ token, user }) => {
          localStorage.setItem(`banfei:${user.role}:token`, token); localStorage.setItem(`banfei:${user.role}:user`, JSON.stringify(user));
        }, { token: session.access_token, user: session.user });
      }
      const page = await context.newPage();
      await page.goto(route.url);
      await page.locator("main").last().waitFor({ state: "visible" });
      await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
      await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
      await page.screenshot({ path: path.join(screenshotRoot, `${route.name}-${viewport.width}x${viewport.height}.png`), fullPage: true });
      await context.close();
    }
  });
}
