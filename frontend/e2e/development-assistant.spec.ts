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
 admin=await login(r,'admin1');user=await login(r,'user_a');const tags=await ok(await r.get(API+'/development/capabilities',{headers:user}));tag=tags.find((t:{name:string})=>t.name==='数据库').id;const ai=tags.find((t:{name:string})=>t.name==='盘古大模型').id;
 for(const [kind,title,cap] of [['course','数据库迁移合成课程',tag],['lab','数据库进阶迁移实验',tag],['lab','数据库进阶回退实验',tag],['course','RAG 知识库工程课程',ai],['lab','Agent 工具调用集成实验',ai],['lab','Agent 接口可靠性实验',ai]]){
  const row=await ok(await r.post(API+'/admin/enablement/resources',{headers:admin,data:{base_revision:0,metadata:{resource_type:kind,title,summary:'合成实践验证',target_capability:title,product_direction:title,difficulty:'advanced',duration_minutes:90,cost:'free',account_requirement:'测试云账号',source_platform:'synthetic',source_url:'https://example.com/advisor',capability_tag_ids:[cap]}}}));await publish(r,API+'/admin/enablement/resources/'+row.source_id,row);
 }
});
for(const width of [1366,1920])test(`Advisor UX content, discuss and revision ${width}`,async({page,request:r})=>{
 test.setTimeout(150000);await login(r,'user_a',page);await page.setViewportSize({width,height:width===1366?768:1080});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const dir=path.resolve('../artifacts/v12/advisor');await mkdir(dir,{recursive:true});
 async function snap(name:string){await page.evaluate(()=>window.scrollTo(0,0));await page.addStyleTag({content:'nextjs-portal{display:none}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await expect(page.locator('aside').getByRole('link',{name:'伙伴服务能力发展中心',exact:true})).toBeInViewport();await page.screenshot({path:path.join(dir,`${name}-${width}.png`),fullPage:true});}
 async function menu(name:string){await page.getByText('更多',{exact:true}).click();await page.getByRole('button',{name,exact:true}).click();}
 async function create(direction:string){const a=await ok(await r.post(API+'/development/plans',{headers:user,data:{submission_id:randomUUID(),request:{target_partner_id:'partner-1',development_direction:direction,model_input_allowed:true}}}));await expect.poll(async()=> (await ok(await r.get(API+'/development/plans/'+a.plan_id,{headers:user}))).runs[0].status).toBe('ready');return a.plan_id;}
 const id=await create('希望形成企业级 Agent 应用交付能力');const detail=()=>r.get(API+'/development/plans/'+id,{headers:user}).then(ok);
 await page.goto('/tasks/'+id);await expect(page.getByRole('heading',{name:'目标方向',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'基于当前伙伴画像',exact:true})).toBeVisible();await expect(page.getByTestId('advisor-focus').first()).toBeVisible();
 await expect(page.getByRole('button',{name:'设为当前采用版本',exact:true})).not.toBeVisible();await expect(page.getByRole('button',{name:'高级编辑',exact:true})).not.toBeVisible();await expect(page.getByTestId('version-history')).toHaveCount(0);await expect(page.getByTestId('run-records')).toHaveCount(0);await expect(page.locator('main input[type=number]')).toHaveCount(0);await expect(page.locator('main select')).toHaveCount(0);
 await expect(page.getByTestId('resource-advice').first()).toContainText('1.5 小时');await expect(page.getByTestId('resource-advice').first()).toContainText('测试云账号');await snap('01-full-advice');
 const d=await detail(),v1=d.plan.current_version_id;expect(d.plan.confirmed_version_id).toBeNull();
 // Unconfirmed advice can open resources, including the backend-resolved redirect action.
 await page.getByRole('link',{name:'查看来源与发起跳转 →'}).first().click();await expect(page).toHaveURL(/enablement\/resources/);await expect(page.getByRole('button',{name:'发起跳转',exact:true})).toBeVisible();await page.goto('/tasks/'+id);
 for(const [index,message] of ['为什么推荐 RAG？','这两个实验有什么区别？'].entries()){
  await page.getByLabel('消息',{exact:true}).fill(message);await page.getByRole('button',{name:'发送',exact:true}).click();await expect.poll(async()=> (await detail()).conversation.length).toBe(index+1);await expect(page.getByTestId('conversation')).toContainText(message);expect((await detail()).versions.length).toBe(1);expect((await detail()).runs.length).toBe(1);await snap(index?'05-comparison':'04-explanation');
 }
 // Secondary operations remain available but never lead the default page.
 await menu('高级编辑');await expect(page.getByTestId('structured-edit')).toBeVisible();await page.getByRole('button',{name:'取消编辑',exact:true}).click();await expect(page.getByTestId('structured-edit')).toHaveCount(0);
 await menu('设为当前采用版本');await expect.poll(async()=> (await detail()).plan.confirmed_version_id).toBe(v1);
 await page.getByLabel('消息',{exact:true}).fill('模拟调整失败');await page.getByRole('button',{name:'发送',exact:true}).click();await expect.poll(async()=> (await detail()).runs[0].status).toBe('failed');await expect(page.getByTestId('advisor-run-notice')).toContainText('已有建议仍可使用');expect((await detail()).plan.current_version_id).toBe(v1);expect((await detail()).plan.confirmed_version_id).toBe(v1);await snap('07-failed-revise');
 await page.getByLabel('消息',{exact:true}).fill('不要基础课，多给实验');await page.getByRole('button',{name:'发送',exact:true}).click();await expect.poll(async()=> (await detail()).versions.length).toBe(2);await page.reload();await expect(page.getByTestId('analysis')).toHaveCount(0);const v2=await detail();expect(v2.plan.confirmed_version_id).toBe(v1);expect(new Set(v2.payload.stages.flatMap((s:{items:{source_type:string}[]})=>s.items.map(i=>i.source_type)))).toEqual(new Set(['lab']));await snap('06-natural-revise');
 await menu('历史版本');await expect(page.getByTestId('version-history')).toContainText('当前草稿 V2');await expect(page.getByTestId('version-history')).toContainText('已确认 V1');await page.getByRole('button',{name:'收起历史版本',exact:true}).click();
 const exploratory=await create('这个伙伴下一步适合往哪里发展？');await page.goto('/tasks/'+exploratory);await expect(page.getByRole('heading',{name:'值得考虑的发展方向',exact:true})).toBeVisible();await expect(page.getByTestId('resource-advice')).toHaveCount(0);await expect(page.getByRole('heading',{name:'下一步项目实践',exact:true})).toHaveCount(0);await snap('02-exploratory');
 const short=await create('只给几个进阶实验，不要基础课');await page.goto('/tasks/'+short);await expect(page.getByTestId('resource-advice').first()).toBeVisible();await expect(page.getByTestId('analysis')).toHaveCount(0);await expect(page.getByTestId('advisor-focus')).toHaveCount(0);await expect(page.getByRole('heading',{name:'下一步项目实践',exact:true})).toHaveCount(0);await snap('03-short-resources');
 await page.goto('/tasks');await page.getByRole('combobox',{name:'任务类型'}).selectOption('development_plan');await expect(page.locator('tbody').getByTestId('plan-status').first()).toBeVisible();await snap('08-task-list');
 expect(errors).toEqual([]);
});
