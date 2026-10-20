import {test,expect,type Page} from '@playwright/test';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {API,origin,localUser,createIdentity,legacyLogout,adminSession,userCount} from './local-identity-support';

const DEVICE='banfei:user:device-secret';
async function storedDevice(page:Page){
 return page.evaluate(()=>{const token=localStorage.getItem('banfei:user:token')!;return {secret:localStorage.getItem('banfei:user:device-secret'),token,sid:JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).sid};});
}
async function sameDevice(page:Page,secret:string|null){
 expect(await page.evaluate(value=>localStorage.getItem('banfei:user:device-secret')===value,secret)).toBe(true);
 expect((await page.context().cookies()).find(c=>c.name==='banfei_http_identity_session')?.value===secret).toBe(true);
}
for(const cleared of ['cookie','localStorage'])test('device pilot: complementary storage restores the same identity '+cleared,async({page,context,request})=>{
 const original=await createIdentity(page),before=await storedDevice(page),admin=await adminSession(request),users=await userCount(request,admin.access_token);
 const task=execFileSync(resolve('../.venv/bin/python'),['-m','backend.tests.support.seed_identity_history',original.user.id],{cwd:resolve('..'),encoding:'utf8'}).trim();
 let creates=0,resumes=0;page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;if(r.url().endsWith('/auth/identity/resume'))resumes++;});
 if(cleared==='cookie')await context.clearCookies();else await page.evaluate(()=>localStorage.clear());
 await page.reload();await expect(page.locator('.sidebar')).toBeVisible();expect((await localUser(page)).id).toBe(original.user.id);
 await sameDevice(page,before.secret);expect((await storedDevice(page)).sid===before.sid).toBe(true);expect(creates).toBe(0);expect(resumes).toBe(cleared==='cookie'?1:0);
 expect(await userCount(request,admin.access_token)).toBe(users);await page.goto('/tasks/'+task);await expect(page.locator('main').getByText('退出身份保留的个人任务',{exact:true})).toBeVisible();
});
for(const withLink of [false,true])test('device pilot: both stores lost uses only the available link '+withLink,async({page,context,request})=>{
 const original=await createIdentity(page),before=await storedDevice(page),admin=await adminSession(request),users=await userCount(request,admin.access_token);
 const task=execFileSync(resolve('../.venv/bin/python'),['-m','backend.tests.support.seed_identity_history',original.user.id],{cwd:resolve('..'),encoding:'utf8'}).trim();let creates=0;
 await context.clearCookies();await page.evaluate(()=>localStorage.clear());page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;});
 await page.goto(withLink?original.link:'/');
 if(withLink){await expect(page.locator('.sidebar')).toBeVisible();await expect(page.getByRole('dialog')).toHaveCount(0);expect((await localUser(page)).id).toBe(original.user.id);expect(creates).toBe(0);}
 else{await expect(page.getByRole('dialog',{name:'欢迎使用伴飞'})).toBeVisible();expect((await localUser(page)).id).not.toBe(original.user.id);expect(creates).toBe(1);}
 const after=await storedDevice(page);await sameDevice(page,after.secret);expect(after.secret!==before.secret).toBe(true);expect(await userCount(request,admin.access_token)).toBe(users+(withLink?0:1));
 const own=await request.get(API+'/agent/tasks/'+task,{headers:{Authorization:'Bearer '+after.token}});expect(own.status()).toBe(withLink?200:404);
 expect((await request.get(API+'/agent/tasks/'+task,{headers:{Authorization:'Bearer '+before.token}})).status()).toBe(200);
});
test('device pilot: legacy valid token rebuilds a binding without a new user',async({page,context,request})=>{
 const original=await createIdentity(page),before=await storedDevice(page),admin=await adminSession(request),users=await userCount(request,admin.access_token);let creates=0,keys=0;
 await context.clearCookies();await page.evaluate(key=>localStorage.removeItem(key),DEVICE);page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;if(r.url().endsWith('/auth/identity/key/login'))keys++;});
 await page.reload();await expect(page.locator('.sidebar')).toBeVisible();expect((await localUser(page)).id).toBe(original.user.id);expect(creates).toBe(0);expect(keys).toBe(1);
 const after=await storedDevice(page);await sameDevice(page,after.secret);expect(after.secret!==before.secret).toBe(true);expect(await userCount(request,admin.access_token)).toBe(users);
 expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+before.token}})).status()).toBe(200);
});
test('device pilot: legacy Key-read failure never creates or clears old material',async({page,context,request})=>{
 const original=await createIdentity(page),before=await storedDevice(page);await context.clearCookies();await page.evaluate(key=>localStorage.removeItem(key),DEVICE);let creates=0,keys=0;
 await page.route('**/auth/identity/key',route=>route.fulfill({status:503,json:{detail:'synthetic unavailable'}}));page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;if(r.url().endsWith('/auth/identity/key/login'))keys++;});
 await page.reload();await expect(page.locator('.identity-entry-card .error-text[role=alert]')).toHaveText('暂时无法恢复原身份，请重试。');expect(creates).toBe(0);expect(keys).toBe(0);
 expect(await page.evaluate(t=>localStorage.getItem('banfei:user:token')===t,before.token)).toBe(true);expect((await localUser(page)).id).toBe(original.user.id);
 expect((await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+before.token}})).status()).toBe(200);
});
for(const failure of ['network',503,429,403,401,'malformed','empty'] as const)test('device pilot: uncertain resume retains backup and never creates '+failure,async({page,context,request})=>{
 const original=await createIdentity(page),before=await storedDevice(page),admin=await adminSession(request),users=await userCount(request,admin.access_token);let creates=0,keys=0;
 await context.clearCookies();await page.route('**/auth/identity/resume',route=>{if(failure==='network')return route.abort();if(failure==='malformed')return route.fulfill({status:200,contentType:'application/json',body:'{broken'});if(failure==='empty')return route.fulfill({status:200,json:null});return route.fulfill({status:failure,json:{detail:'synthetic restore unavailable'}});});
 page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;if(r.url().endsWith('/auth/identity/key/login'))keys++;});
 await page.reload();await expect(page.locator('.identity-entry-card .error-text[role=alert]')).toBeVisible();
 expect(await page.evaluate(v=>localStorage.getItem('banfei:user:device-secret')===v,before.secret)).toBe(true);expect(await page.evaluate(v=>localStorage.getItem('banfei:user:token')===v,before.token)).toBe(true);expect(creates).toBe(0);expect(keys).toBe(0);
 await page.unroute('**/auth/identity/resume');await page.reload();await expect(page.locator('.sidebar')).toBeVisible();expect((await localUser(page)).id).toBe(original.user.id);await sameDevice(page,before.secret);expect(await userCount(request,admin.access_token)).toBe(users);
});
test('device pilot: only explicit invalid backup is cleared without creating on login',async({page,context})=>{
 await createIdentity(page);await legacyLogout(page);await context.clearCookies();let creates=0;
 page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;});await page.goto('/login');
 await expect(page.getByLabel('登录链接',{exact:true})).toBeVisible();expect(await page.evaluate(key=>localStorage.getItem(key),DEVICE)).toBeNull();expect(creates).toBe(0);
});
test('device pilot: verified Cookie replaces a different valid backup',async({page,browser,request})=>{
 const a=await createIdentity(page),first=await storedDevice(page),other=await browser.newContext({baseURL:origin.Origin});try{
 const p=await other.newPage(),b=await createIdentity(p),second=await storedDevice(p);await page.evaluate(({key,value})=>localStorage.setItem(key,value!),{key:DEVICE,value:second.secret});let resumes=0;page.on('request',r=>{if(r.url().endsWith('/auth/identity/resume'))resumes++;});
 await page.reload();await expect(page.locator('.sidebar')).toBeVisible();expect((await localUser(page)).id).toBe(a.user.id);await sameDevice(page,first.secret);expect(resumes).toBe(0);
 const stillB=await request.get(API+'/auth/me',{headers:{Authorization:'Bearer '+second.token}});expect((await stillB.json()).id).toBe(b.user.id);
 }finally{await other.close();}
});
test('device pilot: unavailable storage degrades to cookie-only with a notice',async({page,context})=>{
 await createIdentity(page);const before=await storedDevice(page);let creates=0;
 await page.addInitScript(()=>{Storage.prototype.setItem=function(){throw new DOMException('denied','SecurityError');};});page.on('request',r=>{if(r.url().endsWith('/auth/identity/session')&&r.postDataJSON()?.create)creates++;});
 await page.reload();await expect(page.locator('.sidebar')).toBeVisible();
 await expect(page.getByText('这台电脑无法保存身份备份')).toBeVisible();expect(creates).toBe(0);
 expect((await context.cookies()).find(c=>c.name==='banfei_http_identity_session')?.value===before.secret).toBe(true);
 await page.getByRole('button',{name:'知道了'}).click();await expect(page.getByText('这台电脑无法保存身份备份')).toHaveCount(0);
});
test('device pilot: missing response backup reports version mismatch without empty overwrite',async({page})=>{
 await createIdentity(page);const before=await storedDevice(page);let creates=0;
 await page.route('**/auth/identity/session',async route=>{if(route.request().postDataJSON()?.create)creates++;const response=await route.fetch(),body=await response.json();delete body.device_secret;await route.fulfill({response,json:body});});
 await page.reload();await expect(page.locator('.identity-entry-card .error-text[role=alert]')).toHaveText('身份接口版本不一致，请刷新后重试。');expect(await page.evaluate(value=>localStorage.getItem('banfei:user:device-secret')===value,before.secret)).toBe(true);expect(creates).toBe(0);
});

