import type {Page} from '@playwright/test';

/** Keep existing isolated business-UI mocks on the current identity handshake. */
export async function mockDeviceSession(page:Page){
 await page.route('**/api/auth/identity/session',async route=>{
  if(route.request().method()!=='POST'||route.request().postDataJSON()?.create)return route.fallback();
  const data=await page.evaluate(async()=>{
   const token=localStorage.getItem('banfei:user:token');
   if(!token)return null;
   const response=await fetch('/api/auth/me',{headers:{Authorization:'Bearer '+token},cache:'no-store'});
   if(!response.ok)return null;
   const user=await response.json();
   if(user.role!=='user')return null;
   return {access_token:token,token_type:'bearer',user,created:false,
    device_secret:localStorage.getItem('banfei:user:device-secret')||'isolated-ui-device-credential-'.padEnd(43,'x')};
  });
  if(!data)return route.fallback();
  return route.fulfill({json:data,headers:{'Cache-Control':'no-store'}});
 });
}
