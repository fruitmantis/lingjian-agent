import { test, expect, chromium, type Page, type APIRequestContext } from '@playwright/test';
import { resolve } from 'node:path';
import { existsSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const API = 'http://localhost:8000';
const origin = { Origin: 'http://localhost:3000' };
async function localUser(page: Page) { return page.evaluate(() => JSON.parse(localStorage.getItem('banfei:user:user') || 'null')); }
async function createIdentity(page: Page) {
  await page.goto('/');
  await expect(page.getByRole('dialog', { name: '保存你的身份 Key' })).toBeVisible();
  await expect(page.getByTestId('identity-key')).toHaveText(/^bf_[\w-]{43}$/);
  const key = (await page.getByTestId('identity-key').textContent())!;
  const user = await localUser(page);
  await page.getByRole('button', { name: '稍后保存' }).click();
  return { key, user };
}
async function keyLogin(page: Page, key: string) {
  await page.goto('/login?method=key'); await page.getByLabel('身份 Key', { exact: true }).fill(key);
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.locator('.sidebar')).toBeVisible();
}
async function adminSession(request: APIRequestContext) {
  const response = await request.post(API+'/auth/admin/login', { data: { username: 'admin1', password: 'ValidationPass123' } });
  expect(response.ok()).toBeTruthy(); return response.json();
}
async function userCount(request: APIRequestContext, token: string) {
  const response = await request.get(API+'/admin/users', { headers: { Authorization: 'Bearer '+token } });
  return (await response.json()).total;
}

test('first visit enters automatically, same Key in popup/account, copy download and reload', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  let creations = 0;
  page.on('request', r => { if (r.url().endsWith('/auth/identity/session') && r.postDataJSON()?.create) creations++; });
  await page.goto('/');
  const dialog = page.getByRole('dialog', { name: '保存你的身份 Key' }); await expect(dialog).toBeVisible();
  await expect(page.getByTestId('identity-key')).toHaveText(/^bf_[\w-]{43}$/);
  const key = (await page.getByTestId('identity-key').textContent())!; const user = await localUser(page);
  await page.getByRole('button', { name: '复制 Key', exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(key);
  const downloadEvent = page.waitForEvent('download'); await page.getByRole('button', { name: '下载凭据 .txt' }).click();
  const download = await downloadEvent; expect(download.suggestedFilename()).toBe('伴飞-身份凭据.txt');
  expect(readFileSync((await download.path())!, 'utf8')).toContain(key);
  await page.screenshot({ path: test.info().outputPath('identity-key-popup.png') });
  await page.getByRole('button', { name: '稍后保存' }).click(); await expect(dialog).toHaveCount(0);
  await page.goto('/account'); await expect(page.getByRole('heading', { name: '身份凭据' })).toBeVisible();
  await expect(page.getByTestId('identity-key')).toHaveText(key);
  await page.getByRole('button', { name: '复制 Key', exact: true }).click(); expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(key);
  const personalDownloadEvent = page.waitForEvent('download'); await page.getByRole('button', { name: '下载凭据 .txt' }).click();
  expect(readFileSync((await (await personalDownloadEvent).path())!, 'utf8')).toContain(key);
  await page.reload(); await expect(page.getByTestId('identity-key')).toHaveText(key);
  expect((await localUser(page)).id).toBe(user.id); expect(creations).toBe(1);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('identity-key-account.png'), fullPage: true });
});

test('saved Key restores same user and history after site data loss without creating users', async ({ page, context, request }) => {
  const original = await createIdentity(page);
  const taskId = execFileSync(resolve('../.venv/bin/python'), ['-m', 'backend.tests.support.seed_identity_history', original.user.id], { cwd: resolve('..'), encoding: 'utf8' }).trim();
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  await context.clearCookies(); await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await keyLogin(page, original.key);
  expect((await localUser(page)).id).toBe(original.user.id);
  await page.goto('/tasks'); await expect(page.getByRole('cell', { name: '退出身份保留的个人任务', exact: true })).toBeVisible();
  await page.reload(); await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(original.user.id);
  expect(await userCount(request, admin.access_token)).toBe(before);
  await page.goto('/account'); await expect(page.getByTestId('identity-key')).toHaveText(original.key);
  expect((await page.request.get(API+'/agent/tasks/'+taskId, { headers: { Authorization: 'Bearer '+await page.evaluate(() => localStorage.getItem('banfei:user:token')) } })).ok()).toBeTruthy();
});

