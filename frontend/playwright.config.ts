import { randomBytes } from "node:crypto";
import { defineConfig } from "@playwright/test";

// Default: UI-only checks, no model service. Explicit replay is engineering regression,
// never a claim that a real supplier or real business output passed validation.
const replay = process.env.PLAYWRIGHT_MODEL_MODE === "replay";
if (process.env.PLAYWRIGHT_MODEL_MODE && !["ui", "replay"].includes(process.env.PLAYWRIGHT_MODEL_MODE)) {
  throw new Error("Use the bounded real-model smoke tool for real provider validation");
}
const validationDatabase = process.env.PLAYWRIGHT_DATABASE_URL;
if (!validationDatabase) throw new Error('Use scripts/run_postgres_validation.py browser with BANFEI_TEST_DATABASE_URL');
const databaseUrl = new URL(validationDatabase);
if (!["postgresql:", "postgresql+psycopg:"].includes(databaseUrl.protocol) || !["/banfei_validation", "/banfei_agent_test"].includes(databaseUrl.pathname) || !["127.0.0.1", "localhost"].includes(databaseUrl.hostname) || !/^-csearch_path=validation_[0-9a-f]{32}$/.test(databaseUrl.searchParams.get('options') || '') || [...databaseUrl.searchParams.keys()].some(key => key !== 'options')) {
  throw new Error('Dedicated local PostgreSQL validation schema required');
}
const testRoot = process.env.BANFEI_TEST_ROOT;
if (!testRoot || !/^\/tmp\/banfei-e2e-[A-Za-z0-9_-]+$/.test(testRoot)) throw new Error('Owned browser test directory required');
process.env.DATABASE_URL = validationDatabase;
process.env.LINGJIAN_UPLOADS_DIR = `${testRoot}/uploads`;
const httpOrigin = process.env.PLAYWRIGHT_HTTP_ORIGIN || "http://localhost";
const allowedOrigins = [...new Set([httpOrigin, "http://localhost"])].join(",");
const validationEnvironment = {
  DATABASE_URL: validationDatabase,
  BANFEI_TEST_ROOT: testRoot,
  BANFEI_ERROR_LOG_PATH: `${testRoot}/errors.jsonl`,
  BANFEI_IDENTITY_ENCRYPTION_KEY: randomBytes(32).toString("base64"),
  LINGJIAN_UPLOADS_DIR: `${testRoot}/uploads`,
  LINGJIAN_CHROMA_DIR: `${testRoot}/chroma`,
  JWT_SECRET_KEY: "e2e-validation-secret-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  BOOTSTRAP_ADMIN_USERNAME: "unused_bootstrap",
  BOOTSTRAP_ADMIN_PASSWORD: "UnusedBootstrap123",
  USER_APPLICATION_RATE_LIMIT: "1000",
  USER_APPLICATION_PENDING_LIMIT: "200",
  VALIDATION_FAKE_LLM_BASE_URL: replay ? "http://127.0.0.1:18180/v1" : "",
  BANFEI_IDENTITY_ORIGIN: allowedOrigins,
  CORS_ORIGINS: allowedOrigins,
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: replay ? "**/*.spec.ts" : [
    "**/business-taxonomy.spec.ts", "**/partner-delete.spec.ts", "**/model-boundary.spec.ts", "**/resource-transfer.spec.ts",
    "**/partner-materials.spec.ts", "**/partner-profile-report.spec.ts", "**/partner-select.spec.ts", "**/pagination.spec.ts", "**/arm-runtime.spec.ts", "**/model-timeout-settings.spec.ts", "**/model-timeout-transport.spec.ts", "**/task-failure.spec.ts", "**/feedback.spec.ts", "**/first-login.spec.ts", "**/local-identity.spec.ts",
    "**/http-identity.spec.ts", "**/task-progress.spec.ts", "**/task-transition.spec.ts", "**/home-scenes.spec.ts", "**/home-scenes-boundaries.spec.ts", "**/agent-settings.spec.ts",
  ],
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [["line"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",
  use: {
    baseURL: httpOrigin,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    ...(replay ? [{
      command: ".venv/bin/python -m uvicorn backend.tests.support.fake_llm_server:app --host 127.0.0.1 --port 18180",
      cwd: "..",
      url: "http://127.0.0.1:18180/health",
      env: validationEnvironment,
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === "1",
      timeout: 30_000,
    }] : []),
    {
      command: ".venv/bin/python -m backend.tests.support.prepare_e2e && .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000",
      cwd: "..",
      url: "http://127.0.0.1:8000/health",
      env: validationEnvironment,
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === "1",
      timeout: 30_000,
    },
    {
      command: "npm run dev -- -p 3000 -H 127.0.0.1",
      cwd: ".",
      url: "http://127.0.0.1:3000/login",
      env: { NEXT_PUBLIC_API_BASE_URL: "/api", BANFEI_API_PROXY_TARGET: "http://127.0.0.1:8000", BANFEI_IDENTITY_ORIGIN: allowedOrigins },
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === "1",
      timeout: 60_000,
    },
    {
      command: "../.isolation/tools/caddy run --config ../deploy/Caddyfile --adapter caddyfile",
      cwd: ".",
      url: httpOrigin + "/api/health",
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === "1",
      timeout: 30_000,
    },
  ],
});
