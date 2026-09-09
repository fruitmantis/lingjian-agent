import { expect, test } from "@playwright/test";
import { webcrypto } from "node:crypto";
import { execFileSync } from "node:child_process";
import { newTaskId } from "../components/task-navigation";
import { requestTimeoutMs } from "../lib/api-request";

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

test("same-origin proxy preserves direct API model request budgets", () => {
  const cases: [string, string, number][] = [
    ["/agent/match", "POST", 360_000],
    ["/agent/tasks/task-id/retry", "POST", 360_000],
    ["/partners/partner-id/profile", "POST", 180_000],
    ["/admin/model-configs/model-id/test", "POST", 45_000],
    ["/agent/tasks", "GET", 30_000],
  ];
  for (const [path, method, budget] of cases) {
    expect(requestTimeoutMs("http://127.0.0.1:8000" + path, method)).toBe(budget);
    expect(requestTimeoutMs("/api" + path, method)).toBe(budget);
    expect(requestTimeoutMs("http://app.test:3000/api" + path, method)).toBe(budget);
  }
});

test("optional proxy leaves direct development config unchanged", () => {
  const code = `import config from './next.config.mjs'; console.log(JSON.stringify({rules:await config.rewrites(),experimental:config.experimental}));`;
  const run = (extra: Record<string,string>) => JSON.parse(execFileSync(process.execPath, ["--input-type=module", "-e", code], { cwd: process.cwd(), env: { ...process.env, BANFEI_API_PROXY_TARGET: "", BANFEI_BUILD_CPUS: "", ...extra }, encoding: "utf8" }));
  expect(run({})).toEqual({ rules: [] });
  const proxy=run({ BANFEI_API_PROXY_TARGET: "http://127.0.0.1:8000", BANFEI_BUILD_CPUS: "1" });
  expect(proxy.rules).toEqual([{ source: "/api/:path*", destination: "http://127.0.0.1:8000/:path*" }]);
  expect(proxy.experimental).toEqual({ cpus: 1, proxyTimeout: 420_000 });
});
