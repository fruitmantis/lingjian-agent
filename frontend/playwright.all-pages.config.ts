import {defineConfig} from '@playwright/test';
import base from './playwright.config';
export default defineConfig({...base,testMatch:['**/coze-all-pages.spec.ts'],timeout:300_000,use:{...base.use,deviceScaleFactor:1},reporter:[['line'],['json',{outputFile:'/tmp/banfei-ui-all-pages/results.json'}]]});
