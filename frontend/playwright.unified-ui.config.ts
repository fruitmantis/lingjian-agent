import {defineConfig} from '@playwright/test';
import base from './playwright.config';
export default defineConfig({...base,testMatch:[
 '**/coze-all-pages.spec.ts','**/coze-global-controls.spec.ts','**/coze-ui.spec.ts',
 '**/ui-system.spec.ts','**/sidebar-visual.spec.ts','**/opportunity-ui.spec.ts',
 '**/task-failure.spec.ts','**/unified-answer.spec.ts','**/feedback.spec.ts',
 '**/partner-filters.spec.ts','**/partner-tags.spec.ts',
],timeout:300_000,use:{...base.use,deviceScaleFactor:1},reporter:[['line'],['json',{outputFile:process.env.COZE_REPORT_FILE || '/tmp/banfei-ui-all-pages/regression-results.json'}]]});
