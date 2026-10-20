import { test, expect, chromium, type Page, type APIRequestContext } from '@playwright/test';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import {API,origin,localUser,loginLink,readLoginLink,createIdentity,keyLogin,emptyEntry,legacyLogout,adminSession,userCount} from './local-identity-support';

test('first visit enters automatically, same login link in popup/account, copy download and reload', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  let creations = 0;
  page.on('request', r => { if (r.url().endsWith('/auth/identity/session') && r.postDataJSON()?.create) creations++; });
  await page.goto('/');
  const dialog = page.getByRole('dialog', { name: '欢迎使用伴飞' }); await expect(dialog).toBeVisible();
  const { link } = await readLoginLink(page); const user = await localUser(page);
  await expect(dialog.getByRole('button')).toHaveCount(2);
  await expect(dialog.getByRole('checkbox')).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: '下载凭据 .txt' })).toHaveCount(0);
  await page.getByRole('button', { name: '复制登录链接', exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(link);
  await expect(dialog.getByRole('status')).toHaveText('登录链接已复制');
  await page.screenshot({ path: test.info().outputPath('login-link-popup.png') });
  await page.getByRole('button', { name: '开始使用伴飞' }).click(); await expect(dialog).toHaveCount(0);
  await page.goto('/account'); await expect(page.getByRole('heading', { name: '身份凭据' })).toBeVisible();
  await expect(page.getByTestId('identity-key')).toHaveText(link);
  await page.getByRole('button', { name: '复制登录链接', exact: true }).click(); expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(link);
  await page.reload(); await expect(page.getByTestId('identity-key')).toHaveText(link);
  expect((await localUser(page)).id).toBe(user.id); expect(creations).toBe(1);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('login-link-account.png'), fullPage: true });
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
  await page.goto('/account'); await expect(page.getByTestId('identity-key')).toHaveText(loginLink(page, original.key));
  expect((await page.request.get(API+'/agent/tasks/'+taskId, { headers: { Authorization: 'Bearer '+await page.evaluate(() => localStorage.getItem('banfei:user:token')) } })).ok()).toBeTruthy();
});

test('explicit Key entry and invalid input never create users or request business history', async ({ page, request }) => {
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  let business = 0, creations = 0;
  await page.addInitScript(() => sessionStorage.setItem('lingjian:pending-tasks:residual', JSON.stringify([{ id: 'missing-task' }])));
  page.on('request', r => { if (r.url().includes('/agent/tasks')) business++; if (r.url().endsWith('/session') && r.postDataJSON()?.create) creations++; });
  await page.goto('/login'); await page.getByLabel('登录链接', { exact: true }).fill('incorrect-key');
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.locator('form [role=alert]')).toHaveText('请输入有效的登录链接。');
  expect(await localUser(page)).toBeNull(); expect(await userCount(request, admin.access_token)).toBe(before);
  expect(business).toBe(0); expect(creations).toBe(0);
});

test('saved login link switches identity without another user or merge', async ({ page, browser, request }) => {
  const original = await createIdentity(page);
  const otherContext = await browser.newContext(); const other = await otherContext.newPage();
  try {
    await other.goto('/'); await expect(other.getByRole('dialog')).toBeVisible(); const temporary = await localUser(other);
    const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
    await other.goto(original.link);
    const change=other.getByRole('dialog',{name:'切换身份',exact:true});await expect(change).toBeVisible();await change.getByRole('button',{name:'切换',exact:true}).click();await expect(change).toHaveCount(0);
    await expect(other.locator('.sidebar')).toBeVisible(); expect((await localUser(other)).id).toBe(original.user.id);
    expect(temporary.id).not.toBe(original.user.id); expect(await userCount(request, admin.access_token)).toBe(before);
  } finally { await otherContext.close(); }
});