test('explicit Key entry and invalid input never create users or request business history', async ({ page, request }) => {
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  let business = 0, creations = 0;
  await page.addInitScript(() => sessionStorage.setItem('lingjian:pending-tasks:residual', JSON.stringify([{ id: 'missing-task' }])));
  page.on('request', r => { if (r.url().includes('/agent/tasks')) business++; if (r.url().endsWith('/session') && r.postDataJSON()?.create) creations++; });
  await page.goto('/login'); await page.getByLabel('身份 Key', { exact: true }).fill('incorrect-key');
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.locator('form [role=alert]')).toHaveText('身份 Key 格式不正确，请检查后重试。');
  expect(await localUser(page)).toBeNull(); expect(await userCount(request, admin.access_token)).toBe(before);
  expect(business).toBe(0); expect(creations).toBe(0);
});

test('popup existing-Key action switches identity without another user or merge', async ({ page, browser, request }) => {
  const original = await createIdentity(page);
  const otherContext = await browser.newContext(); const other = await otherContext.newPage();
  try {
    await other.goto('/'); await expect(other.getByRole('dialog')).toBeVisible(); const temporary = await localUser(other);
    const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
    await other.getByRole('button', { name: '已有 Key？登录原身份' }).click();
    await other.getByLabel('身份 Key', { exact: true }).fill(original.key);
    await other.getByRole('button', { name: '登录原身份', exact: true }).click();
    await expect(other.locator('.sidebar')).toBeVisible(); expect((await localUser(other)).id).toBe(original.user.id);
    expect(temporary.id).not.toBe(original.user.id); expect(await userCount(request, admin.access_token)).toBe(before);
  } finally { await otherContext.close(); }
});

