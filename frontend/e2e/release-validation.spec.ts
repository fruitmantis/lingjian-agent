import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const API_BASE = "http://127.0.0.1:8100";
const DEFAULT_PASSWORD = "ValidationPass123";

type LoginResult = { access_token: string; user: Record<string, unknown> };

async function apiLogin(request: APIRequestContext, username: string, password = DEFAULT_PASSWORD): Promise<LoginResult> {
  const response = await request.post(`${API_BASE}/auth/login`, { data: { username, password } });
  expect(response.ok(), `API login failed for ${username}: ${response.status()}`).toBeTruthy();
  return await response.json() as LoginResult;
}

async function loginInBrowser(page: Page, username: string, password = DEFAULT_PASSWORD) {
  await page.goto("/login");
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

async function loggedPage(browser: Browser, request: APIRequestContext, username: string, password = DEFAULT_PASSWORD) {
  const session = await apiLogin(request, username, password);
  const context = await browser.newContext();
  await context.addInitScript(({ token, user }) => {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user));
  }, { token: session.access_token, user: session.user });
  return { context, page: await context.newPage(), session };
}

test.describe.configure({ mode: "serial" });

test("E2E-001 login and public application page render", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "灵鉴 Agent" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "账号登录" })).toBeVisible();
  await page.getByRole("tab", { name: "注册" }).click();
  await expect(page.getByRole("heading", { name: "注册" })).toBeVisible();
});

test("E2E-002 application approval and forced first-login password change", async ({ browser }) => {
  const applicantContext = await browser.newContext();
  const applicant = await applicantContext.newPage();
  await applicant.goto("/login");
  await applicant.getByRole("tab", { name: "注册" }).click();
  await applicant.locator("#applyName").fill("端到端申请人");
  await applicant.locator("#applyUsername").fill("e2e_applicant");
  await applicant.locator("#applyDepartment").fill("验证部门");
  await applicant.locator("#applyContact").fill("e2e_applicant@company.example");
  await applicant.locator("#applyPassword").fill("ApplicantPass123");
  await applicant.locator("#applyConfirmPassword").fill("ApplicantPass123");
  await applicant.locator("#applyReason").fill("发布前自动化验证");
  await applicant.getByRole("button", { name: "提交" }).click();
  await expect(applicant.getByText("账号申请已提交", { exact: false })).toBeVisible();
  await applicantContext.close();

  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  await loginInBrowser(admin, "admin1");
  await admin.goto("/admin/users?tab=applications");
  const row = admin.locator("tbody tr").filter({ hasText: "e2e_applicant" });
  await expect(row).toBeVisible();
  admin.once("dialog", dialog => dialog.accept());
  await row.getByRole("button", { name: "批准" }).click();
  await expect(admin.getByText("账号 e2e_applicant 已开通", { exact: false })).toBeVisible();
  await adminContext.close();

  const firstLoginContext = await browser.newContext();
  const firstLogin = await firstLoginContext.newPage();
  await loginInBrowser(firstLogin, "e2e_applicant", "ApplicantPass123");
  await expect(firstLogin).toHaveURL(/\/account\?changePassword=1/);
  await expect(firstLogin.getByText("首次登录必须修改临时密码", { exact: false })).toBeVisible();
  await firstLogin.locator("#currentPassword").fill("ApplicantPass123");
  await firstLogin.locator("#newPassword").fill("ApplicantChanged456");
  await firstLogin.locator("#confirmPassword").fill("ApplicantChanged456");
  await firstLogin.getByRole("button", { name: "修改密码" }).click();
  await expect(firstLogin.getByText("密码已修改，其他登录状态已失效")).toBeVisible();
  await firstLoginContext.close();
});

test("E2E-003 ordinary users see only their own tasks and cannot enter admin", async ({ browser }) => {
  const userAContext = await browser.newContext();
  const userA = await userAContext.newPage();
  await loginInBrowser(userA, "user_a");
  await userA.goto("/tasks");
  await expect(userA.locator("main").getByText("A-ready", { exact: true })).toBeVisible();
  await expect(userA.locator("main").getByText("B-ready", { exact: true })).toHaveCount(0);
  await userA.goto("/tasks/task-b-ready");
  await expect(userA.getByRole("heading", { name: "无法查看任务" })).toBeVisible();
  await userA.goto("/admin");
  await expect(userA).toHaveURL(/\/403$/);
  await expect(userA.getByText("无权访问", { exact: false })).toBeVisible();
  await userAContext.close();

  const userBContext = await browser.newContext();
  const userB = await userBContext.newPage();
  await loginInBrowser(userB, "user_b");
  await userB.goto("/tasks");
  await expect(userB.locator("main").getByText("B-ready", { exact: true })).toBeVisible();
  await expect(userB.locator("main").getByText("A-ready", { exact: true })).toHaveCount(0);
  await userBContext.close();
});

test("E2E-004 administrator sees all task owners and user management", async ({ page }) => {
  await loginInBrowser(page, "admin1");
  await page.goto("/admin/tasks");
  await expect(page.getByText("A-ready", { exact: true })).toBeVisible();
  await expect(page.getByText("B-ready", { exact: true })).toBeVisible();
  await page.goto("/admin/users");
  await expect(page.getByRole("heading", { name: "用户管理" })).toBeVisible();
  await expect(page.getByText("user_a", { exact: true })).toBeVisible();
});

test("E2E-005 disabling a user and changing a password invalidate old sessions", async ({ browser, request }) => {
  const admin = await apiLogin(request, "admin1");
  const userA = await loggedPage(browser, request, "user_a");
  await userA.page.goto("/tasks");
  await expect(userA.page.locator("main.page > h1", { hasText: "我的任务" })).toBeVisible();
  let response = await request.patch(`${API_BASE}/admin/users/user-a-id/status`, {
    headers: { Authorization: `Bearer ${admin.access_token}` }, data: { status: "disabled" },
  });
  expect(response.ok()).toBeTruthy();
  await userA.page.reload();
  await expect(userA.page).toHaveURL(/\/login$/);
  await userA.context.close();
  response = await request.patch(`${API_BASE}/admin/users/user-a-id/status`, {
    headers: { Authorization: `Bearer ${admin.access_token}` }, data: { status: "active" },
  });
  expect(response.ok()).toBeTruthy();

  const userB = await apiLogin(request, "user_b");
  response = await request.post(`${API_BASE}/auth/change-password`, {
    headers: { Authorization: `Bearer ${userB.access_token}` },
    data: { current_password: DEFAULT_PASSWORD, new_password: "ChangedPass456" },
  });
  expect(response.ok()).toBeTruthy();
  const oldSession = await request.get(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${userB.access_token}` } });
  expect(oldSession.status()).toBe(401);
  await apiLogin(request, "user_b", "ChangedPass456");
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
  await adminUsers.page.route(/^http:\/\/127\.0\.0\.1:8100\/admin\/users\?/, route => route.abort("connectionrefused"));
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
          localStorage.setItem("token", token); localStorage.setItem("user", JSON.stringify(user));
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