test('legacy logout rotates the session and automatically resumes the same identity after restart', async ({page,context,browser,request})=>{
 const original=await createIdentity(page),oldToken=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));
 const admin=await adminSession(request),before=await userCount(request,admin.access_token);
 const oldCookie=(await context.cookies()).find(c=>c.name==='banfei_http_identity_session')!.value;
 await legacyLogout(page);expect((await context.cookies()).find(c=>c.name==='banfei_http_identity_session')!.value).not.toBe(oldCookie);
 expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+oldToken}})).status()).toBe(401);
 await page.goto('/');await expect(page.locator('.sidebar')).toBeVisible();expect((await localUser(page)).id).toBe(original.user.id);
 await expect(page.getByRole('heading',{name:'已退出伴飞'})).toHaveCount(0);
 const restarted=await browser.newContext({storageState:await context.storageState(),baseURL:origin.Origin});
 try{const tab=await restarted.newPage();await tab.goto('/');await expect(tab.locator('.sidebar')).toBeVisible();expect((await localUser(tab)).id).toBe(original.user.id);}finally{await restarted.close();}
 expect(await userCount(request,admin.access_token)).toBe(before);await page.goto('/account');await expect(page.getByTestId('identity-key')).toHaveText(original.link);
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
  await page.getByRole('button',{name:'切换身份',exact:true}).click();await page.getByRole('dialog',{name:'切换身份',exact:true}).getByRole('button',{name:'取消',exact:true}).click();
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

test('two first-open tabs create one identity; confirmed switching updates the other tab',async({context,browser})=>{
 let creations=0;context.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creations++;});
 const a=await context.newPage(),b=await context.newPage();await Promise.all([a.goto('/'),b.goto('/')]);await expect(a.locator('.sidebar')).toBeVisible();await expect(b.locator('.sidebar')).toBeVisible();
 expect((await localUser(a)).id).toBe((await localUser(b)).id);expect(creations).toBe(1);
 await a.getByRole('button',{name:'开始使用伴飞',exact:true}).click();
 const other=await browser.newContext({baseURL:origin.Origin});
 try{const target=await createIdentity(await other.newPage());await a.goto(target.link);const change=a.getByRole('dialog',{name:'切换身份',exact:true});await change.getByRole('button',{name:'切换',exact:true}).click();
 const settledUser=async(p:Page)=>{try{return await localUser(p)}catch{return null}};await expect.poll(async()=>(await settledUser(a))?.id).toBe(target.user.id);await expect.poll(async()=>(await settledUser(b))?.id).toBe(target.user.id);expect(creations).toBe(1);
 }finally{await other.close();}
});

