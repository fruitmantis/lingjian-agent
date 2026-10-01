import { expect, test } from "@playwright/test";
import { webcrypto } from "node:crypto";
import { execFileSync } from "node:child_process";
import { newTaskId } from "../components/task-navigation";
import { modelRequestCalls, modelRequestBudgetMs, type ModelTimeoutSettings } from "../lib/api-request";

test("HTTP origins without randomUUID keep safe unique submission IDs", () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  Object.defineProperty(globalThis, "crypto", { configurable: true, value: { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) } });
  try {
    const ids = Array.from({ length: 100 }, () => newTaskId());
    expect(new Set(ids).size).toBe(100);
    for (const id of ids) expect(id).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "crypto", descriptor);
    else Reflect.deleteProperty(globalThis, "crypto");
  }
});

const policy: ModelTimeoutSettings = {timeoutSeconds:300, timeoutRetries:3};
const requestTimeoutMs = (input: string, method: string) => modelRequestCalls(input, method) ? modelRequestBudgetMs(policy, modelRequestCalls(input, method)) : 30_000;

test("same-origin proxy preserves direct API model request budgets", () => {
  const cases: [string, string, number][] = [
    ["/agent/match", "POST", 3_630_000],
    ["/agent/tasks/task-id/retry", "POST", 3_630_000],
    ["/partners/partner-id/profile", "POST", 3_630_000],
    ["/admin/model-configs/model-id/test", "POST", 1_230_000],
    ["/agent/tasks", "POST", 30_000],
    ["/development/plans", "POST", 30_000],
    ["/development/plans/plan-id/revise", "POST", 30_000],
    ["/development/plans/plan-id/retry", "POST", 30_000],
    ["/agent/tasks", "GET", 30_000],
    ["/development/plans/plan-id/conversation", "POST", 30_000],
  ];
  for (const [path, method, budget] of cases) {
    expect(requestTimeoutMs("http://localhost/api" + path, method)).toBe(budget);
    expect(requestTimeoutMs("/api" + path, method)).toBe(budget);
    expect(requestTimeoutMs("http://app.test:3000/api" + path, method)).toBe(budget);
  }
});

test("proxy configuration has no build-time model timeout setting", () => {
  const code = `import config from './next.config.mjs'; console.log(JSON.stringify(config));`;
  const result = JSON.parse(execFileSync(process.execPath, ["--input-type=module", "-e", code], {
    cwd: process.cwd(), env: {...process.env, BANFEI_BUILD_CPUS:"1", BANFEI_API_PROXY_TARGET:"http://127.0.0.1:8000"}, encoding:"utf8"}));
  expect(result).toEqual({experimental:{cpus:1}});
});

test("current policy determines timeout and retry budget without a rebuild", () => {
  expect(modelRequestBudgetMs({timeoutSeconds:60, timeoutRetries:1})).toBe(150_000);
  expect(modelRequestBudgetMs({timeoutSeconds:60, timeoutRetries:1}, 2)).toBe(270_000);
  expect(modelRequestBudgetMs({timeoutSeconds:60, timeoutRetries:0})).toBe(90_000);
  expect(modelRequestCalls("/api/agent/tasks", "GET")).toBe(0);
  expect(modelRequestCalls("/api/agent/match", "POST")).toBe(3);
  expect(modelRequestCalls("/api/agent/tasks/task-id/retry", "POST")).toBe(3);
  expect(modelRequestCalls("/api/partners/partner-id/profile", "POST")).toBe(3);
});
