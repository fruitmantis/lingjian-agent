import {expect,type Page,type APIRequestContext} from '@playwright/test';
export const API = (process.env.PLAYWRIGHT_HTTP_ORIGIN || 'http://localhost') + '/api';
export const origin = { Origin: process.env.PLAYWRIGHT_HTTP_ORIGIN || 'http://localhost' };
export async function localUser(page: Page) { return page.evaluate(() => JSON.parse(localStorage.getItem('banfei:user:user') || 'null')); }
export const loginLink = (page: Page, key: string) => new URL('/#k='+encodeURIComponent(key), page.url()).href;
export async function readLoginLink(page: Page) {
  await expect(page.getByTestId('identity-key')).toHaveText(/^http:\/\/.+\/#k=bf_[\w-]{43}$/);
  const link = (await page.getByTestId('identity-key').textContent())!;
  return { link, key: new URLSearchParams(new URL(link).hash.slice(1)).get('k')! };
}
export async function createIdentity(page: Page) {
  await page.goto('/');
  await expect(page.getByRole('dialog', { name: '欢迎使用伴飞' })).toBeVisible();
  const { key, link } = await readLoginLink(page);
  const user = await localUser(page);
  await page.getByRole('button', { name: '开始使用伴飞' }).click();
  return { key, user, link };
}
export async function keyLogin(page: Page, key: string) {
  await page.goto('/login?method=key');
  const change=page.getByRole('dialog',{name:'切换身份',exact:true});
  if(await change.count()){await change.getByLabel('目标登录链接').fill(key);await change.getByRole('button',{name:'切换',exact:true}).click();await expect(change).toHaveCount(0);}
  else{await page.getByLabel('登录链接',{exact:true}).fill(key);await page.getByRole('button',{name:'登录原身份',exact:true}).click();}
  await expect(page.locator('.sidebar')).toBeVisible();
}
export async function emptyEntry(page:Page){
  await page.context().clearCookies();
  await page.evaluate(()=>{localStorage.removeItem('banfei:user:token');localStorage.removeItem('banfei:user:user');localStorage.removeItem('banfei:user:device-secret');});
  await page.goto('/login?method=key');
  await expect(page.getByLabel('登录链接',{exact:true})).toBeVisible();
}
export async function legacyLogout(page:Page){
  const token=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));
  const response=await page.request.post(API+'/auth/identity/logout',{headers:{...origin,Authorization:'Bearer '+token}});
  expect(response.ok()).toBe(true);
  await page.evaluate(()=>{localStorage.removeItem('banfei:user:token');localStorage.removeItem('banfei:user:user');localStorage.setItem('banfei:user:signed-out','remembered');});
}
export async function adminSession(request: APIRequestContext) {
  const response = await request.post(API+'/auth/admin/login', { data: { username: 'admin1', password: 'ValidationPass123' } });
  expect(response.ok()).toBeTruthy(); return response.json();
}
export async function userCount(request: APIRequestContext, token: string) {
  const response = await request.get(API+'/admin/users', { headers: { Authorization: 'Bearer '+token } });
  return (await response.json()).total;
}
