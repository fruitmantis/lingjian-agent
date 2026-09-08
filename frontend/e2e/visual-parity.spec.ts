import { expect, test, type APIRequestContext, type Browser } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const API_BASE = "http://127.0.0.1:8000";
const DEFAULT_PASSWORD = "ValidationPass123";

type LoginResult = { access_token: string; user: Record<string, unknown> };

async function apiLogin(request: APIRequestContext, username: string): Promise<LoginResult> {
  const response = await request.post(`${API_BASE}/auth/login`, { data: { username, password: DEFAULT_PASSWORD } });
  expect(response.ok(), `API login failed for ${username}: ${response.status()}`).toBeTruthy();
  return await response.json() as LoginResult;
}

test("capture cloudbao visual parity pages and validate browser health", async ({ browser, request }) => {
  const screenshotRoot = path.resolve(process.cwd(), "../.isolation/evidence/visual-regression");
  await mkdir(screenshotRoot, { recursive: true });
  const sessions = new Map<string, LoginResult>();
  sessions.set("user_a", await apiLogin(request, "user_a"));
  sessions.set("admin1", await apiLogin(request, "admin1"));

  const routes = [
    { name: "home-1920x1080", url: "/", user: "user_a", viewport: { width: 1920, height: 1080 } },
    { name: "home-1440x900", url: "/", user: "user_a", viewport: { width: 1440, height: 900 } },
    { name: "home-1366x768", url: "/", user: "user_a", viewport: { width: 1366, height: 768 } },
    { name: "home-1024x768", url: "/", user: "user_a", viewport: { width: 1024, height: 768 } },
    { name: "scenes-1920x1080", url: "/scenes", user: "user_a", viewport: { width: 1920, height: 1080 } },
    { name: "scenes-1440x900", url: "/scenes", user: "user_a", viewport: { width: 1440, height: 900 } },
    { name: "scenes-1366x768", url: "/scenes", user: "user_a", viewport: { width: 1366, height: 768 } },
    { name: "scenes-1024x768", url: "/scenes", user: "user_a", viewport: { width: 1024, height: 768 } },
    { name: "tasks-1440x900", url: "/tasks", user: "user_a", viewport: { width: 1440, height: 900 } },
    { name: "task-detail-1440x900", url: "/tasks/task-a-ready", user: "user_a", viewport: { width: 1440, height: 900 } },
    { name: "admin-home-1440x900", url: "/admin", user: "admin1", viewport: { width: 1440, height: 900 } },
    { name: "admin-users-1440x900", url: "/admin/users", user: "admin1", viewport: { width: 1440, height: 900 } },
  ];

  for (const route of routes) {
    const context = await browser.newContext({ viewport: route.viewport });
    const session = sessions.get(route.user)!;
    await context.addInitScript(({ token, user }) => {
      localStorage.setItem("token", token);
      localStorage.setItem("user", JSON.stringify(user));
    }, { token: session.access_token, user: session.user });
    const page = await context.newPage();
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];
    const requestFailures: string[] = [];
    page.on("pageerror", error => pageErrors.push(error.message));
    page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("requestfailed", request => requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || "failed"}`));
    await page.goto(route.url);
    await page.locator("main").last().waitFor({ state: "visible" });
    await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    await expect.poll(async () => page.evaluate(() => document.body.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
    await page.screenshot({ path: path.join(screenshotRoot, `${route.name}.png`), fullPage: false });
    expect(pageErrors, `${route.name} page errors`).toEqual([]);
    expect(consoleErrors, `${route.name} console errors`).toEqual([]);
    expect(requestFailures, `${route.name} request failures`).toEqual([]);
    await context.close();
  }
});
