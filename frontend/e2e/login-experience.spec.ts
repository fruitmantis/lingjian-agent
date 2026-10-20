import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {resolve} from 'node:path';
const origin=process.env.PLAYWRIGHT_HTTP_ORIGIN||'http://localhost',API=origin+'/api';
async function current(page:Page){return page.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')||'null'));}
async function welcome(page:Page,employee=''){
 await page.goto('/');const dialog=page.getByRole('dialog',{name:'欢迎使用伴飞'});await expect(dialog).toBeVisible();
 await expect(dialog.getByRole('button',{name:'复制登录链接',includeHidden:true})).toBeEnabled();
 await expect(dialog.getByTestId('identity-key')).toHaveText(/^http:\/\/.+\/#k=bf_[\w-]{43}$/);
 const link=(await dialog.getByTestId('identity-key').textContent())!;
 if(employee)await dialog.getByRole('textbox',{name:'工号（可选）'}).fill(employee);
 await dialog.getByRole('button',{name:'开始使用伴飞',exact:true}).click();await expect(dialog).toHaveCount(0);
 return {link,key:new URLSearchParams(new URL(link).hash.slice(1)).get('k')!,user:await current(page)};
}
async function admin(request:APIRequestContext){return (await request.post(API+'/auth/admin/login',{data:{username:'admin1',password:'ValidationPass123'}})).json();}
async function count(request:APIRequestContext,token:string){return (await(await request.get(API+'/admin/users',{headers:{Authorization:'Bearer '+token}})).json()).total;}
async function openSwitch(page:Page){await page.locator('.sidebar').getByRole('button',{name:'切换身份',exact:true}).click();return page.getByRole('dialog',{name:'切换身份',exact:true});}
function seed(userId:string){return execFileSync(resolve('../.venv/bin/python'),['-m','backend.tests.support.seed_identity_history',userId],{cwd:resolve('..'),encoding:'utf8'}).trim();}

for(const width of [1366,1920,390])test(`welcome: optional employee, visible compact link, explicit copy and revisit ${width}`,async({page})=>{
 await page.setViewportSize({width,height:width===390?844:900});
 await page.addInitScript(()=>{(window as any).copied=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(value:string)=>{(window as any).copied.push(value);}}});});
 await page.goto('/');const dialog=page.getByRole('dialog',{name:'欢迎使用伴飞'});await expect(dialog).toBeVisible();
 await expect(dialog).toContainText('找到合适的伙伴，把合作推进下去');await expect(dialog).toContainText('可跳过');
 await expect(dialog.getByTestId('identity-key')).toBeVisible();await expect(dialog.getByRole('checkbox')).toHaveCount(0);
 const employee=width===1366?'':'a00123';if(employee)await dialog.getByRole('textbox',{name:'工号（可选）'}).fill(employee);
 await expect(dialog.getByTestId('identity-key')).toHaveText(/^http:\/\/.+\/#k=bf_[\w-]{43}$/);
 const link=(await dialog.getByTestId('identity-key').textContent())!;await expect(dialog.getByRole('button',{name:'复制登录链接',includeHidden:true})).toBeEnabled();
 expect(await page.evaluate(()=>(window as any).copied)).toEqual([]);
 await page.screenshot({path:test.info().outputPath('welcome-'+width+'.png'),mask:[page.getByTestId('identity-key')]});
 await dialog.getByRole('button',{name:'复制登录链接'}).click();await expect(dialog.getByRole('status')).toHaveText('登录链接已复制');
 expect(await page.evaluate(()=>(window as any).copied)).toEqual([link]);expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
 await dialog.getByRole('button',{name:'开始使用伴飞',exact:true}).click();await expect(dialog).toHaveCount(0);
 expect((await current(page)).employee_number).toBe(employee||null);
 await page.reload();await expect(page.locator('.sidebar')).toBeVisible();await expect(dialog).toHaveCount(0);
 await page.goto('/account');await expect(page.getByLabel('工号（可选）',{exact:true})).toHaveValue(employee);await expect(page.getByTestId('identity-key')).toHaveText(link);
});
test('welcome: Escape skips without copying or saving employee',async({page})=>{
 await page.goto('/');const dialog=page.getByRole('dialog',{name:'欢迎使用伴飞'});await expect(dialog).toBeVisible();await page.keyboard.press('Escape');
 await expect(dialog).toHaveCount(0);await page.reload();await expect(page.locator('.sidebar')).toBeVisible();await expect(dialog).toHaveCount(0);expect((await current(page)).employee_number).toBeNull();
});
test('employee: account edits preserve display name, Key, ID and task owner',async({page})=>{
 const original=await welcome(page),task=seed(original.user.id);await page.goto('/account');const name=original.user.display_name;await expect(page.getByLabel('显示名称',{exact:true})).toHaveValue(name);
 await page.getByLabel('工号（可选）',{exact:true}).fill('  000-E  ');await page.getByRole('button',{name:'保存个人信息',exact:true}).click();
 await expect.poll(async()=>(await current(page)).employee_number).toBe('000-E');expect((await current(page)).id).toBe(original.user.id);
 await expect(page.getByLabel('显示名称',{exact:true})).toHaveValue(name);await expect(page.getByTestId('identity-key')).toHaveText(original.link);
 await page.getByLabel('工号（可选）',{exact:true}).fill('');await page.getByRole('button',{name:'保存个人信息',exact:true}).click();await expect.poll(async()=>(await current(page)).employee_number).toBeNull();
 await page.goto('/tasks/'+task);await expect(page.locator('main').getByText('退出身份保留的个人任务',{exact:true})).toBeVisible();
});
test('switch: external A link prompts while B stays valid; copy and cancel preserve B',async({page,browser,request})=>{
 const b=await welcome(page),context=await browser.newContext({baseURL:origin});
 try{const a=await welcome(await context.newPage());let posts=0;page.on('request',req=>{if(req.url().endsWith('/auth/identity/key/login'))posts++;});
 await page.goto(a.link);const dialog=page.getByRole('dialog',{name:'切换身份',exact:true});await expect(dialog).toBeVisible();const token=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));await expect(dialog.getByLabel('目标登录链接')).toHaveValue(a.link);
 expect(posts).toBe(0);expect((await current(page)).id).toBe(b.user.id);
 await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(text:string)=>{(window as any).copied=text;}}}));
 await dialog.getByRole('button',{name:'复制登录链接'}).click();expect(await page.evaluate(()=>(window as any).copied)).toBe(b.link);
 await page.screenshot({path:test.info().outputPath('switch-save-current.png')});await dialog.getByRole('button',{name:'取消',exact:true}).click();await expect(dialog).toHaveCount(0);
 expect(await page.evaluate(()=>localStorage.getItem('banfei:user:token'))).toBe(token);expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+token}})).ok()).toBe(true);expect(posts).toBe(0);
 }finally{await context.close();}
});
for(const source of ['link','key'])test('switch: personal center confirms target and preserves A history '+source,async({page,browser,request})=>{
 const b=await welcome(page),context=await browser.newContext({baseURL:origin});try{
 const a=await welcome(await context.newPage(),'A-001'),task=seed(a.user.id),session=await admin(request),before=await count(request,session.access_token);
 await page.goto('/account');await page.locator('main').getByRole('button',{name:'切换身份',exact:true}).click();const dialog=page.getByRole('dialog',{name:'切换身份',exact:true});
 await dialog.getByLabel('目标登录链接').fill(source==='link'?a.link:a.key);await dialog.getByRole('button',{name:'切换',exact:true}).click();await expect(dialog).toHaveCount(0);
 await expect.poll(async()=>(await current(page)).id).toBe(a.user.id);expect(a.user.id).not.toBe(b.user.id);expect(await count(request,session.access_token)).toBe(before);
 await page.goto('/tasks/'+task);await expect(page.locator('main').getByText('退出身份保留的个人任务',{exact:true})).toBeVisible();
 }finally{await context.close();}
});
test('switch: creating a new identity keeps the old one recoverable', async ({ page, request }) => {
  const a = await welcome(page);
  const session = await admin(request); const before = await count(request, session.access_token);
  const dialog = await openSwitch(page);
  await dialog.getByRole('button', { name: '在这台电脑上新建身份' }).click();
  await expect(dialog.getByText('新建后，这台电脑只会保留新身份')).toBeVisible();
  await dialog.getByRole('button', { name: '确定新建' }).click();
  const created = page.getByRole('dialog', { name: '欢迎使用伴飞' });
  await expect(created).toBeVisible();
  await created.getByRole('button', { name: '开始使用伴飞' }).click();
  expect((await current(page)).id).not.toBe(a.user.id);
  expect(await count(request, session.access_token)).toBe(before + 1);
  await page.goto(a.link);
  const back = page.getByRole('dialog', { name: '切换身份' });
  await back.getByRole('button', { name: '切换', exact: true }).click();
  await expect.poll(async () => (await current(page)).id).toBe(a.user.id);
});