test('logout retains browser identity, explicitly continues without Key after restart', async ({ page, context, browser, request }) => {
  const original = await createIdentity(page); const oldToken = await page.evaluate(() => localStorage.getItem('banfei:user:token'));
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  const oldCookie = (await context.cookies()).find(c => c.name === 'banfei_identity_session')!.value;
  await page.getByRole('button', { name: '退出', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/); await expect(page.getByRole('heading', { name: '已退出伴飞' })).toBeVisible();
  expect(await localUser(page)).toBeNull(); expect((await context.cookies()).find(c => c.name === 'banfei_identity_session')!.value).not.toBe(oldCookie);
  await expect(page.getByRole('button', { name: '继续使用当前身份' })).toBeVisible();
  await expect(page.getByLabel('身份 Key', { exact: true })).toHaveCount(0);
  await page.screenshot({path:test.info().outputPath('remembered-identity-continue.png')});
  let businessAfterLogout=0;page.on('request',r=>{if(r.url().includes('/agent/tasks'))businessAfterLogout++;});
  expect((await request.get(API+'/auth/me', { headers: { Authorization: 'Bearer '+oldToken } })).status()).toBe(401);
  await page.goto('/'); await expect(page.getByRole('heading', { name: '已退出伴飞' })).toBeVisible();
  await page.reload(); await expect(page.getByRole('heading', { name: '已退出伴飞' })).toBeVisible();
  const restarted = await browser.newContext({ storageState: await context.storageState() });
  try {
    const tab = await restarted.newPage(); await tab.goto('/'); await expect(tab.getByRole('heading', { name: '已退出伴飞' })).toBeVisible();
    await tab.getByRole('button', { name: '继续使用当前身份' }).click();
    await expect(tab.locator('.sidebar')).toBeVisible(); expect((await localUser(tab)).id).toBe(original.user.id);
  }
  finally { await restarted.close(); }
  expect(await userCount(request, admin.access_token)).toBe(before); expect(businessAfterLogout).toBe(0);
  await page.getByRole('button',{name:'使用其他 Key 登录'}).click();
  await expect(page.getByLabel('身份 Key',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'返回当前浏览器身份'}).click();
  await page.getByRole('button', { name: '继续使用当前身份' }).click();
  await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(original.user.id);
  await page.goto('/account'); await expect(page.getByTestId('identity-key')).toHaveText(original.key);
});

test('administrator sees masked Key matched to user ID and ordinary logout remains independent', async ({ page, request }) => {
  const original = await createIdentity(page);
  await page.goto('/admin/login'); await page.getByLabel('用户名', { exact: true }).fill('admin1'); await page.getByLabel('密码', { exact: true }).fill('ValidationPass123');
  await page.getByRole('button', { name: '登录', exact: true }).click(); await expect(page).toHaveURL(/\/admin$/);
  const hint = original.key.slice(0, 5)+'…'+original.key.slice(-5);
  const listResponse = page.waitForResponse(r => r.url().startsWith(API+'/admin/users?') && r.request().method() === 'GET');
  await page.goto('/admin/users');
  const listData = await (await listResponse).json();
  expect(listData.items.find((user: { id: string }) => user.id === original.user.id).identity_key_hint).toBe(hint);
  expect(JSON.stringify(listData)).not.toContain(original.key);
  const row = page.getByRole('row').filter({ has: page.locator(`a[href="/admin/users/${original.user.id}"]`) });
  await expect(page.getByRole('columnheader', { name: 'Key 标识', exact: true })).toBeVisible();
  await expect(row.getByText(hint, { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('admin-key-hint-list.png'), fullPage: true });
  const detailResponse = page.waitForResponse(r => r.url() === API+'/admin/users/'+original.user.id && r.request().method() === 'GET');
  await row.getByRole('link').click();
  const detailData = await (await detailResponse).json();
  expect(detailData.id).toBe(original.user.id); expect(detailData.identity_key_hint).toBe(hint);
  expect(JSON.stringify(detailData)).not.toContain(original.key);
  await expect(page.getByText('身份 Key', { exact: true })).toBeVisible();
  await expect(page.getByText(original.user.id, { exact: true })).toBeVisible();
  await expect(page.getByText(hint, { exact: true })).toBeVisible();
  await expect(page.getByText(original.key, { exact: true })).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('admin-key-hint-detail.png'), fullPage: true });
  await page.getByRole('button', { name: '退出登录', exact: true }).click(); await expect(page).toHaveURL(/\/admin\/login$/);
  await page.goto('/'); await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(original.user.id);
  const admin = await adminSession(request); await page.evaluate(s => { localStorage.setItem('banfei:admin:token', s.access_token); localStorage.setItem('banfei:admin:user', JSON.stringify(s.user)); }, admin);
  await page.getByRole('button', { name: '退出', exact: true }).click(); await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate(() => localStorage.getItem('banfei:admin:token'))).toBe(admin.access_token);
  await page.goto('/admin'); await expect(page.locator('.admin-layout')).toBeVisible();
});

test('ordinary identities cannot read each other tasks, and expired token restores browser session', async ({ page, browser }) => {
  const a = await createIdentity(page);
  const task = execFileSync(resolve('../.venv/bin/python'), ['-m', 'backend.tests.support.seed_identity_history', a.user.id], { cwd: resolve('..'), encoding: 'utf8' }).trim();
  const second = await browser.newContext(); const b = await second.newPage();
  try {
    await createIdentity(b); const token = await b.evaluate(() => localStorage.getItem('banfei:user:token'));
    expect((await b.request.get(API+'/agent/tasks/'+task, { headers: { Authorization: 'Bearer '+token } })).status()).toBe(404);
    await page.evaluate(() => localStorage.setItem('banfei:user:token', 'expired')); await page.reload(); await expect(page.locator('.sidebar')).toBeVisible();
    expect((await localUser(page)).id).toBe(a.user.id);
  } finally { await second.close(); }
});

test('two first-open tabs create one identity; logout updates the other tab', async ({ context }) => {
  let creations = 0; context.on('request', r => { if (r.url().endsWith('/auth/identity/session') && r.postDataJSON()?.create) creations++; });
  const a = await context.newPage(), b = await context.newPage();
  await Promise.all([a.goto('/'), b.goto('/')]);
  await expect(a.locator('.sidebar')).toBeVisible(); await expect(b.locator('.sidebar')).toBeVisible();
  expect((await localUser(a)).id).toBe((await localUser(b)).id); expect(creations).toBe(1);
  if (await a.getByRole('button', { name: '稍后保存' }).count()) await a.getByRole('button', { name: '稍后保存' }).click();
  await a.getByRole('button', { name: '退出', exact: true }).click();
  await expect(a.getByRole('heading', { name: '已退出伴飞' })).toBeVisible();
  await expect(b.getByRole('heading', { name: '已退出伴飞' })).toBeVisible();
  expect(creations).toBe(1);
});

