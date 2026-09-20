import { expect, test, type Page } from "@playwright/test";

// All API traffic is fulfilled locally. Never changes a real user's password.
async function fixture(page: Page, options: { authenticated?: boolean; forced?: boolean; role?: "user" | "admin"; residualTask?: boolean } = {}) {
  const authenticated = options.authenticated ?? true;
  let user = { id: "password-ui", username: "password-ui", display_name: "改密验证", role: options.role ?? "user", status: "active", must_change_password: options.forced ?? true };
  const restoredTask = { id: "11111111-2222-4333-8444-555555555555", createdAt: "2026-09-20T00:00:00Z", requirement: "残留待确认任务", taskStatus: "ready" };
  const storageKey = `lingjian:pending-tasks:${user.id}`;
  const savedTasks = [{ id: restoredTask.id, createdAt: restoredTask.createdAt }];
  const changes: { current_password: string; new_password: string }[] = [];
  const earlyBusiness: string[] = [];
  const taskRequests: string[] = [];
  await page.addInitScript(({ user, authenticated, residualTask, storageKey, savedTasks }) => {
    if (authenticated && !localStorage.getItem("token")) {
      localStorage.setItem("token", "synthetic-password-session"); localStorage.setItem("user", JSON.stringify(user));
    }
    if (residualTask && !sessionStorage.getItem(storageKey)) sessionStorage.setItem(storageKey, JSON.stringify(savedTasks));
  }, { user, authenticated, residualTask: options.residualTask, storageKey, savedTasks });
  await page.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.port !== "8000" && !url.pathname.startsWith("/api/")) return route.continue();
    const path = url.pathname.replace(/^\/api/, "");
    if (path === "/auth/login") return route.fulfill({ json: { access_token: "synthetic-password-session", user } });
    if (path === "/auth/me") {
      if (!route.request().headers().authorization) return route.fulfill({ status: 401, json: { detail: "请先登录" } });
      return route.fulfill({ json: user });
    }
    if (path === "/auth/change-password") {
      expect(route.request().method()).toBe("POST");
      const body = route.request().postDataJSON(); changes.push(body);
      if (body.current_password !== "CurrentPass123") return route.fulfill({ status: 400, json: { detail: "当前密码不正确" } });
      user = { ...user, must_change_password: false };
      return route.fulfill({ json: { access_token: "synthetic-updated-session", user } });
    }
    if (path === "/health") return route.fulfill({ json: { status: "ok" } });
    if (!route.request().headers().authorization || user.must_change_password || new URL(page.url()).pathname === "/change-password") earlyBusiness.push(path);
    if (path.startsWith("/agent/tasks")) taskRequests.push(path);
    if (path === `/agent/tasks/${restoredTask.id}`) return route.fulfill({ json: restoredTask });
    return route.fulfill({ json: path === "/agent/tasks" ? { items: [], total: 0, hasMore: false } : [] });
  });
  return { changes, earlyBusiness, taskRequests, restoredTask, storageKey, savedTasks };
}

for (const width of [1366, 1920]) test(`first login uses standalone page and enters workspace after password change ${width}`, async ({ page }) => {
  const state = await fixture(page, { authenticated: false });
  await page.setViewportSize({ width, height: width === 1366 ? 768 : 1080 });
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill("password-ui");
  await page.getByLabel("密码", { exact: true }).fill("CurrentPass123");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/change-password$/);
  await expect(page.getByRole("heading", { name: "请先修改密码", exact: true })).toBeVisible();
  await expect(page.locator(".sidebar, .topbar-new")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "个人中心", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("当前密码", { exact: true })).toHaveValue("");
  expect(state.earlyBusiness).toEqual([]);
  await page.getByLabel("当前密码", { exact: true }).fill("CurrentPass123");
  await page.getByLabel("新密码", { exact: true }).fill("ChangedPass456");
  await page.getByLabel("确认新密码", { exact: true }).fill("DifferentPass456");
  await page.getByRole("button", { name: "修改密码并进入", exact: true }).click();
  await expect(page.locator(".password-change-card [role=alert]")).toHaveText("两次输入的新密码不一致");
  expect(state.changes).toHaveLength(0);
  await page.getByLabel("当前密码", { exact: true }).fill("WrongPass123");
  await page.getByLabel("确认新密码", { exact: true }).fill("ChangedPass456");
  await page.getByRole("button", { name: "修改密码并进入", exact: true }).click();
  await expect(page.locator(".password-change-card [role=alert]")).toHaveText("当前密码不正确");
  await expect(page).toHaveURL(/\/change-password$/);
  await page.getByLabel("当前密码", { exact: true }).fill("CurrentPass123");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `/tmp/banfei-first-login-${width}.png`, fullPage: true });
  await page.getByRole("button", { name: "修改密码并进入", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "开启新任务", exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("token"))).toBe("synthetic-updated-session");
  expect(state.changes).toHaveLength(2);
});