for(const validFormat of [false,true])test('switch: invalid target retains current identity '+validFormat,async({page})=>{
 const b=await welcome(page),token=await page.evaluate(()=>localStorage.getItem('banfei:user:token')),dialog=await openSwitch(page);
 await dialog.getByLabel('目标登录链接').fill(validFormat?origin+'/#k=bf_'+'z'.repeat(43):'invalid');await dialog.getByRole('button',{name:'切换',exact:true}).click();
 await expect(dialog.locator('.error-text[role=alert]')).toBeVisible();expect((await current(page)).id).toBe(b.user.id);expect(await page.evaluate(()=>localStorage.getItem('banfei:user:token'))).toBe(token);
 await dialog.getByRole('button',{name:'取消',exact:true}).click();await expect(page.locator('.sidebar')).toBeVisible();
});
for(const committed of [false,true])test('switch: lost network response confirms actual identity '+committed,async({page,browser,request})=>{
 const b=await welcome(page),token=await page.evaluate(()=>localStorage.getItem('banfei:user:token')),context=await browser.newContext({baseURL:origin});try{
 const a=await welcome(await context.newPage());await page.route('**/auth/identity/key/login',async route=>{if(committed)expect((await route.fetch()).ok()).toBe(true);await route.abort();});
 const dialog=await openSwitch(page);await dialog.getByLabel('目标登录链接').fill(a.link);await dialog.getByRole('button',{name:'切换',exact:true}).click();
 if(committed){
  await expect(dialog).toHaveCount(0);await expect(page.locator('.identity-notice[role=status]')).toHaveText('切换已生效，当前身份：'+(a.user.employee_number||a.user.username));
  expect((await current(page)).id).toBe(a.user.id);const adoptedToken=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));
  const verified=await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+adoptedToken}});expect(verified.ok()).toBe(true);expect((await verified.json()).id).toBe(a.user.id);
  await expect(page.locator('.sidebar')).toBeVisible();
 }else{
  await expect(dialog.locator('.error-text[role=alert]')).toHaveText('切换失败，你仍是原来的身份，请重试。');expect((await current(page)).id).toBe(b.user.id);expect(await page.evaluate(()=>localStorage.getItem('banfei:user:token'))).toBe(token);
  await dialog.getByRole('button',{name:'取消',exact:true}).click();await expect(page.locator('.sidebar')).toBeVisible();
 }
 expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+token}})).status()).toBe(committed?401:200);
 }finally{await context.close();}
});
test('link: new browser restores A without extra identity; same identity link is automatic',async({page,browser,request})=>{
 const a=await welcome(page,'A-101'),session=await admin(request),before=await count(request,session.access_token),context=await browser.newContext({baseURL:origin});try{
 const other=await context.newPage();let creates=0,posts=0;other.on('request',req=>{if(req.url().endsWith('/auth/identity/session')&&req.postDataJSON()?.create)creates++;if(req.url().endsWith('/auth/identity/key/login'))posts++;});
 await other.goto(a.link);await expect(other.locator('.sidebar')).toBeVisible();expect((await current(other)).id).toBe(a.user.id);await expect(other.getByRole('dialog')).toHaveCount(0);expect(creates).toBe(0);expect(posts).toBe(1);
 await other.goto(a.link);await expect(other.locator('.sidebar')).toBeVisible();await expect(other.getByRole('dialog')).toHaveCount(0);expect(posts).toBe(1);expect(await count(request,session.access_token)).toBe(before);
 }finally{await context.close();}
});
test('restore: legacy exit marker resumes valid Cookie without intermediate page',async({page})=>{
 const b=await welcome(page),token=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));
 expect((await page.request.post(API+'/auth/identity/logout',{headers:{Origin:origin,Authorization:'Bearer '+token}})).ok()).toBe(true);
 await page.evaluate(()=>{localStorage.removeItem('banfei:user:token');localStorage.removeItem('banfei:user:user');localStorage.setItem('banfei:user:signed-out','remembered');});
 await page.goto('/');await expect(page.locator('.sidebar')).toBeVisible();expect((await current(page)).id).toBe(b.user.id);await expect(page.getByRole('heading',{name:'已退出伴飞'})).toHaveCount(0);
 expect(await page.evaluate(()=>localStorage.getItem('banfei:user:signed-out'))).toBeNull();await expect(page.getByRole('button',{name:'退出',exact:true})).toHaveCount(0);
});
test('restore: network failure cannot create a replacement identity',async({page})=>{
 let creates=0;await page.route('**/auth/identity/session',route=>{if(route.request().postDataJSON()?.create)creates++;return route.fulfill({status:503,json:{detail:'暂时无法恢复身份，请重试'}});});
 await page.goto('/');await expect(page.locator('.error-text[role=alert]')).toBeVisible();expect(creates).toBe(0);expect(await current(page)).toBeNull();
});
test('switch: same-page hash prompts; cross-tab and administrator remain consistent',async({page,context,browser,request})=>{
 const b=await welcome(page),second=await context.newPage();await second.goto('/');await expect(second.locator('.sidebar')).toBeVisible();
 const session=await admin(request);await page.evaluate(admin=>{localStorage.setItem('banfei:admin:token',admin.access_token);localStorage.setItem('banfei:admin:user',JSON.stringify(admin.user));},session);
 const otherContext=await browser.newContext({baseURL:origin});try{const a=await welcome(await otherContext.newPage());await page.evaluate(link=>{location.hash=new URL(link).hash;},a.link);
 const dialog=page.getByRole('dialog',{name:'切换身份',exact:true});await expect(dialog).toBeVisible();expect((await current(page)).id).toBe(b.user.id);const otherReload=second.waitForEvent('domcontentloaded');await dialog.getByRole('button',{name:'切换',exact:true}).click();
 await otherReload;await expect(second.locator('.sidebar')).toBeVisible();await expect.poll(async()=>(await current(page)).id).toBe(a.user.id);expect((await current(second)).id).toBe(a.user.id);expect(await page.evaluate(()=>localStorage.getItem('banfei:admin:token'))).toBe(session.access_token);
 await page.goto('/admin#k=invalid');await expect(page.locator('.admin-layout')).toBeVisible();await page.getByRole('button',{name:'退出登录',exact:true}).click();await expect(page).toHaveURL(/\/admin\/login$/);
 await page.goto('/');await expect(page.locator('.sidebar')).toBeVisible();expect((await current(page)).id).toBe(a.user.id);
 }finally{await otherContext.close();}
});