const chromePath = resolve('../.isolation/identity-browsers/chrome/opt/google/chrome/chrome');
const edgePath = resolve('../.isolation/identity-browsers/edge/opt/microsoft/msedge/msedge');
test('Chrome Key logs into the same identity in Edge without platform verification', async () => {
  test.skip(!existsSync(chromePath) || !existsSync(edgePath), 'Official browsers not installed');
  const chrome = await chromium.launch({ executablePath: chromePath }); const edge = await chromium.launch({ executablePath: edgePath });
  try {
    const a = await chrome.newPage({ baseURL: 'http://localhost' }); const original = await createIdentity(a);
    const b = await edge.newPage({ baseURL: 'http://localhost' }); await keyLogin(b, original.key);
    expect((await localUser(b)).id).toBe(original.user.id);
    await b.goto('/account'); await expect(b.getByTestId('identity-key')).toHaveText(loginLink(b, original.key));
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

test('missing remembered Cookie on the login route offers Key without creating a replacement',async({page,request})=>{
 const original=await createIdentity(page),admin=await adminSession(request),before=await userCount(request,admin.access_token);
 await legacyLogout(page);await emptyEntry(page);await expect(page.getByLabel('登录链接',{exact:true})).toBeVisible();expect(await userCount(request,admin.access_token)).toBe(before);
 await keyLogin(page,original.key);expect((await localUser(page)).id).toBe(original.user.id);
});

test('business 401 restores same browser identity without Key or a new user', async ({ page, request }) => {
  const original=await createIdentity(page);const admin=await adminSession(request);const before=await userCount(request,admin.access_token);
  let rejected=false;
  await page.route('**/agent/tasks?**',route=>{
    if(rejected)return route.continue();rejected=true;
    return route.fulfill({status:401,json:{detail:'expired test token'}});
  });
  await page.goto('/tasks');
  await expect(page).toHaveURL(origin.Origin+'/');
  await expect(page.locator('.sidebar')).toBeVisible();
  expect(rejected).toBe(true);expect((await localUser(page)).id).toBe(original.user.id);
  expect(await userCount(request,admin.access_token)).toBe(before);
});

test('deleted target cannot clear the current identity; explicit new identity remains a separate action',async({page,request,browser})=>{
 const current=await createIdentity(page),admin=await adminSession(request),other=await browser.newContext({baseURL:origin.Origin});
 let deleted:Awaited<ReturnType<typeof createIdentity>>;
 try{deleted=await createIdentity(await other.newPage());await deleteIdentity(request,admin.access_token,deleted.user.id);}finally{await other.close();}
 const before=await userCount(request,admin.access_token);await page.goto(deleted.link);
 const change=page.getByRole('dialog',{name:'切换身份',exact:true});await change.getByRole('button',{name:'切换',exact:true}).click();await expect(change.locator('[role=alert]')).toContainText('该身份已被管理员删除');
 await change.getByRole('button',{name:'取消',exact:true}).click();expect((await localUser(page)).id).toBe(current.user.id);
 await emptyEntry(page);await page.getByLabel('登录链接',{exact:true}).fill(deleted.key);await page.getByRole('button',{name:'登录原身份',exact:true}).click();await expect(page.getByRole('heading',{name:'原身份已删除'})).toBeVisible();
 await page.getByRole('button',{name:'创建新身份',exact:true}).click();await expect(page.getByRole('dialog',{name:'欢迎使用伴飞'})).toBeVisible();
 expect((await localUser(page)).id).not.toBe(current.user.id);expect((await localUser(page)).id).not.toBe(deleted.user.id);expect(await userCount(request,admin.access_token)).toBe(before+1);
 const restored=await request.post(API+'/auth/identity/key/login',{headers:origin,data:{key:current.key}});expect((await restored.json()).user.id).toBe(current.user.id);
});

test('disabled Key is distinguished from deletion and provides no new identity shortcut', async ({ page, request }) => {
  const original = await createIdentity(page); const admin = await adminSession(request);
  await emptyEntry(page);
  expect((await request.patch(API+'/admin/users/'+original.user.id+'/status', { headers: { Authorization: 'Bearer '+admin.access_token }, data: { status: 'disabled' } })).ok()).toBe(true);
  await page.goto('/login?method=key');
  await page.getByLabel('登录链接').fill(original.key);
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.locator('form [role=alert]')).toHaveText('该身份已停用，需要管理员重新启用后才能继续使用。');
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '创建新身份', exact: true })).toHaveCount(0);
  expect((await request.patch(API+'/admin/users/'+original.user.id+'/status', { headers: { Authorization: 'Bearer '+admin.access_token }, data: { status: 'active' } })).ok()).toBe(true);
  await page.getByLabel('登录链接').fill(original.key);
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.locator('.sidebar')).toBeVisible(); expect((await localUser(page)).id).toBe(original.user.id);
});

test('unknown Key with a stale remembered marker offers explicit creation without claiming deletion', async ({ page, request }) => {
  const admin = await adminSession(request); const before = await userCount(request, admin.access_token);
  await page.goto('/login?method=key');
  await page.evaluate(() => localStorage.setItem('banfei:user:signed-out', 'remembered'));
  await page.reload();
  await page.getByLabel('登录链接', { exact: true }).fill('bf_'+'z'.repeat(43));
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.locator('form [role=alert]')).toHaveText('凭据无效或已失效，请确认 Key 或凭据文件。');
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '返回当前浏览器身份' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '创建新身份', exact: true })).toBeVisible();
  expect(await localUser(page)).toBeNull(); expect(await userCount(request, admin.access_token)).toBe(before);
  await page.getByRole('button', { name: '创建新身份', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '欢迎使用伴飞' })).toBeVisible();
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
  await page.goto('/login?method=key');
  await expect(page.getByRole('heading', { name: '原身份已删除' }).or(page.getByLabel('登录链接', { exact: true }))).toBeVisible();
  if (await page.getByRole('heading', { name: '原身份已删除' }).isVisible()) await page.getByRole('button', { name: '使用其他登录链接' }).click();
  await page.getByLabel('登录链接', { exact: true }).fill(original.key);
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


