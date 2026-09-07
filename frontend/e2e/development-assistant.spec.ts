import {test,expect,type APIRequestContext,type Page} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
const API='http://127.0.0.1:8100';
let admin:Record<string,string>,user:Record<string,string>,tag:string;
async function login(r:APIRequestContext,name:string,page?:Page){const res=await r.post(API+'/auth/login',{data:{username:name,password:'ValidationPass123'}});expect(res.ok()).toBeTruthy();const s=await res.json();if(page)await page.addInitScript(s=>{localStorage.setItem('token',s.access_token);localStorage.setItem('user',JSON.stringify(s.user));},s);return {Authorization:`Bearer ${s.access_token}`};}
async function ok(res:Awaited<ReturnType<APIRequestContext['get']>>){expect(res.ok(),await res.text()).toBeTruthy();return res.status()===204?null:res.json();}
async function publish(r:APIRequestContext,url:string,row:{revision:number}){row=await ok(await r.patch(url+'/permissions',{headers:admin,data:{base_revision:row.revision,system_visible:true,model_allowed:true,partner_allowed:true,reason:"V1.2 合成测试授权"}}));await ok(await r.post(url+'/review',{headers:admin,data:{base_revision:row.revision,link_status:'available',content_checked:true,authorization_checked:true}}));return ok(await r.post(url+'/publish',{headers:admin,data:{base_revision:row.revision}}));}
test.beforeAll(async({request:r})=>{
 admin=await login(r,'admin1');user=await login(r,'user_a');tag=(await ok(await r.get(API+'/development/capabilities',{headers:user}))).find((t:{name:string})=>t.name==='数据库').id;
 for(const [kind,title] of [['course','数据库迁移合成课程'],['lab','数据库进阶迁移实验'],['lab','数据库进阶回退实验']]){
  const row=await ok(await r.post(API+'/admin/enablement/resources',{headers:admin,data:{base_revision:0,metadata:{resource_type:kind,title,summary:'合成迁移验证',target_capability:title,difficulty:'advanced',source_platform:'synthetic',source_url:'https://example.com/v12',capability_tag_ids:[tag]}}}));await publish(r,API+'/admin/enablement/resources/'+row.source_id,row);
 }
});
for(const width of [1366,1920])test(`V1.2 minimal entry, advice, explanation, revision, gap and recovery ${width}`,async({page,request:r})=>{
 test.setTimeout(120000);await login(r,'user_a',page);await page.setViewportSize({width,height:width===1366?768:1080});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const dir=path.resolve('../artifacts/v12/screenshots');await mkdir(dir,{recursive:true});
 async function snap(name:string){if(new URL(page.url()).pathname.startsWith('/tasks/')){const current=page.locator('aside [aria-current=page]');await expect(current.getByTestId('plan-primary')).toHaveText(await page.locator('main').getByTestId('plan-primary').innerText(),{timeout:10000});await expect(current.getByTestId('plan-latest-run')).toHaveText(await page.locator('main').getByTestId('plan-latest-run').innerText(),{timeout:10000});}await page.evaluate(()=>window.scrollTo(0,0));await page.addStyleTag({content:'nextjs-portal{display:none}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await expect(page.locator('aside').getByRole('link',{name:'伙伴服务能力发展中心',exact:true})).toBeInViewport();await page.screenshot({path:path.join(dir,`${name}-${width}.png`),fullPage:true});}
 await page.goto('/enablement?partner_id=partner-1');await page.getByLabel('发展方向',{exact:true}).fill('数据库迁移');
 for(const label of ['参训岗位','人员已知基础','周期（周）','语言','账号条件','添加目标能力','本次目标要求'])await expect(page.getByLabel(label,{exact:true})).toHaveCount(0);
 await snap('01-minimal');
 const accepted=page.waitForResponse(res=>res.url()===API+'/development/plans'&&res.request().method()==='POST');await page.getByRole('button',{name:'生成能力发展建议',exact:true}).click();const id=(await (await accepted).json()).plan_id;
 const detail=()=>r.get(API+'/development/plans/'+id,{headers:user}).then(ok);
 await expect(page).toHaveURL('/tasks/'+id);await expect(page.getByTestId('analysis')).toBeVisible();await expect(page.getByTestId('stages')).toBeVisible();await snap('02-advice');
 const d=await detail(),v1=d.plan.current_version_id;expect(d.plan.confirmed_version_id).toBeNull();
 await expect(page.getByRole('link',{name:'查看来源与发起跳转'}).first()).toBeVisible();
 for(const message of ['为什么推荐这个方向？','这两个实验有什么区别？']){
  await page.getByLabel('消息',{exact:true}).fill(message);await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.getByTestId('conversation')).toContainText(message);await expect.poll(async()=> (await detail()).conversation.length).toBe(message.startsWith('为什么')?1:2);
  expect((await detail()).versions.length).toBe(1);expect((await detail()).runs.length).toBe(1);
 }
 await snap('03-explanation');
 await page.getByRole('button',{name:'确认当前版本',exact:true}).click();await expect.poll(async()=> (await detail()).plan.confirmed_version_id).toBe(v1);
 await page.getByLabel('消息',{exact:true}).fill('不要基础课，多给实验');await page.getByRole('button',{name:'发送',exact:true}).click();await expect.poll(async()=> (await detail()).versions.length).toBe(2);await page.reload();await expect(page.getByTestId('analysis')).toHaveCount(0);await expect(page.getByTestId('stages')).toBeVisible();const v2=await detail();expect(v2.plan.confirmed_version_id).toBe(v1);expect(new Set(v2.payload.stages.flatMap((s:{items:{source_type:string}[]})=>s.items.map(i=>i.source_type)))).toEqual(new Set(['lab']));await snap('04-short-revision');
 await ok(await r.post(API+`/development/plans/${id}/revise`,{headers:user,data:{submission_id:randomUUID(),based_on_version_id:v2.plan.current_version_id,instruction:'C_FAIL 合成失败'}}));await expect.poll(async()=> (await detail()).runs[0].status).toBe('failed');expect((await detail()).plan.current_version_id).toBe(v2.plan.current_version_id);await page.reload();await expect(page.locator('main').getByTestId('plan-primary')).toHaveText('方案可用');
 const gap=await ok(await r.post(API+'/development/plans',{headers:user,data:{submission_id:randomUUID(),request:{target_partner_id:'partner-1',development_direction:'C_GAP Agent 应用交付'}}}));await page.goto('/tasks/'+gap.plan_id);await expect(page.getByTestId('gaps')).toContainText('当前资源库未找到匹配');await snap('05-resource-gap');
 expect(errors).toEqual([]);
});