const chromePath = resolve('../.isolation/identity-browsers/chrome/opt/google/chrome/chrome');
const edgePath = resolve('../.isolation/identity-browsers/edge/opt/microsoft/msedge/msedge');
test('Chrome Key logs into the same identity in Edge without platform verification', async () => {
  test.skip(!existsSync(chromePath) || !existsSync(edgePath), 'Official browsers not installed');
  const chrome = await chromium.launch({ executablePath: chromePath }); const edge = await chromium.launch({ executablePath: edgePath });
  try {
    const a = await chrome.newPage({ baseURL: 'http://localhost:3000' }); const original = await createIdentity(a);
    const b = await edge.newPage({ baseURL: 'http://localhost:3000' }); await keyLogin(b, original.key);
    expect((await localUser(b)).id).toBe(original.user.id);
    await b.goto('/account'); await expect(b.getByTestId('identity-key')).toHaveText(original.key);
  } finally { await chrome.close(); await edge.close(); }
});

test('same browser auto-enters normal login route with either token or remembered Cookie', async ({ page, request }) => {
  const original=await createIdentity(page);
  const admin=await adminSession(request);const before=await userCount(request,admin.access_token);
  await page.goto('/login'); await expect(page.locator('.sidebar')).toBeVisible();
  expect((await localUser(page)).id).toBe(original.user.id);
  await page.evaluate(()=>localStorage.removeItem('banfei:user:token'));
  await page.goto('/login'); await expect(page.locator('.sidebar')).toBeVisible();
  expect((await localUser(page)).id).toBe(original.user.id);
  expect(await userCount(request,admin.access_token)).toBe(before);
});

test('lost remembered Cookie after logout offers Key without creating a replacement', async ({ page, context, request }) => {
  const original=await createIdentity(page); const admin=await adminSession(request); const before=await userCount(request,admin.access_token);
  await page.getByRole('button',{name:'退出',exact:true}).click();
  await expect(page.getByRole('button',{name:'继续使用当前身份'})).toBeVisible();
  await context.clearCookies();
  await page.getByRole('button',{name:'继续使用当前身份'}).click();
  await expect(page.getByLabel('身份 Key',{exact:true})).toBeVisible();
  expect(await userCount(request,admin.access_token)).toBe(before);
  await page.getByLabel('身份 Key',{exact:true}).fill(original.key);
  await page.getByRole('button',{name:'登录原身份',exact:true}).click();
  await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(original.user.id);
});

test('business 401 restores same browser identity without Key or a new user', async ({ page, request }) => {
  const original=await createIdentity(page);const admin=await adminSession(request);const before=await userCount(request,admin.access_token);
  let rejected=false;
  await page.route('**/agent/tasks?**',route=>{
    if(rejected)return route.continue();rejected=true;
    return route.fulfill({status:401,json:{detail:'expired test token'}});
  });
  await page.goto('/tasks');
  await expect(page).toHaveURL('http://localhost:3000/');
  await expect(page.locator('.sidebar')).toBeVisible();
  expect(rejected).toBe(true);expect((await localUser(page)).id).toBe(original.user.id);
  expect(await userCount(request,admin.access_token)).toBe(before);
});