for(const width of [1366,1920,390])test('login link v3: dismiss without copying at '+width,async({page})=>{
 await page.setViewportSize({width,height:width===390?844:900});await page.goto('/');const dialog=page.getByRole('dialog',{name:'欢迎使用伴飞'});await expect(dialog).toBeVisible();await readLoginLink(page);
 await expect(dialog.getByTestId('identity-key')).toBeVisible();await expect(dialog.getByRole('button',{name:'复制登录链接'})).toBeVisible();expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
 if(width===390)await dialog.getByRole('button',{name:'开始使用伴飞'}).click();else await page.keyboard.press('Escape');
 await expect(dialog).toHaveCount(0);await page.reload();await expect(page.locator('.sidebar')).toBeVisible();await expect(dialog).toHaveCount(0);
});
test('login link v3: new browser restores A history without creating an extra identity',async({page,browser,request})=>{
 const a=await createIdentity(page),task=execFileSync(resolve('../.venv/bin/python'),['-m','backend.tests.support.seed_identity_history',a.user.id],{cwd:resolve('..'),encoding:'utf8'}).trim();
 const admin=await adminSession(request),before=await userCount(request,admin.access_token),context=await browser.newContext({baseURL:origin.Origin});
 try{const other=await context.newPage();let creates=0;other.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;});await other.goto(a.link);await expect(other.locator('.sidebar')).toBeVisible();
 expect((await localUser(other)).id).toBe(a.user.id);await other.goto('/tasks/'+task);await expect(other.locator('main').getByText('退出身份保留的个人任务',{exact:true})).toBeVisible();expect(creates).toBe(0);expect(await userCount(request,admin.access_token)).toBe(before);
 }finally{await context.close();}
});
for(const navigation of ['reload','hashchange'])test('login link v3: B confirms A before adoption '+navigation,async({page,browser})=>{
 const a=await createIdentity(page),context=await browser.newContext({baseURL:origin.Origin});try{
 const other=await context.newPage(),b=await createIdentity(other);if(navigation==='reload')await other.goto(a.link);else await other.evaluate(link=>{location.hash=new URL(link).hash;},a.link);
 const change=other.getByRole('dialog',{name:'切换身份',exact:true});await expect(change).toBeVisible();expect((await localUser(other)).id).toBe(b.user.id);
 await change.getByRole('button',{name:'切换',exact:true}).click();await expect(change).toHaveCount(0);await expect.poll(async()=>(await localUser(other)).id).toBe(a.user.id);expect(new URL(other.url()).hash).toBe('');
 }finally{await context.close();}
});
for(const failure of ['invalid','network'])test('login link v3: failed target preserves B '+failure,async({page,context,request})=>{
 const b=await createIdentity(page),cookie=(await context.cookies()).find(c=>c.name==='banfei_http_identity_session')!.value;
 if(failure==='network')await page.route('**/auth/identity/key/login',route=>route.abort());
 await page.goto(loginLink(page,'bf_'+'z'.repeat(43)));const change=page.getByRole('dialog',{name:'切换身份',exact:true});await expect(change).toBeVisible();const token=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));await change.getByRole('button',{name:'切换',exact:true}).click();
 await expect(change.locator('[role=alert]')).toContainText(failure==='network'?'切换失败，你仍是原来的身份，请重试。':'凭据无效或已失效');expect((await localUser(page)).id).toBe(b.user.id);expect(await page.evaluate(()=>localStorage.getItem('banfei:user:token'))).toBe(token);
 expect((await context.cookies()).find(c=>c.name==='banfei_http_identity_session')!.value).toBe(cookie);expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+token}})).ok()).toBe(true);
 await change.getByRole('button',{name:'取消',exact:true}).click();
});
test('login link v3: invalid link on an empty browser creates no identity',async({page,request})=>{
 const admin=await adminSession(request),before=await userCount(request,admin.access_token);let creates=0;page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;});
 await page.goto('/#k=invalid');await expect(page.locator('.error-text[role=alert]')).toContainText('身份 Key 格式不正确');expect(creates).toBe(0);expect(await localUser(page)).toBeNull();expect(await userCount(request,admin.access_token)).toBe(before);
});
test('login link v3: link restores legacy exited identity without touching admin credentials',async({page,request})=>{
 const a=await createIdentity(page),admin=await adminSession(request);await page.evaluate(admin=>{localStorage.setItem('banfei:admin:token',admin.access_token);localStorage.setItem('banfei:admin:user',JSON.stringify(admin.user));},admin);
 await legacyLogout(page);await page.goto(a.link);await expect(page.locator('.sidebar')).toBeVisible();expect((await localUser(page)).id).toBe(a.user.id);expect(await page.evaluate(()=>localStorage.getItem('banfei:admin:token'))).toBe(admin.access_token);
 await page.goto('/admin#k=invalid');await expect(page.locator('.admin-layout')).toBeVisible();
});
test('login link v3: lost committed response adopts the verified Cookie identity and reports it',async({page,browser,request})=>{
  const b=await createIdentity(page),context=await browser.newContext({baseURL:origin.Origin});
  let token=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));
  let releaseOld401!:()=>void;const old401Ready=new Promise<void>(resolve=>{releaseOld401=resolve;});let held=0,creates=0;
  const probes:Array<{authorization:string|undefined;create:unknown}>=[];
  try{
    const a=await createIdentity(await context.newPage());
    page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')){if(r.postDataJSON()?.create)creates++;else probes.push({authorization:r.headers().authorization,create:r.postDataJSON()?.create});}});
    // This old business request returns 401 after adoption, exercising the
    // same race without letting its default redirect erase the switch notice.
    await page.route('**/api/agent/tasks?*',async route=>{
      if(route.request().headers().authorization!=='Bearer '+token)return route.continue();
      held++;await old401Ready;await route.fulfill({status:401,json:{detail:'synthetic revoked previous session'}});
    });
    await page.route('**/auth/identity/key/login',async route=>{expect((await route.fetch()).ok()).toBe(true);await route.abort();});
    await page.goto(a.link);const change=page.getByRole('dialog',{name:'切换身份',exact:true});await expect(change).toBeVisible();token=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));await expect.poll(()=>held).toBeGreaterThan(0);
    await change.getByRole('button',{name:'切换',exact:true}).click();await expect(change).toHaveCount(0);
    const notice=page.locator('.identity-notice[role=status]');await expect(notice).toHaveText('切换已生效，当前身份：'+(a.user.employee_number||a.user.username));
    const late401=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/agent/tasks'&&r.status()===401);releaseOld401();await(await late401).finished();
    await expect(notice).toBeVisible();await expect(page.locator('.sidebar')).toBeVisible();expect(new URL(page.url()).pathname).toBe('/');
    expect((await localUser(page)).id).toBe(a.user.id);const currentToken=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));
    expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+currentToken}})).status()).toBe(200);
    expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+token}})).status()).toBe(401);
    expect(await page.evaluate(()=>localStorage.getItem('banfei:user:device-secret')!==null)).toBe(true);
    expect(creates).toBe(0);expect(probes).toContainEqual({authorization:undefined,create:false});
  }finally{releaseOld401();await context.close();}
});

