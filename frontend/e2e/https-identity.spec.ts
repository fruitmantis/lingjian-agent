import {expect,test} from '@playwright/test';
import {readFileSync} from 'node:fs';

test('HTTPS trusts the CA, preserves old browser identity and enforces the configured Origin',async({page,context,request})=>{
  test.skip(!process.env.PLAYWRIGHT_HTTPS_FIXTURE,'Explicit isolated HTTPS fixture required');
  const fixture=JSON.parse(readFileSync(process.env.PLAYWRIGHT_HTTPS_FIXTURE!,'utf8'));
  const origin=process.env.PLAYWRIGHT_HTTPS_ORIGIN!;
  await context.addCookies([{name:'banfei_identity_session',value:fixture.cookie,domain:'localhost',path:'/',httpOnly:true,secure:false,sameSite:'Strict'}]);
  await page.goto('/');
  await expect(page.locator('.sidebar')).toBeVisible();
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('banfei:user:user')!).id)).toBe(fixture.user_id);
  const capabilities=await page.evaluate(()=>({secure:isSecureContext,locks:typeof navigator.locks?.request==='function',clipboard:typeof navigator.clipboard?.writeText==='function'}));
  expect(capabilities).toEqual({secure:true,locks:true,clipboard:true});
  const cookie=(await context.cookies()).find(item=>item.name==='banfei_identity_session')!;
  expect(cookie.value).toBe(fixture.cookie);expect(cookie.secure).toBe(true);expect(cookie.httpOnly).toBe(true);expect(cookie.sameSite).toBe('Strict');
  await page.goto('/account');await expect(page.getByTestId('identity-key')).toHaveText(fixture.key);
  await page.goto('/tasks');await expect(page.getByRole('cell',{name:'HTTPS 切换前的历史任务',exact:true})).toBeVisible();
  const token=await page.evaluate(()=>localStorage.getItem('banfei:user:token'));
  const probe=await request.get(origin+'/api/__https_validation',{headers:{Authorization:'Bearer '+token,'X-Forwarded-Proto':'http'}});
  expect((await probe.json()).scheme).toBe('https');
  const refused=await request.post(origin+'/api/auth/identity/session',{headers:{Origin:'https://untrusted.invalid'},data:{create:true}});
  expect(refused.status()).toBe(403);expect(refused.headers()['set-cookie']).toBeUndefined();
  expect((await request.get(origin+'/api/agent/tasks/'+fixture.task_id,{headers:{Authorization:'Bearer '+token}})).ok()).toBeTruthy();
});
