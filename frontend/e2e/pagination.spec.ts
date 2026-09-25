import { test, expect, type Page, type Locator } from "@playwright/test";
import { ENABLED_SCENES } from "../lib/scenes";

// All API traffic is intercepted. No user, resource, task or model writes.
async function fixture(page: Page) {
  const requests: URL[] = [];
  const state = { resourceTotal: 29 };
  await page.addInitScript(() => {
    for (const role of ["user", "admin"]) localStorage.setItem(`banfei:${role}:token`, `pagination-${role}`);
  });
  await page.route(/https?:\/\/(?:localhost|127\.0\.0\.1):8000\//, async route => {
    expect(route.request().method()).toBe("GET");
    const url = new URL(route.request().url()), path = url.pathname, p = url.searchParams;
    requests.push(url);
    const number = Number(p.get("page") || 1);
    const slice = <T,>(total: number, size: number, make: (n: number) => T, start = (number - 1) * size) =>
      Array.from({ length: Math.max(0, Math.min(size, total - start)) }, (_, i) => make(start + i + 1));
    let json: unknown;
    if (path === "/auth/me") json = { id: "pagination-actor", username: "分页验收", display_name: "分页验收",
      role: route.request().headers().authorization === "Bearer pagination-admin" ? "admin" : "user",
      status: "active", must_change_password: false };
    else if (path === "/enablement/resource-filters") json = { roles: [{ id: "role-1", name: "迁移工程师" }], zones: [], capabilities: [] };
    else if (path === "/enablement/resources") {
      const total = p.get("q") === "无结果" ? 0 : state.resourceTotal;
      json = { total, items: slice(total, 12, n => ({ source_type: p.get("source_type"), source_id: `resource-${n}`,
        source_version: 1, title: `分页资源 ${n}`, summary: "仅用于分页验证", capabilities: [], roles: [], zones: [],
        level: "basic", source_platform: "测试来源", status: "published", review: null })) };
    } else if (path === "/agent/tasks" || path === "/admin/tasks") {
      const sidebar = p.get("pageSize") !== "20", total = sidebar ? 0 : 45;
      json = { total, totalPages: Math.ceil(total / 20), page: number, pageSize: 20,
        items: slice(total, 20, n => ({ id: `task-${n}`, requirement: `分页任务 ${n}`, topPartner: "合成伙伴", partnerCount: 1,
          task_type: "partner_match", taskStatus: "ready", createdAt: "2026-09-25T08:00:00Z", archivedAt: null,
          ownerName: "合成用户", department: null, completenessScore: null, lastErrorStage: null })) };
    } else if (path === "/admin/users") json = { total: 45, page: number, items: slice(45, 20, n => ({
      id: `user-${n}`, username: `分页用户 ${n}`, display_name: null, role: "user", status: "active",
      must_change_password: false, auth_methods: ["identity_key"], identity_key_hint: null,
    })) };
    else if (path === "/admin/user-audit-logs") json = { total: 235, page: number, items: slice(235, 20, n => ({
      id: `audit-${n}`, action: "auth.login", summary: `分页日志 ${n}`, createdAt: "2026-09-25T08:00:00Z",
    })) };
    else if (path === "/admin/feedback") json = { total: 65, items: slice(65, 30, n => ({
      id: `feedback-${n}`, created_at: "2026-09-25T08:00:00Z", submitter: "合成用户", summary: `分页反馈 ${n}`,
      screenshot_count: 0, status: "pending",
    }), Number(p.get("offset") || 0)) };
    else if (path === "/admin/demand-profiles") json = { overview: { totalDemands: 25, thisMonthDemands: 25,
      gapDemandCount: 25, avgPartnerCount: 1, topCapabilityTags: "数据库" }, industryDistribution: {}, capabilityDistribution: {},
      regionDistribution: {}, deliveryTypeDistribution: {}, profiles: Array.from({ length: 25 }, (_, i) => ({
        id: `demand-${i + 1}`, requirementText: `分页需求 ${i + 1}`, supplyStatus: "gap", matchedPartnerCount: 0,
        createdAt: "2026-09-25T08:00:00Z", complexityLevel: "低", urgencyLevel: "低",
      })) };
    else if (path === "/admin/opportunities") json = Array.from({ length: 25 }, (_, i) => ({
      id: `opportunity-${i + 1}`, projectName: `分页机会 ${i + 1}`, customerName: "合成客户", industry: "制造", region: "广东",
      projectStage: "规划", supplyStatus: "partial", completenessScore: 50,
    }));
    else return route.fulfill({ status: 404, json: { detail: "Unexpected isolated request" } });
    return route.fulfill({ json });
  });
  return { requests, state };
}

