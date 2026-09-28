import {defineConfig} from '@playwright/test';
import base from './playwright.config';
export default defineConfig({...base,testMatch:['**/coze-polish.spec.ts','**/coze-ui.spec.ts','**/task-failure.spec.ts','**/unified-answer.spec.ts'],timeout:180_000,use:{...base.use,deviceScaleFactor:1},reporter:[['line'],['json',{outputFile:'/tmp/banfei-coze-polish/results.json'}]]});
