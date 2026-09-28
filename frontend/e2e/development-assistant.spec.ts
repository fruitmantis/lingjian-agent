import {fixtureLogin} from "./identity-fixture";
import {test,expect,type APIRequestContext,type Page} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import {evidenceRoot} from './evidence-path';
import {randomUUID} from 'node:crypto';
const API='http://localhost:8000';
let admin:Record<string,string>,user:Record<string,string>,tag:string;
async function login(r:APIRequestContext,name:string,page?:Page){const res=await fixtureLogin(r, name, 'ValidationPass123');expect(res.ok()).toBeTruthy();const s=await res.json();if(page)await page.addInitScript(s=>{localStorage.setItem(`banfei:${s.user.role}:token`, s.access_token); localStorage.setItem(`banfei:${s.user.role}:user`, JSON.stringify(s.user));},s);return {Authorization:`Bearer ${s.access_token}`};}
async function ok(res:Awaited<ReturnType<APIRequestContext['get']>>){expect(res.ok(),await res.text()).toBeTruthy();return res.status()===204?null:res.json();}
async function publish(r:APIRequestContext,url:string,row:{revision:number}){row=await ok(await r.patch(url+'/permissions',{headers:admin,data:{base_revision:row.revision,system_visible:true,model_allowed:true,partner_allowed:true,reason:"V1.2 合成测试授权"}}));if(url.includes('/sharing'))await ok(await r.post(url+'/review',{headers:admin,data:{base_revision:row.revision,link_status:'available',content_checked:true,authorization_checked:true}}));return ok(await r.post(url+'/publish',{headers:admin,data:{base_revision:row.revision}}));}
test.beforeAll(async({request:r})=>{
 admin=await login(r,'admin1');user=await login(r,'user_a');const tags=await ok(await r.get(API+'/development/capabilities',{headers:user}));tag=tags.find((t:{name:string})=>t.name==='数据库').id;const ai=tags.find((t:{name:string})=>t.name==='盘古大模型').id;
 for(const [kind,title,cap] of [['course','数据库迁移合成课程',tag],['lab','数据库进阶迁移实验',tag],['lab','数据库进阶回退实验',tag],['course','RAG 知识库工程课程',ai],['lab','Agent 工具调用集成实验',ai],['lab','Agent 接口可靠性实验',ai]]){
  const row=await ok(await r.post(API+'/admin/enablement/resources',{headers:admin,data:{base_revision:0,metadata:{resource_type:kind,title,summary:'合成实践验证',level:'advanced',duration_minutes:90,role_ids:['role-7'],zone_ids:['zone-4'],...(kind==='course'?{course_goals:title}:{lab_goals:title,lab_requirements:'合成实践要求'}),source_url:'https://example.com/advisor'}}}));await publish(r,API+'/admin/enablement/resources/'+row.source_id,row);
 }
});
for(const width of [1366,1920])test(`Advisor UX content, discuss and revision ${width}`,async({page,request:r})=>{
 test.setTimeout(150000);await login(r,'user_a',page);await page.setViewportSize({width,height:width===1366?768:1080});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const dir=path.resolve(`${evidenceRoot}/advisor`);await mkdir(dir,{recursive:true});
 async function snap(name:string){await page.evaluate(()=>window.scrollTo(0,0));await page.addStyleTag({content:'nextjs-portal{display:none}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await expect(page.locator('aside').getByRole('link',{name:'资源中心',exact:true})).toBeInViewport();await page.screenshot({path:path.join(dir,`${name}-${width}.png`),fullPage:true});}
 async function menu(name:string){await page.getByText('更多',{exact:true}).click();await page.getByRole('button',{name,exact:true}).click();}
 async function create(direction:string){const a=await ok(await r.post(API+'/development/plans',{headers:user,data:{submission_id:randomUUID(),request:{target_partner_id:'partner-1',development_direction:direction,model_input_allowed:true}}}));await expect.poll(async()=> (await ok(await r.get(API+'/development/plans/'+a.plan_id,{headers:user}))).runs[0].status).toBe('ready');return a.plan_id;}
 const id=await create('希望形成企业级 Agent 应用交付能力');const detail=()=>r.get(API+'/development/plans/'+id,{headers:user}).then(ok);
 await page.goto('/tasks/'+id);await expect(page.getByRole('heading',{name:'目标方向',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'基于当前伙伴画像',exact:true})).toBeVisible();await expect(page.getByTestId('advisor-focus').first()).toBeVisible();
 await expect(page.getByRole('button',{name:'设为当前采用版本',exact:true})).not.toBeVisible();await expect(page.getByRole('button',{name:'高级编辑',exact:true})).toHaveCount(0);await expect(page.getByTestId('version-history')).toHaveCount(0);await expect(page.getByTestId('run-records')).toHaveCount(0);await expect(page.locator('main input[type=number]')).toHaveCount(0);await expect(page.locator('main select')).toHaveCount(0);
 const courseAdvice=page.getByTestId('resource-advice').filter({has:page.locator('.advisor-resource-type',{hasText:'课程'})});
 const labAdvice=page.getByTestId('resource-advice').filter({has:page.locator('.advisor-resource-type',{hasText:'实验'})});
 await expect(courseAdvice.first()).toBeVisible();await expect(courseAdvice.locator('dt').filter({hasText:'时长'})).toHaveCount(0);
 await expect(labAdvice.first()).toContainText('1.5 小时');await expect(page.getByTestId('resource-advice').first()).toContainText('进阶');await snap('01-full-advice');
 const d=await detail(),v1=d.plan.current_version_id;expect(d.plan).not.toHaveProperty("confirmed_version_id");
 // Current advice can open resources without confirmation, including the backend-resolved redirect action.
 await page.getByRole('link',{name:'查看资源',exact:true}).first().click();await expect(page).toHaveURL(/resources\//);await expect(page.getByRole('button',{name:/前往课程|前往实验/})).toBeVisible();await page.goto('/tasks/'+id);
 for(const [index,message] of ['为什么推荐 RAG？','这两个实验有什么区别？','还需要补哪些准备？'].entries()){
  await page.getByLabel('消息',{exact:true}).fill(message);await page.getByRole('button',{name:'发送',exact:true}).click();await expect.poll(async()=> (await detail()).conversation.length).toBe(index+1);await expect(page.getByTestId('conversation')).toContainText(message);
  const answer=page.getByTestId('advisor-answer').nth(index);
  await expect(answer.getByRole('heading',{name:'结论',level:3,exact:true})).toBeVisible();
  const topics=answer.locator('h4');expect(await topics.count()).toBeGreaterThanOrEqual(1);expect(await topics.count()).toBeLessThanOrEqual(3);
  await expect(topics.first()).toHaveText(['推荐依据','资源差异','实践准备'][index]);
  await expect(answer.locator('li').first()).toBeVisible();await expect(answer).not.toContainText('###');
  const spacing=await answer.evaluate(el=>({title:parseFloat(getComputedStyle(el.querySelector('h3')!).fontSize),topic:parseFloat(getComputedStyle(el.querySelector('h4')!).fontSize),paragraph:parseFloat(getComputedStyle(el.querySelector('.advisor-answer-body p')!).marginTop),list:parseFloat(getComputedStyle(el.querySelector('li')!).marginTop)}));
  expect(spacing.title).toBeGreaterThan(spacing.topic);expect(spacing.paragraph).toBeGreaterThanOrEqual(10);expect(spacing.list).toBeGreaterThanOrEqual(6);
  expect((await detail()).versions.length).toBe(1);expect((await detail()).runs.length).toBe(1);await snap(index?'05-comparison':'04-explanation');
 }
 // Natural language is the only user-facing editing path; backend edit API remains tested separately.
 await page.getByText('更多',{exact:true}).click();
 await expect(page.getByRole('button',{name:'高级编辑',exact:true})).toHaveCount(0);
 await expect(page.getByTestId('structured-edit')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'运行记录',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'运行记录',exact:true}).click();
 await expect(page.getByTestId('run-records')).toBeVisible();
 await menu('运行记录');await expect(page.getByTestId('run-records')).toHaveCount(0);
 await menu('伙伴可传递视图预览');await expect(page.getByTestId('transfer-preview')).toBeVisible();await page.getByRole('button',{name:'关闭预览',exact:true}).click();
 await page.getByLabel('消息',{exact:true}).fill('模拟调整失败');await page.getByRole('button',{name:'发送',exact:true}).click();await expect.poll(async()=> (await detail()).runs[0].status).toBe('failed');await expect(page.getByTestId('advisor-run-notice')).toContainText('当前建议保持不变');expect((await detail()).plan.current_version_id).toBe(v1);expect((await detail()).plan).not.toHaveProperty("confirmed_version_id");await snap('07-failed-revise');
 await page.getByLabel('消息',{exact:true}).fill('不要基础课，多给实验');await page.getByRole('button',{name:'发送',exact:true}).click();await expect.poll(async()=> (await detail()).versions.length).toBe(2);await page.reload();await expect(page.getByTestId('analysis')).toHaveCount(0);const v2=await detail();expect(v2.plan.current_version_id).not.toBe(v1);expect(v2.plan).not.toHaveProperty("confirmed_version_id");expect(new Set(v2.payload.stages.flatMap((s:{items:{source_type:string}[]})=>s.items.map(i=>i.source_type)))).toEqual(new Set(['lab']));await snap('06-natural-revise');
 await menu('历史版本');await expect(page.getByTestId('version-history')).toContainText('V2 · 当前版本');await expect(page.getByTestId('version-history')).toContainText('V1 · 历史版本');await expect(page.locator('main')).not.toContainText(/草稿|尚未确认|当前采用/);
 await page.getByTestId('version-history').locator('select').selectOption(v1);
 await expect(page.getByText('正在查看历史内容。',{exact:false})).toBeVisible();
 await expect(page.getByTestId('analysis')).toBeVisible();
 expect((await detail()).plan.current_version_id).toBe(v2.plan.current_version_id);
 expect((await detail()).plan).not.toHaveProperty("confirmed_version_id");
 await page.getByRole('button',{name:'返回最新建议继续交流',exact:true}).click();
 await expect(page.getByTestId('analysis')).toHaveCount(0);
 await page.getByRole('button',{name:'收起历史版本',exact:true}).click();
 const exploratory=await create('这个伙伴下一步适合往哪里发展？');await page.goto('/tasks/'+exploratory);await expect(page.getByRole('heading',{name:'值得考虑的发展方向',exact:true})).toBeVisible();await expect(page.getByTestId('resource-advice')).toHaveCount(0);await expect(page.getByRole('heading',{name:'下一步项目实践',exact:true})).toHaveCount(0);await snap('02-exploratory');
 const short=await create('只给几个进阶实验，不要基础课');await page.goto('/tasks/'+short);await expect(page.getByTestId('resource-advice').first()).toBeVisible();await expect(page.getByTestId('analysis')).toHaveCount(0);await expect(page.getByTestId('advisor-focus')).toHaveCount(0);await expect(page.getByRole('heading',{name:'下一步项目实践',exact:true})).toHaveCount(0);await snap('03-short-resources');
 await page.goto('/tasks');await page.getByRole('combobox',{name:'任务类型'}).selectOption('development_plan');await expect(page.locator('tbody').getByTestId('plan-status').first()).toBeVisible();await snap('08-task-list');
 expect(errors).toEqual([]);
});

for (const width of [390,1280]) test(`Advisor reply prose wraps safely and preserves historical plain text ${width}`,async({page,request:r})=>{
 await login(r,'user_a',page);await page.setViewportSize({width,height:900});
 const accepted=await ok(await r.post(API+'/development/plans',{headers:user,data:{submission_id:randomUUID(),request:{target_partner_id:'partner-1',development_direction:'Agent 应用交付'}}}));
 const url=API+'/development/plans/'+accepted.plan_id;
 await expect.poll(async()=>(await ok(await r.get(url,{headers:user}))).runs[0].status).toBe('ready');
 const original=await ok(await r.get(url,{headers:user}));
 const answers=[
  '### 结论\n\n先验证接口。\n\n#### 接口边界\n\n- **输入**：明确数据。\n- 输出：核对格式。',
  '## **结论**\n\n按目标选择实验。\n\n### 对比维度\n\n1. 先修条件。\n2. 实际用途。\n\n### 实践投入\n\n结合可用时间安排。\n\n### 选择建议\n\n先完成小规模验证。',
  '【结论】\r\n先检查环境。\r\n【环境准备】\r\n- 核实账号。\r\n- 准备样本。',
  '### 结论\n\n保留长标识和原始文本。\n\n#### 输入示例\n\n'+'A'.repeat(1500)+'\n\n<img src=x onerror="window.__advisorInjected=true">',
  '这是历史简短回答。\n保留原有换行。',
 ];
 await page.route(url,route=>route.fulfill({json:{...original,conversation:answers.map((answer,index)=>({submission_id:String(index),message:'测试问题 '+index,answer}))}}));
 await page.goto('/tasks/'+accepted.plan_id);
 const replies=page.getByTestId('advisor-answer');await expect(replies).toHaveCount(5);
 for(let index=0;index<4;index++)await expect(replies.nth(index).getByRole('heading',{level:3,name:'结论',exact:true})).toBeVisible();
 await expect(replies.nth(0).locator('ul li')).toHaveCount(2);await expect(replies.nth(0).locator('li strong')).toHaveText('输入');
 await expect(replies.nth(1).locator('h4')).toHaveCount(3);await expect(replies.nth(1).locator('ol li')).toHaveCount(2);
 await expect(replies.nth(2).locator('ul li')).toHaveCount(2);
 await expect(replies.nth(4).locator('.advisor-answer-body p')).toHaveText('这是历史简短回答。\n保留原有换行。');
 await expect(replies.locator('img,script,iframe,a')).toHaveCount(0);
 expect(await page.evaluate(()=>Reflect.get(window,'__advisorInjected'))).toBeUndefined();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 for(const reply of await replies.all())expect(await reply.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBeTruthy();
});