test('credential file import restores downloaded identity and history without uploading the file', async ({ page, context, request }) => {
  const original = await createIdentity(page);
  const taskId = execFileSync(resolve('../.venv/bin/python'), ['-m', 'backend.tests.support.seed_identity_history', original.user.id], { cwd: resolve('..'), encoding: 'utf8' }).trim();
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  await page.evaluate(session => {
    localStorage.setItem('banfei:admin:token', session.access_token);
    localStorage.setItem('banfei:admin:user', JSON.stringify(session.user));
  }, admin);
  await page.goto('/account');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载凭据 .txt' }).click();
  const download = await downloadEvent;
  const file = { name: download.suggestedFilename(), mimeType: 'text/plain', buffer: readFileSync((await download.path())!) };
  await context.clearCookies();
  await page.evaluate(() => { localStorage.removeItem('banfei:user:token'); localStorage.removeItem('banfei:user:user'); });
  await page.goto('/login');
  await expect(page.getByRole('button', { name: '导入凭据 .txt 登录' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('identity-import-login.png'), fullPage: true });
  const chooserEvent = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: '导入凭据 .txt 登录' }).click();
  const loginRequest = page.waitForRequest(r => r.url().endsWith('/auth/identity/key/login'));
  await (await chooserEvent).setFiles(file);
  expect((await loginRequest).postDataJSON()).toEqual({ key: original.key });
  await expect(page.locator('.sidebar')).toBeVisible();
  expect((await localUser(page)).id).toBe(original.user.id);
  await page.goto('/tasks'); await expect(page.getByRole('cell', { name: '退出身份保留的个人任务', exact: true })).toBeVisible();
  await page.reload(); await expect(page.locator('.sidebar')).toBeVisible();
  expect((await localUser(page)).id).toBe(original.user.id);
  expect(await userCount(request, admin.access_token)).toBe(before);
  expect(await page.evaluate(() => localStorage.getItem('banfei:admin:token'))).toBe(admin.access_token);
  const token = await page.evaluate(() => localStorage.getItem('banfei:user:token'));
  expect((await page.request.get(API+'/agent/tasks/'+taskId, { headers: { Authorization: 'Bearer '+token } })).ok()).toBeTruthy();
  await page.goto('/account'); await expect(page.getByTestId('identity-key')).toHaveText(original.key);
});

test('credential file import accepts plain Key with BOM and Windows line endings after logout', async ({ page }) => {
  const original = await createIdentity(page);
  await page.getByRole('button', { name: '退出', exact: true }).click();
  await page.getByRole('button', { name: '使用其他 Key 登录' }).click();
  const chooserEvent = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: '导入凭据 .txt 登录' }).click();
  await (await chooserEvent).setFiles({ name: 'identity.TXT', mimeType: 'text/plain', buffer: Buffer.from('\uFEFF \r\n '+original.key+' \r\n') });
  await expect(page.locator('.sidebar')).toBeVisible();
  expect((await localUser(page)).id).toBe(original.user.id);
});

test('credential file import rejects invalid files locally and cancellation preserves the remembered identity', async ({ page, context, request }) => {
  const original = await createIdentity(page);
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  await page.getByRole('button', { name: '退出', exact: true }).click();
  await page.getByRole('button', { name: '使用其他 Key 登录' }).click();
  const cookie = (await context.cookies()).find(c => c.name === 'banfei_identity_session')!.value;
  let authRequests = 0, businessRequests = 0;
  page.on('request', r => { if (r.url().includes('/auth/identity/')) authRequests++; if (r.url().includes('/agent/tasks')) businessRequests++; });
  const chooserEvent = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: '导入凭据 .txt 登录' }).click();
  await (await chooserEvent).setFiles([]);
  await expect(page.locator('form [role=alert]')).toHaveCount(0);
  await page.getByLabel('身份 Key', { exact: true }).fill('manual-value');
  const invalidFiles = [
    { name: 'empty.txt', content: '', error: '未找到有效的身份 Key' },
    { name: 'unrelated.txt', content: '没有凭据的普通文本', error: '未找到有效的身份 Key' },
    { name: 'truncated.txt', content: original.key.slice(0, -1), error: '未找到有效的身份 Key' },
    { name: 'long-key.txt', content: original.key+'a', error: '未找到有效的身份 Key' },
    { name: 'two.txt', content: original.key+'\n'+original.key, error: '文件包含多个 Key' },
    { name: 'large.txt', content: original.key+'\n'+' '.repeat(16 * 1024), error: '文件过大' },
    { name: 'wrong.pdf', content: original.key, error: '请选择下载的 .txt' },
    { name: 'binary.txt', content: original.key+'\n\0', error: '未找到有效的身份 Key' },
    { name: 'sql.txt', content: "bf_' OR 1=1--", error: '未找到有效的身份 Key' },
    { name: 'script.txt', content: 'bf_<script>alert(1)</script>', error: '未找到有效的身份 Key' },
    { name: 'command.txt', content: 'bf_$(id)', error: '未找到有效的身份 Key' },
    { name: 'path.txt', content: 'bf_../../etc/passwd', error: '未找到有效的身份 Key' },
  ];
  for (const file of invalidFiles) {
    await page.getByLabel('选择身份凭据文件').setInputFiles({ name: file.name, mimeType: 'text/plain', buffer: Buffer.from(file.content) });
    await expect(page.locator('form [role=alert]')).toContainText(file.error);
    await expect(page.getByRole('button', { name: '导入凭据 .txt 登录' })).toBeEnabled();
    await expect(page.getByLabel('身份 Key', { exact: true })).toHaveValue('manual-value');
  }
  expect(authRequests).toBe(0); expect(businessRequests).toBe(0);
  expect(await userCount(request, admin.access_token)).toBe(before);
  expect((await context.cookies()).find(c => c.name === 'banfei_identity_session')!.value).toBe(cookie);
  await page.getByRole('button', { name: '返回当前浏览器身份' }).click();
  await page.getByRole('button', { name: '继续使用当前身份' }).click();
  await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(original.user.id);
});

