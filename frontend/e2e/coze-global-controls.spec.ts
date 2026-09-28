import {test,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fixture,partner} from './coze-fixtures';
import {createFontVerification} from './font-verification';

for(const [width,height] of [[1366,768],[1920,1080],[390,844]])test(`global dialogs fonts and compatibility ${width}`,async({page})=>{
  await page.setViewportSize({width,height});const {requests,unexpected}=await fixture(page);
  const typography=await createFontVerification(page),errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const dir=path.resolve(process.env.COZE_ALL_EVIDENCE_DIR || '../artifacts/coze-all-pages','extra');await mkdir(dir,{recursive:true});
  async function capture(name:string,selector:string){
    await page.evaluate(()=>document.fonts.ready);await page.addStyleTag({content:'nextjs-portal{display:none}'});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({path:path.join(dir,`${name}-${width}.png`),mask:[page.locator('input[type=password]'),page.locator('.identity-key-value')]});
    await page.locator(selector).screenshot({path:path.join(dir,`${name}-${width}-detail.png`),mask:[page.locator('input[type=password]')]});
  }
  const admin={id:'ui-admin',username:'ui-admin',display_name:'合成管理员',role:'admin',status:'active',must_change_password:true};
  await page.addInitScript(()=>localStorage.setItem('banfei:admin:token','synthetic-admin'));
  await page.route('**/auth/me',r=>r.fulfill({json:r.request().headers().authorization==='Bearer synthetic-admin'?admin:{...admin,role:'user',must_change_password:false}}));
  await page.goto('/admin/change-password');await expect(page.getByRole('heading',{name:/修改密码/})).toBeVisible();
  await typography.inspect('admin-password');await capture('admin-password','.login-card');
  admin.must_change_password=false;
  await page.route(/:8000\/admin\/partner-materials\?/,r=>r.fulfill({json:{items:[{kind:'case',id:'case-0',partner_id:partner.id,partner_name:partner.name,title:'合成预览材料',description:'正文与附件控件验收。',category_id:'technical-3',visible:true,file_count:1,processing_status:'ready',updated_at:'2026-09-28T02:30:00Z'}],total:1,partners:[partner]}}));
  await page.route('**/cases/case-0/deliverables',r=>r.fulfill({json:[{id:'file-1',filename:'合成材料.txt',file_type:'txt',processing_status:'ready'}]}));
  await page.route('**/cases/case-0/deliverables/file-1/preview',r=>r.fulfill({contentType:'text/plain; charset=utf-8',body:'伙伴交付验证材料\n\nEnterprise Agent 2026\n验证接口、数据一致性与回退流程。\n资料不足不代表缺乏能力。'}));
  await page.goto('/admin/partner-materials');await page.getByRole('button',{name:'查看与管理'}).click();await page.getByRole('button',{name:'在线查看'}).click();
  const viewer=page.getByRole('dialog',{name:'合成材料.txt'});await expect(viewer.locator('pre')).toContainText('Enterprise Agent 2026');
  await expect(viewer.locator('pre')).toHaveCSS('font-family',/Segoe UI/);await expect(viewer.locator('pre')).toHaveCSS('font-size','16px');await expect(viewer.locator('pre')).toHaveCSS('line-height','26px');
  await capture('material-preview','[role=dialog][aria-label="合成材料.txt"]');await viewer.getByRole('button',{name:'关闭'}).click();await expect(viewer).toHaveCount(0);
  await typography.inspect('material-dialog');
  await page.goto('/enablement?partner_id=coze-partner');await expect(page).toHaveURL(/mode=development/);await expect(page.getByLabel('选择目标伙伴')).toHaveValue(partner.id);
  await page.goto('/enablement?tab=resources&resource_type=lab');await expect(page).toHaveURL(/\/resources\?resource_type=lab/);await expect(page.locator('.learning-card')).toHaveCount(6);
  await page.goto('/enablement/resources/course/course-0');await expect(page).toHaveURL(/\/resources\/course\/course-0/);await expect(page.locator('.learning-content')).toBeVisible();
  await page.goto('/admin/partners/coze-partner/cases/case-0/sharing');await expect(page).toHaveURL(/\/admin\/partner-materials\?partner_id=coze-partner/);await expect(page.getByLabel('筛选伙伴')).toHaveValue(partner.id);
  await page.goto('/change-password');await expect(page).toHaveURL(/\/$/);
  expect(errors).toEqual([]);expect(unexpected).toEqual([]);expect(requests.filter(r=>r.method!=='GET')).toEqual([]);
  await writeFile(path.join(dir,`fonts-${width}.json`),JSON.stringify(typography.evidence(),null,2));
});