async function openSwitch(page: Page) {
  await page.locator('.sidebar').getByRole('button', {name:'切换身份', exact:true}).click();
  const dialog = page.getByRole('dialog', {name:'切换身份', exact:true});
  await expect(dialog).toBeVisible();
  return dialog;
}
async function capture(page: Page, name: string) {
  await page.screenshot({path:test.info().outputPath(name+'.png'),
    mask:[page.getByTestId('identity-key'), page.getByLabel('目标登录链接')]});
}
async function blockStorage(page: Page, mode: 'write'|'all') {
  await page.addInitScript((mode)=>{
    Storage.prototype.setItem=function(){throw new DOMException('synthetic storage restriction','QuotaExceededError');};
    if(mode==='all'){
      Storage.prototype.getItem=function(){throw new DOMException('synthetic read restriction','SecurityError');};
      Storage.prototype.removeItem=function(){throw new DOMException('synthetic removal restriction','SecurityError');};
    }
  },mode);
}
for(const mode of ['write','all'] as const)test('storage fallback: fresh browser supports authenticated use '+mode,async({page})=>{
  await blockStorage(page,mode);
  const sessions:{id:string,created:boolean}[]=[];
  page.on('response',async response=>{
    if(response.url().endsWith('/auth/identity/session')&&response.ok()){
      const data=await response.json().catch(()=>null);
      if(data?.user)sessions.push({id:data.user.id,created:data.created});
    }
  });
  await page.goto('/');
  const welcome=page.getByRole('dialog',{name:'欢迎使用伴飞'});
  await expect(welcome).toBeVisible();
  await expect(welcome.getByTestId('identity-key')).toHaveText(/^http:\/\/.+\/#k=bf_[\w-]{43}$/);
  await welcome.getByRole('button',{name:'开始使用伴飞',exact:true}).click();
  await expect(page.getByText('这台电脑无法保存身份备份',{exact:false})).toBeVisible();
  await page.goto('/account');
  await expect(page.getByTestId('identity-key')).toHaveText(/^http:\/\/.+\/#k=bf_[\w-]{43}$/);
  await page.reload();
  await expect(page.getByTestId('identity-key')).toHaveText(/^http:\/\/.+\/#k=bf_[\w-]{43}$/);
  expect(sessions.filter(s=>s.created)).toHaveLength(1);
  expect(new Set(sessions.map(s=>s.id)).size).toBe(1);
  await capture(page,'storage-'+mode);
});

test('storage fallback: write failure cannot leave the previous bearer after switching',async({page,browser})=>{
  const a=await createIdentity(page), other=await browser.newContext({baseURL:origin.Origin});
  try{
    const b=await createIdentity(await other.newPage());
    await blockStorage(page,'write');await page.reload();await expect(page.locator('.sidebar')).toBeVisible();
    const dialog=await openSwitch(page);await dialog.getByLabel('目标登录链接').fill(b.link);
    const login=page.waitForResponse(r=>r.url().endsWith('/auth/identity/key/login')&&r.status()===200);
    await dialog.getByRole('button',{name:'切换',exact:true}).click();expect((await(await login).json()).user.id).toBe(b.user.id);
    await expect(dialog).toHaveCount(0);
    const ownKey=page.waitForResponse(r=>r.url().endsWith('/auth/identity/key'));
    await page.goto('/account');const response=await ownKey;
    expect(response.status()).toBe(200);
    expect((await response.json()).key).toBe(b.key);
    await expect(page.getByTestId('identity-key')).toHaveText(b.link);
  }finally{await other.close();}
});