test('credential file import with an unknown Key creates no user and can retry the same filename', async ({ page, context, request }) => {
  const original = await createIdentity(page);
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  await page.getByRole('button', { name: '退出', exact: true }).click();
  await page.getByRole('button', { name: '使用其他 Key 登录' }).click();
  const cookie = (await context.cookies()).find(c => c.name === 'banfei_identity_session')!.value;
  const fileInput = page.getByLabel('选择身份凭据文件');
  await fileInput.setInputFiles({ name: 'identity.txt', mimeType: 'text/plain', buffer: Buffer.from('bf_'+'x'.repeat(43)) });
  await expect(page.locator('form [role=alert]')).toHaveText('凭据无效或已失效，请确认 Key 或凭据文件。');
  expect(await localUser(page)).toBeNull(); expect(await userCount(request, admin.access_token)).toBe(before);
  expect((await context.cookies()).find(c => c.name === 'banfei_identity_session')!.value).toBe(cookie);
  await fileInput.setInputFiles({ name: 'identity.txt', mimeType: 'text/plain', buffer: Buffer.from(original.key) });
  await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(original.user.id);
  expect(await userCount(request, admin.access_token)).toBe(before);
});

async function deleteIdentity(request: APIRequestContext, adminToken: string, userId: string) {
  const headers = { Authorization: 'Bearer '+adminToken };
  const preview = await request.get(API+'/admin/users/'+userId+'/deletion-preview', { headers });
  const data = await preview.json(); expect(data.allowed).toBe(true);
  expect((await request.delete(API+'/admin/users/'+userId, { headers, data: { confirmationToken: data.confirmationToken } })).status()).toBe(204);
}

for (const method of ['paste', 'file']) test(`deleted Key ${method} shows explicit new identity action without automatic creation`, async ({ page, request }) => {
  const original = await createIdentity(page); const admin = await adminSession(request);
  await page.evaluate(s => { localStorage.setItem('banfei:admin:token', s.access_token); localStorage.setItem('banfei:admin:user', JSON.stringify(s.user)); }, admin);
  await page.getByRole('button', { name: '退出', exact: true }).click();
  await expect(page.getByRole('button', { name: '继续使用当前身份' })).toBeVisible();
  await deleteIdentity(request, admin.access_token, original.user.id);
  const before = await userCount(request, admin.access_token);
  let creations = 0;
  page.on('request', r => { if (r.url().endsWith('/auth/identity/session') && r.postDataJSON()?.create) creations++; });
  await page.getByRole('button', { name: '使用其他 Key 登录' }).click();
  if (method === 'paste') {
    await page.getByLabel('身份 Key', { exact: true }).fill(original.key);
    await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  } else {
    await page.getByLabel('选择身份凭据文件').setInputFiles({ name: 'deleted.txt', mimeType: 'text/plain', buffer: Buffer.from(original.key) });
  }
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toBeVisible();
  await expect(page.getByText('该身份已被管理员删除，原凭据已失效。请重新建立身份。', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '创建新身份', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '返回当前浏览器身份' })).toHaveCount(0);
  expect(creations).toBe(0); expect(await userCount(request, admin.access_token)).toBe(before);
  expect(await localUser(page)).toBeNull();
  if (method === 'file') {
    await page.screenshot({ path: test.info().outputPath('deleted-key-entry.png') });
    // A transient creation error must keep a retryable creation action.
    await page.route('**/auth/identity/session', route => route.fulfill({ status: 503, json: { detail: '暂时无法创建，请重试' } }), { times: 1 });
    await page.getByRole('button', { name: '创建新身份', exact: true }).click();
    await expect(page.getByText('暂时无法创建，请重试', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '原身份已删除' })).toBeVisible();
    expect(await userCount(request, admin.access_token)).toBe(before);
  }
  await page.getByRole('button', { name: '创建新身份', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '保存你的身份 Key' })).toBeVisible();
  expect((await localUser(page)).id).not.toBe(original.user.id);
  await expect(page.getByTestId('identity-key')).not.toHaveText(original.key);
  expect(await userCount(request, admin.access_token)).toBe(before+1);
  expect(await page.evaluate(() => localStorage.getItem('banfei:admin:token'))).toBe(admin.access_token);
  expect((await request.get(API+'/auth/me', { headers: { Authorization: 'Bearer '+admin.access_token } })).ok()).toBe(true);
});

