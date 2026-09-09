import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {test, expect} from '@playwright/test';
const API = 'http://127.0.0.1:8000';

for (const width of [1366, 1920]) test(`admin partner deletion preserves business history ${width}`, async ({page, request}) => {
  // Created by prepare_e2e only in its guarded /tmp fixture directory. No runtime credentials.
  expect(process.env.PLAYWRIGHT_REUSE_SERVER).not.toBe('1');
  const session = JSON.parse(readFileSync('/tmp/lingjian-enablement-e2e/visual-session.json','utf8'));
  expect(session.database).toBe(process.env.PLAYWRIGHT_DATABASE_URL?.startsWith('postgresql') ? 'postgresql:banfei_validation' : '/tmp/lingjian-enablement-e2e/app.db');
  const headers = {Authorization: `Bearer ${session.access_token}`};
  // The ephemeral fixture token cannot authenticate against the private runtime database.
  expect((await request.get(`${API}/partners`,{headers})).status()).toBe(200);
  await page.setViewportSize({width, height: width === 1366 ? 768 : 1080});
  await page.addInitScript(s => {localStorage.setItem('token',s.access_token); localStorage.setItem('user',JSON.stringify(s.user));}, session);
  const unusedName = `Synthetic unused ${randomUUID()}`;
  const usedName = `Synthetic history ${randomUUID()}`;
  async function create(name: string) {
    const response = await request.post(`${API}/partners`, {headers,data:{name}});
    expect(response.status()).toBe(201); return response.json();
  }
  const unused = await create(unusedName), used = await create(usedName);
  const caseResponse = await request.post(`${API}/cases`, {headers,data:{partner_id:used.id,title:'Synthetic protected case',description:'Only in temporary E2E database'}});
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