for (const role of ["user", "admin"] as const) test(`forced ${role} cannot bypass the page with direct or legacy links`, async ({ page }) => {
  const state = await fixture(page, { role, residualTask: true });
  for (const path of ["/", "/account?changePassword=1", "/tasks", "/admin", "/change-password"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/change-password$/);
    await expect(page.getByRole("heading", { name: "请先修改密码", exact: true })).toBeVisible();
    await expect(page.locator(".sidebar")).toHaveCount(0);
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "请先修改密码", exact: true })).toBeVisible();
  expect(state.earlyBusiness).toEqual([]);
  expect(state.taskRequests).toEqual([]);
  expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key) || "[]"), state.storageKey)).toEqual(state.savedTasks);
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate(() => localStorage.getItem("token"))).toBeNull();
});

test("anonymous users cannot open the standalone password form", async ({ page }) => {
  const state = await fixture(page, { authenticated: false, residualTask: true });
  await page.goto("/change-password");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "请先修改密码", exact: true })).toHaveCount(0);
  expect(state.taskRequests).toEqual([]);
  expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key) || "[]"), state.storageKey)).toEqual(state.savedTasks);
});

test("residual tasks resume only after forced password change completes", async ({ page }) => {
  const state = await fixture(page, { authenticated: false, residualTask: true });
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill("password-ui");
  await page.getByLabel("密码", { exact: true }).fill("CurrentPass123");
  expect(state.taskRequests).toEqual([]);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/change-password$/);
  await expect(page.getByRole("heading", { name: "请先修改密码", exact: true })).toBeVisible();
  await page.reload();
  await page.getByLabel("当前密码", { exact: true }).fill("CurrentPass123");
  await page.getByLabel("新密码", { exact: true }).fill("ChangedPass456");
  await page.getByLabel("确认新密码", { exact: true }).fill("ChangedPass456");
  expect(state.taskRequests).toEqual([]);
  expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key) || "[]"), state.storageKey)).toEqual(state.savedTasks);
  await page.getByRole("button", { name: "修改密码并进入", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "开启新任务", exact: true })).toBeVisible();
  await expect.poll(() => state.taskRequests).toContain(`/agent/tasks/${state.restoredTask.id}`);
  expect(state.earlyBusiness).toEqual([]);
  await expect.poll(() => page.evaluate(key => JSON.parse(sessionStorage.getItem(key) || "[]"), state.storageKey)).toEqual([]);
});

test("normal accounts keep personal-center password maintenance", async ({ page }) => {
  const state = await fixture(page, { forced: false, residualTask: true });
  await page.goto("/change-password");
  await expect(page).toHaveURL(/\/$/);
  await expect.poll(() => state.taskRequests).toContain(`/agent/tasks/${state.restoredTask.id}`);
  expect(state.earlyBusiness).toEqual([]);
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "个人中心", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "修改密码", exact: true })).toBeVisible();
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.getByText("首次登录必须修改临时密码", { exact: false })).toHaveCount(0);
});