test('login link v3: unrecoverable switch response enters login with an explicit expired notice',async({page,context,browser,request})=>{
  const b=await createIdentity(page),token=await page.evaluate(()=>localStorage.getItem('banfei:user:token')),other=await browser.newContext({baseURL:origin.Origin});let creates=0;
  try{
    const a=await createIdentity(await other.newPage());page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;});
    await page.route('**/auth/identity/key/login',async route=>{expect((await route.fetch()).ok()).toBe(true);await context.clearCookies();await route.abort();});
    await page.goto(a.link);await page.getByRole('dialog',{name:'切换身份',exact:true}).getByRole('button',{name:'切换',exact:true}).click();
    await expect(page).toHaveURL(/\/login$/);await expect(page.locator('.identity-entry-card .error-text[role=alert]')).toHaveText('登录已失效，请重新进入');
    await expect(page.getByLabel('登录链接',{exact:true})).toBeVisible();await expect(page.locator('.sidebar')).toHaveCount(0);
    expect(await localUser(page)).toBeNull();expect(await page.evaluate(()=>localStorage.getItem('banfei:user:token'))).toBeNull();expect(creates).toBe(0);
    expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+token}})).status()).toBe(401);
  }finally{await other.close();}
});

async function deleteIdentity(request: APIRequestContext, adminToken: string, userId: string) {
  const headers = { Authorization: 'Bearer '+adminToken };
  const preview = await request.get(API+'/admin/users/'+userId+'/deletion-preview', { headers });
  const data = await preview.json(); expect(data.allowed).toBe(true);
  expect((await request.delete(API+'/admin/users/'+userId, { headers, data: { confirmationToken: data.confirmationToken } })).status()).toBe(204);
}

