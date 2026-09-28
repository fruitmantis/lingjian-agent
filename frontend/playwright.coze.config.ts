import {defineConfig} from '@playwright/test';
import base from './playwright.config';

// Same isolated PostgreSQL harness; bounded UI fixtures never contact a model.
export default defineConfig({
  ...base,
  testMatch: ['**/coze-ui.spec.ts', '**/task-failure.spec.ts', '**/unified-answer.spec.ts'],
  timeout: 90_000,
  reporter: [['line'], ['json', {outputFile: '/tmp/banfei-coze-results.json'}]],
});
