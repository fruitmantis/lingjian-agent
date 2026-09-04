import { defineConfig } from "@playwright/test";

const validationEnvironment = {
  LINGJIAN_DATABASE_PATH: "/tmp/lingjian-agent-e2e/app.db",
  LINGJIAN_UPLOADS_DIR: "/tmp/lingjian-agent-e2e/uploads",
  LINGJIAN_CHROMA_DIR: "/tmp/lingjian-agent-e2e/chroma",
  JWT_SECRET_KEY: "e2e-validation-secret-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  BOOTSTRAP_ADMIN_USERNAME: "unused_bootstrap",
  BOOTSTRAP_ADMIN_PASSWORD: "UnusedBootstrap123",
  TASK_STALE_SECONDS: "2",
  USER_APPLICATION_RATE_LIMIT: "1000",
  USER_APPLICATION_PENDING_LIMIT: "200",
  VALIDATION_FAKE_LLM_BASE_URL: "http://127.0.0.1:18080/v1",
  CORS_ORIGINS: "http://127.0.0.1:3100,http://localhost:3100",
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [["line"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: ".venv/bin/python -m uvicorn backend.tests.support.fake_llm_server:app --host 127.0.0.1 --port 18080",
      cwd: "..",
      url: "http://127.0.0.1:18080/health",
      env: validationEnvironment,
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === "1",
      timeout: 30_000,
    },
    {
      command: ".venv/bin/python -m backend.tests.support.prepare_e2e && .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 18000",
      cwd: "..",
      url: "http://127.0.0.1:18000/health",
      env: validationEnvironment,
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === "1",
      timeout: 30_000,
    },
    {
      command: "npm run dev -- -p 3100",
      cwd: ".",
      url: "http://127.0.0.1:3100/login",
      env: { NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:18000" },
      reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === "1",
      timeout: 60_000,
    },
  ],
});