test('admin deletion during an active session explains the loss and offers a new identity', async ({ page, request }) => {
  const original = await createIdentity(page);
  const admin = await adminSession(request);
  await deleteIdentity(request, admin.access_token, original.user.id);
  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toBeVisible();
  await expect(page.getByRole('button', { name: '创建新身份', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '登录原身份', exact: true })).toHaveCount(0);
});

test('deleted Key shows explicit new identity action without automatic creation', async ({ page, request }) => {
  const original = await createIdentity(page); const admin = await adminSession(request);
  await page.evaluate(s => { localStorage.setItem('banfei:admin:token', s.access_token); localStorage.setItem('banfei:admin:user', JSON.stringify(s.user)); }, admin);
  await emptyEntry(page);
  await deleteIdentity(request, admin.access_token, original.user.id);
  const before = await userCount(request, admin.access_token);
  let creations = 0;
  page.on('request', r => { if (r.url().endsWith('/auth/identity/session') && r.postDataJSON()?.create) creations++; });
  await page.goto('/login?method=key');
  await page.getByLabel('登录链接', { exact: true }).fill(original.key);
  await page.getByRole('button', { name: '登录原身份', exact: true }).click();
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toBeVisible();
  await expect(page.getByText('该身份已被管理员删除，原凭据已失效。请重新建立身份。', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '创建新身份', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '返回当前浏览器身份' })).toHaveCount(0);
  expect(creations).toBe(0); expect(await userCount(request, admin.access_token)).toBe(before);
  expect(await localUser(page)).toBeNull();
  await page.screenshot({ path: test.info().outputPath('deleted-key-entry.png') });
  // A transient creation error must keep a retryable creation action.
  await page.route('**/auth/identity/session', route => route.fulfill({ status: 503, json: { detail: '暂时无法创建，请重试' } }), { times: 1 });
  await page.getByRole('button', { name: '创建新身份', exact: true }).click();
  await expect(page.getByText('暂时无法创建，请重试', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '原身份已删除' })).toBeVisible();
  expect(await userCount(request, admin.access_token)).toBe(before);
  await page.getByRole('button', { name: '创建新身份', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '欢迎使用伴飞' })).toBeVisible();
  expect((await localUser(page)).id).not.toBe(original.user.id);
  await expect(page.getByTestId('identity-key')).not.toHaveText(loginLink(page, original.key));
});
