import { expect, test } from "@playwright/test";

const origin = process.env.PLAYWRIGHT_HTTP_ORIGIN;
test.use({ screenshot: "off", trace: "off" });
test("actual-IP HTTP entry keeps identity, copy fallback and tabs consistent", async ({ browser, request }) => {
  test.skip(!origin || new URL(origin).hostname === "localhost", "Explicit actual-IP HTTP origin required");
  const health = await request.get(origin + "/api/health", { maxRedirects: 0 });
  expect(health.status()).toBe(200);
  const icon = await request.get(origin + "/icon.svg", { maxRedirects: 0 });
  expect(icon.status()).toBe(200);
  const context = await browser.newContext({ baseURL: origin });
  const first = await context.newPage();
  const second = await context.newPage();
  const browserEndpoints: string[] = [];
  for (const page of [first, second]) {
    page.on("request", request => browserEndpoints.push(request.url()));
    page.on("websocket", socket => browserEndpoints.push(socket.url()));
  }
  try {
    await Promise.all([first.goto("/"), second.goto("/")]);
    await expect(first.locator(".sidebar")).toBeVisible();
    await expect(second.locator(".sidebar")).toBeVisible();
    const id = await first.evaluate(() => JSON.parse(localStorage.getItem("banfei:user:user") || "null")?.id);
    expect(await second.evaluate(() => JSON.parse(localStorage.getItem("banfei:user:user") || "null")?.id)).toBe(id);
    expect(await first.evaluate(() => isSecureContext)).toBe(false);
    const cookie = (await context.cookies()).find(item => item.name === "banfei_http_identity_session")!;
    expect(cookie).toBeTruthy();
    expect(cookie.secure).toBe(false);
    expect(cookie.httpOnly).toBe(true);
    expect(cookie.sameSite).toBe("Strict");
    const firstDialog = first.getByRole("dialog", { name: "保存你的身份 Key" });
    if (await firstDialog.isVisible()) await firstDialog.getByRole("button", { name: "稍后保存" }).click();
    await first.goto("/account");
    await expect(first.getByTestId("identity-key")).toHaveText(/^bf_[\w-]{43}$/);
    const key = (await first.getByTestId("identity-key").textContent())!;
    expect(key).toMatch(/^bf_[\w-]{43}$/);
    await first.getByRole("button", { name: "复制 Key" }).click();
    await expect.poll(async () => await first.getByText(/Key 已复制|Ctrl\+C/).count()).toBeGreaterThan(0);
    const result = await first.getByRole("status").filter({ hasText: /Key 已复制/ }).count();
    if (!result) {
      await expect(first.getByRole("alert").filter({ hasText: /Ctrl\+C/ })).toBeVisible();
      expect(await first.evaluate(() => window.getSelection()?.toString())).toBe(key);
    }
    await first.evaluate(() => {
      Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
      Object.defineProperty(document, "execCommand", { value: () => false, configurable: true });
    });
    await first.getByRole("button", { name: "复制 Key" }).click();
    await expect(first.getByRole("alert").filter({ hasText: /Ctrl\+C/ })).toBeVisible();
    expect(await first.evaluate(() => window.getSelection()?.toString())).toBe(key);
    const downloaded = first.waitForEvent("download");
    await first.getByRole("button", { name: "下载凭据 .txt" }).click();
    expect((await downloaded).suggestedFilename()).toBe("伴飞-身份凭据.txt");
    await first.reload();
    expect(await first.evaluate(() => JSON.parse(localStorage.getItem("banfei:user:user") || "null")?.id)).toBe(id);

    const other = await browser.newContext({ baseURL: origin });
    try {
      const third = await other.newPage();
      await third.goto("/");
      const thirdDialog = third.getByRole("dialog", { name: "保存你的身份 Key" });
      await expect(thirdDialog.getByTestId("identity-key")).toHaveText(/^bf_[\w-]{43}$/);
      const otherKey = (await thirdDialog.getByTestId("identity-key").textContent())!;
      const otherId = await third.evaluate(() => JSON.parse(localStorage.getItem("banfei:user:user") || "null")?.id);
      expect(otherId).not.toBe(id);
      await first.goto("/login?method=key");
      await first.getByLabel("身份 Key", { exact: true }).fill(otherKey);
      await first.getByRole("button", { name: "登录原身份", exact: true }).click();
      await expect.poll(() => first.evaluate(() => JSON.parse(localStorage.getItem("banfei:user:user") || "null")?.id)).toBe(otherId);
      await expect.poll(() => second.evaluate(() => JSON.parse(localStorage.getItem("banfei:user:user") || "null")?.id)).toBe(otherId);
      await first.getByRole("button", { name: "退出", exact: true }).click();
      await expect(first.getByRole("heading", { name: "已退出伴飞" })).toBeVisible();
      await expect(second.getByRole("heading", { name: "已退出伴飞" })).toBeVisible();
      await second.reload();
      await expect(second.getByRole("heading", { name: "已退出伴飞" })).toBeVisible();
      await first.goto("/login?method=key");
      await first.getByLabel("身份 Key", { exact: true }).fill(key);
      await first.getByRole("button", { name: "登录原身份", exact: true }).click();
      await expect(first.locator(".sidebar")).toBeVisible();
      await expect.poll(() => first.evaluate(() => JSON.parse(localStorage.getItem("banfei:user:user") || "null")?.id)).toBe(id);
    } finally { await other.close(); }
    const refused = await request.post(origin + "/api/auth/identity/session", {
      headers: { Origin: "http://untrusted.invalid" }, data: { create: true }, maxRedirects: 0,
    });
    expect(refused.status()).toBe(403);
    expect(browserEndpoints.length).toBeGreaterThan(0);
    expect(browserEndpoints.filter(url => ["3000", "8000"].includes(new URL(url).port))).toEqual([]);
  } finally { await context.close(); }
});
