import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {test, expect} from '@playwright/test';
const API = 'http://localhost/api';

for (const width of [1366, 1920]) test(`admin partner deletion preserves business history ${width}`, async ({page, request}) => {
  // Created by prepare_e2e only in its guarded /tmp fixture directory. No runtime credentials.
  expect(process.env.PLAYWRIGHT_REUSE_SERVER).not.toBe('1');
  const session = JSON.parse(readFileSync(`${process.env.BANFEI_TEST_ROOT}/visual-session.json`,'utf8'));
  expect(session.database).toBe(`postgresql:${new URL(process.env.PLAYWRIGHT_DATABASE_URL!).pathname.slice(1)}`);
  const headers = {Authorization: `Bearer ${session.access_token}`};
  // The ephemeral fixture token cannot authenticate against the private runtime database.
  expect((await request.get(`${API}/partners`,{headers})).status()).toBe(200);
  await page.setViewportSize({width, height: width === 1366 ? 768 : 1080});
  await page.addInitScript(s => {localStorage.setItem(`banfei:${s.user.role}:token`, s.access_token); localStorage.setItem(`banfei:${s.user.role}:user`, JSON.stringify(s.user));}, session);
  const unusedName = `Synthetic unused ${randomUUID()}`;
  const usedName = `Synthetic history ${randomUUID()}`;
  async function create(name: string) {
    const response = await request.post(`${API}/partners`, {headers,data:{name}});
    expect(response.status()).toBe(201); return response.json();
  }
  const unused = await create(unusedName), used = await create(usedName);
  const caseResponse = await request.post(`${API}/cases`, {headers,data:{partner_id:used.id,title:'Synthetic protected case',category_id:'technical-1',description:'Only in temporary E2E database'}});
  expect(caseResponse.status()).toBe(201);
  await page.goto('/admin/partners');
  const unusedRow = page.getByRole('row').filter({has:page.getByRole('cell',{name:unusedName,exact:true})});
  page.once('dialog',dialog => dialog.dismiss());
  await unusedRow.getByRole('button',{name:'删除',exact:true}).click();
  await expect(unusedRow).toBeVisible();
  expect((await request.get(`${API}/partners/${unused.id}`,{headers})).status()).toBe(200);
  page.once('dialog',dialog => dialog.accept());
  const removed = page.waitForResponse(r => r.request().method() === 'DELETE' && r.url() === `${API}/partners/${unused.id}`);
  await unusedRow.getByRole('button',{name:'删除',exact:true}).click();
  expect((await removed).status()).toBe(204);
  await expect(unusedRow).toHaveCount(0);
  await expect(page.getByText('伙伴已删除',{exact:true})).toBeVisible();
  expect((await request.get(`${API}/partners/${unused.id}`,{headers})).status()).toBe(404);
  const usedRow = page.getByRole('row').filter({has:page.getByRole('cell',{name:usedName,exact:true})});
  page.once('dialog',dialog => dialog.accept());
  await usedRow.getByRole('button',{name:'删除',exact:true}).click();
  await expect(page.getByRole('alert').filter({hasText:'无法删除'})).toContainText('案例 1 条');
  await expect(page.getByRole('alert').filter({hasText:'无法删除'})).toContainText('请停用伙伴以保留历史');
  await expect(usedRow).toBeVisible();
  await usedRow.getByRole('button',{name:'停用',exact:true}).click();
  await expect(usedRow.getByRole('button',{name:'启用',exact:true})).toBeVisible();
  await usedRow.getByRole('button',{name:'启用',exact:true}).click();
  await expect(usedRow.getByRole('button',{name:'停用',exact:true})).toBeVisible();
  expect(await (await request.get(`${API}/cases/by-partner/${used.id}`,{headers})).json()).toHaveLength(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

for(const width of [1366,390])test('phase2 visual: admin list leads and editors cancel without writes at '+width,async({page},info)=>{
 await page.setViewportSize({width,height:844});
 const admin={id:'visual-admin',username:'visual-admin',display_name:'合成后台视觉验证',role:'admin',status:'active',must_change_password:false};
 await page.addInitScript(user=>{localStorage.setItem('banfei:admin:token','synthetic-admin-visual');localStorage.setItem('banfei:admin:user',JSON.stringify(user));},admin);
 const writes:string[]=[];
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname.slice(4);
  if(req.method()!=='GET'){writes.push(path);return route.fulfill({status:409,json:{detail:'Unexpected isolated write'}});}
  if(path==='/auth/me')return route.fulfill({json:admin});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/partners')return route.fulfill({json:Array.from({length:5},(_,i)=>({id:'visual-'+i,name:'合成伙伴 '+i,status:'active',capabilities:'合成能力',industries:'金融',ai_profile:null}))});
  return route.fulfill({status:404,json:{detail:'Unexpected isolated read'}});
 });
 await page.goto('/admin/partners');
 await expect(page.getByRole('cell',{name:'合成伙伴 0',exact:true})).toBeVisible();
 expect((await page.locator('.data-table thead').boundingBox())!.y).toBeLessThan(page.viewportSize()!.height-60);
 const editor=page.locator('.partner-admin-disclosure').filter({has:page.locator('summary').filter({hasText:'新增伙伴'})});
 const toggle=editor.locator('summary');
 await expect(editor).not.toHaveAttribute('open','');
 await toggle.focus();await page.keyboard.press('Enter');
 const name=editor.getByRole('textbox',{name:'伙伴名称',exact:true});await page.keyboard.press('Tab');await expect(name).toBeFocused();
 await name.fill('未提交的合成草稿');await page.keyboard.press('Escape');
 await expect(editor).not.toHaveAttribute('open','');await expect(toggle).toBeFocused();
 await toggle.click();await expect(name).toHaveValue('未提交的合成草稿');await editor.getByRole('button',{name:'取消',exact:true}).click();
 await expect(toggle).toBeFocused();
 const menu=page.locator('.partner-list-menu');await menu.locator('summary').click();
 const action=menu.getByRole('button',{name:'批量生成画像',exact:true});await expect(action).toBeVisible();await action.focus();await page.keyboard.press('Escape');
 await expect(menu).not.toHaveAttribute('open','');await expect(menu.locator('summary')).toBeFocused();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(writes).toEqual([]);
 await page.screenshot({path:info.outputPath('phase2-admin-partners-'+width+'.png'),fullPage:true});
 let release!:()=>void;const transfer=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/api/partners/template',async route=>{await transfer;await route.fulfill({body:'synthetic download only',contentType:'application/octet-stream'});});
 const imports=page.locator('.partner-admin-disclosure').filter({has:page.locator('summary').filter({hasText:'Excel 导入导出'})});
 await imports.locator('summary').click();await imports.getByRole('button',{name:'下载导入模板',exact:true}).click();
 await expect(page.getByText('正在处理伙伴导入或导出…',{exact:true})).toBeVisible();
 await imports.locator('summary').focus();await page.keyboard.press('Escape');
 await expect(imports).not.toHaveAttribute('open','');
 await expect(page.getByText('正在处理伙伴导入或导出…',{exact:true})).toBeVisible();
 release();await expect(page.getByText('模板已下载，按表头和使用说明填写后导入。',{exact:true})).toBeVisible();expect(writes).toEqual([]);

});