test('deleted Key cannot clear a different remembered identity; explicit creation produces a new user', async ({ page, request, browser }) => {
  const current = await createIdentity(page); const admin = await adminSession(request);
  const otherContext = await browser.newContext(); let deleted: Awaited<ReturnType<typeof createIdentity>>;
  try {
    const other = await otherContext.newPage(); deleted = await createIdentity(other);
    await other.getByRole('button', { name: '退出', exact: true }).click();
    await expect(other.getByRole('heading', { name: '已退出伴飞' })).toBeVisible();
    await deleteIdentity(request, admin.access_token, deleted.user.id);
  } finally { await otherContext.close(); }
  await page.getByRole('button', { name: '退出', exact: true }).click();
  await page.getByRole('button', { name: '使用其他 Key 登录' }).click();
  await page.getByLabel('身份 Key', { exact: true }).fill(deleted.key);
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toBeVisible();
  await page.getByRole('button', { name: '返回当前浏览器身份' }).click();
  await page.getByRole('button', { name: '继续使用当前身份' }).click();
  await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(current.user.id);
  await page.goto('/login?method=key'); await page.getByLabel('身份 Key', { exact: true }).fill(deleted.key);
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toBeVisible();
  const before = await userCount(request, admin.access_token);
  await page.getByRole('button', { name: '创建新身份', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '保存你的身份 Key' })).toBeVisible();
  expect((await localUser(page)).id).not.toBe(current.user.id);
  expect((await localUser(page)).id).not.toBe(deleted.user.id);
  expect(await userCount(request, admin.access_token)).toBe(before+1);
  const restored = await request.post(API+'/auth/identity/key/login', { headers: origin, data: { key: current.key } });
  expect((await restored.json()).user.id).toBe(current.user.id);
});

test('disabled Key is distinguished from deletion and provides no new identity shortcut', async ({ page, request }) => {
  const original = await createIdentity(page); const admin = await adminSession(request);
  await page.getByRole('button', { name: '退出', exact: true }).click();
  await expect(page.getByRole('heading', { name: '已退出伴飞' })).toBeVisible();
  expect((await request.patch(API+'/admin/users/'+original.user.id+'/status', { headers: { Authorization: 'Bearer '+admin.access_token }, data: { status: 'disabled' } })).ok()).toBe(true);
  await page.getByRole('button', { name: '使用其他 Key 登录' }).click();
  await page.getByLabel('选择身份凭据文件').setInputFiles({ name: 'disabled.txt', mimeType: 'text/plain', buffer: Buffer.from(original.key) });
  await expect(page.locator('form [role=alert]')).toHaveText('该身份已停用，需要管理员重新启用后才能继续使用。');
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '创建新身份', exact: true })).toHaveCount(0);
  expect((await request.patch(API+'/admin/users/'+original.user.id+'/status', { headers: { Authorization: 'Bearer '+admin.access_token }, data: { status: 'active' } })).ok()).toBe(true);
  await page.getByLabel('选择身份凭据文件').setInputFiles({ name: 'disabled.txt', mimeType: 'text/plain', buffer: Buffer.from(original.key) });
  await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(original.user.id);
});

