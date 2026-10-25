import type {Page} from '@playwright/test';

/** Keep existing isolated business-UI mocks on the current identity handshake. */
export async function mockDeviceSession(page:Page){
 // Existing business-only fixtures must also supply the new authenticated options read.
 await page.route('**/api/agents/*/models',route=>route.fulfill({json:{models:[{id:'model-1',name:'合成模型',isDefault:true}],defaultModelConfigId:'model-1',agentEnabled:true,unavailableReason:null}}));

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