async function jump(nav: Locator, number: number, enter = false) {
  await nav.getByRole("textbox", { name: "跳转页码" }).fill(String(number));
  if (enter) await nav.getByRole("textbox", { name: "跳转页码" }).press("Enter");
  else await nav.getByRole("button", { name: "跳转", exact: true }).click();
  await expect(nav.locator(".pagination-position")).toContainText(`第 ${number} 页`);
}

for (const source of ["course", "lab", "case"]) test(`PAG resource ${source} totals, jump and boundaries`, async ({ page }) => {
  const { requests } = await fixture(page);
  await page.goto(`/resources?resource_type=${source}`);
  const nav = page.getByRole("navigation", { name: "资源分页" });
  await expect(nav).toContainText("共 3 页");
  await expect(nav.getByRole("button", { name: "上一页" })).toBeDisabled();
  for (const invalid of ["", "0", "-1", "1.5", "abc", "999"]) {
    await nav.getByRole("textbox").fill(invalid); await nav.getByRole("button", { name: "跳转", exact: true }).click();
    await expect(nav.getByRole("alert")).toContainText("1～3");
    await expect(nav).toContainText("第 1 页");
  }
  await jump(nav, 3, true);
  await expect(page.getByRole("link", { name: "分页资源 25", exact: true })).toBeVisible();
  await expect(nav.getByRole("button", { name: "下一页" })).toBeDisabled();
  await nav.getByRole("button", { name: "上一页" }).click(); await expect(nav).toContainText("第 2 页");
  await nav.getByRole("button", { name: "下一页" }).click(); await expect(nav).toContainText("第 3 页");
  const resourceQueries = requests.filter(u => u.pathname === "/enablement/resources");
  expect(resourceQueries.every(u => ["1", "2", "3"].includes(u.searchParams.get("page")!))).toBeTruthy();
  if (source !== "case") {
    await page.getByLabel("搜索课程或实验").fill("无结果");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await expect(nav).toContainText("共 0 条"); await expect(nav).toContainText("第 1 页 / 共 1 页");
    await expect(nav.getByRole("textbox")).toBeDisabled();
  }
});

test("PAG resource refresh clamps a vanished last page and fits a narrow screen", async ({ page }, testInfo) => {
  const { state, requests } = await fixture(page); await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/resources"); const nav = page.getByRole("navigation", { name: "资源分页" });
  await jump(nav, 3); state.resourceTotal = 13;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(nav).toContainText("第 2 页 / 共 2 页");
  await expect(page.getByRole("link", { name: "分页资源 13", exact: true })).toBeVisible();
  expect(requests.filter(u => u.pathname === "/enablement/resources").at(-1)?.searchParams.get("page")).toBe("2");
  const box = await nav.boundingBox(); expect(box!.x).toBeGreaterThanOrEqual(0); expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  for (const control of await nav.locator("button,input").all()) {
    const bounds = await control.boundingBox(); expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  }
  await expect(nav.getByRole("textbox")).toHaveCSS("height", "32px");
  await expect(nav.getByRole("button", { name: "跳转", exact: true })).toHaveCSS("height", "32px");
  await nav.screenshot({ path: testInfo.outputPath("pagination-mobile.png") });
  await page.setViewportSize({ width: 1366, height: 900 });
  await nav.screenshot({ path: testInfo.outputPath("pagination-desktop.png") });
});