test('unknown Key with a stale remembered marker offers explicit creation without claiming deletion', async ({ page, request }) => {
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  await page.goto('/login?method=key');
  await page.evaluate(() => localStorage.setItem('banfei:user:signed-out', 'remembered'));
  await page.reload();
  await page.getByLabel('身份 Key', { exact: true }).fill('bf_'+'z'.repeat(43));
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.locator('form [role=alert]')).toHaveText('凭据无效或已失效，请确认 Key 或凭据文件。');
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '返回当前浏览器身份' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '创建新身份', exact: true })).toBeVisible();
  expect(await localUser(page)).toBeNull(); expect(await userCount(request, admin.access_token)).toBe(before);
  await page.getByRole('button', { name: '创建新身份', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '保存你的身份 Key' })).toBeVisible();
  expect(await userCount(request, admin.access_token)).toBe(before+1);
});

for (const location of ['list', 'detail']) test(`account soft deletion from ${location} keeps history and uses one-sentence confirmation`, async ({ page, request }) => {
  const original = await createIdentity(page);
  const taskId = execFileSync(resolve('../.venv/bin/python'), ['-m', 'backend.tests.support.seed_identity_history', original.user.id], { cwd: resolve('..'), encoding: 'utf8' }).trim();
  const admin = await adminSession(request);
  await page.evaluate(s => { localStorage.setItem('banfei:admin:token', s.access_token); localStorage.setItem('banfei:admin:user', JSON.stringify(s.user)); }, admin);
  await page.goto(location === 'list' ? '/admin/users' : '/admin/users/'+original.user.id);
  const target = location === 'list' ? page.getByRole('row').filter({ has: page.locator(`a[href="/admin/users/${original.user.id}"]`) }) : page.locator('main');
  await target.getByRole('button', { name: '删除', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '删除账号' });
  await expect(dialog.locator('p')).toHaveCount(1);
  await expect(dialog.locator('p')).toHaveText('删除后，该账号及身份 Key 将无法使用，历史业务数据仍保留。确定删除？');
  await expect(dialog.getByRole('button')).toHaveCount(2);
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  const headers = { Authorization: 'Bearer '+admin.access_token };
  expect((await request.get(API+'/admin/users/'+original.user.id, { headers })).ok()).toBeTruthy();
  await target.getByRole('button', { name: '删除', exact: true }).click();
  await dialog.getByRole('button', { name: '删除账号', exact: true }).click();
  await expect(dialog).toHaveCount(0); await expect(page).toHaveURL(/\/admin\/users$/);
  await expect(page.locator(`a[href="/admin/users/${original.user.id}"]`)).toHaveCount(0);
  const history = await request.get(API+'/agent/tasks/'+taskId, { headers });
  expect(history.ok()).toBeTruthy(); expect((await history.json()).createdBy).toBe('已删除用户');
  await page.goto('/admin/tasks/'+taskId);
  await expect(page.getByText('已删除用户', { exact: false })).toBeVisible();
  await page.goto('/login?method=key'); await page.getByLabel('身份 Key', { exact: true }).fill(original.key);
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toBeVisible();
  expect((await request.get(API+'/auth/me', { headers })).ok()).toBeTruthy();
});

test('account soft deletion is available for admins and protects the current operator', async ({ page, request }) => {
  const admin = await adminSession(request); const headers = { Authorization:'Bearer '+admin.access_token };
  const created = await request.post(API+'/admin/users', { headers, data:{ username:'delete_admin_'+Date.now(), display_name:'待删除管理员', role:'admin' } });
  expect(created.ok()).toBeTruthy(); const target = (await created.json()).user;
  await page.goto('/admin/login');
  await page.evaluate(s => { localStorage.setItem('banfei:admin:token', s.access_token); localStorage.setItem('banfei:admin:user', JSON.stringify(s.user)); }, admin);
  await page.goto('/admin/users/'+admin.user.id); await page.getByRole('button', { name:'删除', exact:true }).click();
  await expect(page.locator('main').getByRole('alert')).toHaveText('不能删除当前操作账号。'); await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.goto('/admin/users/'+target.id); await page.getByRole('button', { name:'删除', exact:true }).click();
  await page.getByRole('dialog').getByRole('button', { name:'删除账号', exact:true }).click();
  await expect(page).toHaveURL(/\/admin\/users$/);
  expect((await request.get(API+'/admin/users/'+target.id,{ headers })).status()).toBe(404);
  expect((await request.get(API+'/auth/me',{ headers })).status()).toBe(200);
});