for (const path of ["/tasks", "/admin/tasks"]) test(`PAG ${path} keeps archived and search filters when jumping`, async ({ page }) => {
  const { requests } = await fixture(page); await page.goto(path);
  await page.getByRole("button", { name: "已归档", exact: true }).click();
  await page.getByPlaceholder("搜索需求内容").fill("数据库");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  const nav = page.getByRole("navigation", { name: "任务分页" });
  await expect(nav).toContainText("共 3 页"); await jump(nav, 3);
  await expect(page.getByText("分页任务 41", { exact: true })).toBeVisible();
  const query = requests.filter(u => u.pathname === (path.startsWith("/admin") ? "/admin/tasks" : "/agent/tasks") && u.searchParams.get("pageSize") === "20").at(-1)!;
  expect(query.searchParams.get("status")).toBe("archived"); expect(query.searchParams.get("keyword")).toBe("数据库");
});

test("PAG users and audit logs keep separate pages", async ({ page }) => {
  await fixture(page); await page.goto("/admin/users");
  const users = page.getByRole("navigation", { name: "用户分页", exact: true });
  await expect(users).toContainText("共 3 页"); await jump(users, 2);
  await expect(page.getByRole("link", { name: "分页用户 21", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "操作日志", exact: true }).click();
  const audit = page.getByRole("navigation", { name: "用户操作日志分页" });
  await expect(audit).toContainText("共 12 页"); await jump(audit, 12);
  await expect(page.getByText("分页日志 221", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "账号列表", exact: true }).click();
  await expect(users).toContainText("第 2 页");
});

test("PAG feedback translates page number to offset", async ({ page }) => {
  const { requests } = await fixture(page); await page.goto("/admin/feedback");
  const nav = page.getByRole("navigation", { name: "问题反馈分页" });
  await expect(nav).toContainText("共 3 页"); await jump(nav, 3);
  await expect(page.getByRole("link", { name: "分页反馈 61" })).toBeVisible();
  expect(requests.filter(u => u.pathname === "/admin/feedback").at(-1)?.searchParams.get("offset")).toBe("60");
});

test("PAG demand and supply gap lists jump independently and retain size controls", async ({ page }) => {
  await fixture(page); await page.goto("/admin/demands");
  const demand = page.getByRole("navigation", { name: "需求画像分页" }), gap = page.getByRole("navigation", { name: "供需缺口分页" });
  await expect(demand).toContainText("共 3 页"); await jump(demand, 3); await expect(gap).toContainText("第 1 页");
  await jump(gap, 2); await expect(demand).toContainText("第 3 页");
  await demand.getByLabel("每页条数").selectOption("50");
  await expect(demand).toContainText("第 1 页 / 共 1 页");
  await demand.getByLabel("每页条数").selectOption("10"); await expect(demand).toContainText("共 3 页");
});

test("PAG opportunities jump and reset on filtering", async ({ page }) => {
  await fixture(page); await page.goto("/admin/opportunities");
  const nav = page.getByRole("navigation", { name: "项目机会分页" });
  await expect(nav).toContainText("共 3 页"); await jump(nav, 3);
  await expect(page.getByText("分页机会 21", { exact: true })).toBeVisible();
  await page.getByRole("searchbox").fill("数据库"); await expect(nav).toContainText("第 1 页");
});

test("PAG scenes show totals, jump and recalculate when changing page size", async ({ page }) => {
  await fixture(page); await page.goto("/scenes");
  const nav = page.getByRole("navigation", { name: "场景分页" });
  const last = Math.ceil(ENABLED_SCENES.length / 6);
  await expect(nav).toContainText(`共 ${last} 页`); await jump(nav, last);
  await expect(nav.getByRole("button", { name: "下一页" })).toBeDisabled();
  await expect(nav.getByLabel("每页条数")).toHaveCSS("height", "32px");
  await nav.getByLabel("每页条数").selectOption("12");
  await expect(nav).toContainText(`第 1 页 / 共 ${Math.ceil(ENABLED_SCENES.length / 12)} 页`);
});
