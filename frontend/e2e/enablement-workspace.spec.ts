import {test,expect,type APIRequestContext,type Page} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
const API='http://127.0.0.1:8100';
test.describe.configure({mode:'serial'});
let adminHeaders:Record<string,string>;let course:string;let lab:string;let sharedCase:string;
async function login(request:APIRequestContext,username='user_a',page?:Page){
  const response=await request.post(API+'/auth/login',{data:{username,password:'ValidationPass123'}});
  expect(response.ok()).toBeTruthy();const session=await response.json();
  if(page)await page.addInitScript(s=>{localStorage.setItem('token',s.access_token);localStorage.setItem('user',JSON.stringify(s.user));},session);
  return {Authorization:`Bearer ${session.access_token}`};
}
async function checked(response:Awaited<ReturnType<APIRequestContext['get']>>){expect(response.ok(),`Unexpected API status ${response.status()}`).toBeTruthy();return response.json();}
async function publish(request:APIRequestContext,url:string,row:{revision:number}){
  row=await checked(await request.patch(url+'/permissions',{headers:adminHeaders,data:{base_revision:row.revision,system_visible:true,model_allowed:false,partner_allowed:false,reason:'合成自动化验证授权'}}));
  await checked(await request.post(url+'/review',{headers:adminHeaders,data:{base_revision:row.revision,link_status:'available',content_checked:true,authorization_checked:true}}));
  return checked(await request.post(url+'/publish',{headers:adminHeaders,data:{base_revision:row.revision}}));
}
test.beforeAll(async({request})=>{
  adminHeaders=await login(request,'admin1');
  const tags=await checked(await request.get(API+'/admin/capability-tags',{headers:adminHeaders}));
  const tag=tags.find((t:{name:string})=>t.name==='数据库')||tags[0];
  for(const kind of ['course','lab']){
    const row=await checked(await request.post(API+'/admin/enablement/resources',{headers:adminHeaders,data:{base_revision:0,metadata:{resource_type:kind,title:kind==='course'?'数据库迁移基础课程（合成验证）':'数据库迁移演练实验（合成验证）',summary:'通过迁移检查、验证与复盘，理解交付过程中的关键步骤。本条为自动化合成资源。',target_capability:'数据库迁移与交付验证',audience:'交付工程师',product_direction:'数据库',difficulty:'beginner',language:'中文',site:'中国站',cost:'free',account_requirement:'企业账号',environment_requirement:'未知',source_platform:'合成资源平台',source_url:`https://example.com/${kind}`,capability_tag_ids:[tag.id]}}}));
    await publish(request,API+'/admin/enablement/resources/'+row.source_id,row);
    if(kind==='course')course=row.source_id;else lab=row.source_id;
  }
  const base=await checked(await request.post(API+'/cases',{headers:adminHeaders,data:{partner_id:'partner-1',title:'内部案例证据标题',description:'INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE'}}));sharedCase=base.id;
  const url=API+`/admin/cases/${sharedCase}/sharing`;
  const row=await checked(await request.put(url,{headers:adminHeaders,data:{base_revision:0,metadata:{title:'伙伴迁移实践共享案例（合成验证）',summary:'脱敏后的迁移验证实践，仅包含获准共享的方法。',methods:'制定核验清单，分阶段验证迁移结果并复盘。',contributor_role:'承担迁移验证实施，不代表其他交付环节的能力。',source_platform:'合成案例平台',source_url:'https://example.com/shared-case',capability_tag_ids:[tag.id]}}}));
  await publish(request,url,row);
});

test('NAV-01/SCN-01 center preserves navigation and offers truthful scene entries',async({page,request})=>{
  await login(request,'admin1',page);await page.goto('/enablement');
  for(const name of ['开启新任务','场景广场','伙伴洞察','全部任务','个人中心','管理后台','伙伴服务能力发展中心'])await expect(page.locator('aside').getByRole('link',{name,exact:true})).toBeVisible();
  await expect(page.getByText('填写发展诉求后可生成结构化方案。',{exact:false})).toBeVisible();
  await page.getByLabel('选择目标伙伴').selectOption('partner-1');
  await expect(page.getByText('具备制造知识库实施能力',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'生成方案',exact:true})).toHaveCount(0);
  await page.goto('/scenes?category='+encodeURIComponent('能力发展'));
  for(const name of ['制定伙伴服务能力发展方案','查找课程与实验','学习优秀伙伴案例'])await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
  await page.getByRole('link',{name:'查看共享案例',exact:true}).click();
  await expect(page.getByRole('tab',{name:'案例',exact:true})).toHaveAttribute('aria-selected','true');
});

test('RES-02/03 search filters details and unknown metadata use current resources',async({page,request})=>{
  await login(request,'user_a',page);await page.goto('/enablement?tab=resources');
  await expect(page.getByRole('link',{name:'数据库迁移基础课程（合成验证）',exact:true})).toBeVisible();
  await page.getByLabel('资源名称',{exact:true}).fill('不存在的课程');await page.getByRole('button',{name:'搜索资源',exact:true}).click();
  await expect(page.getByRole('heading',{name:'暂无符合条件的资源'})).toBeVisible();
  await page.getByRole('button',{name:'重置筛选',exact:true}).click();
  for(const [label,value] of [['能力','数据库'],['岗位 / 适用对象','交付工程师'],['产品 / 技术方向','数据库'],['难度','入门'],['语言','中文'],['站点','中国站'],['费用','免费'],['账号条件','企业账号'],['环境条件','未知'],['先修条件','未知']])await page.getByLabel(label,{exact:true}).selectOption({label:value});
  await page.getByRole('button',{name:'搜索资源',exact:true}).click();
  await page.getByRole('link',{name:'数据库迁移基础课程（合成验证）',exact:true}).click();
  await expect(page.getByRole('heading',{level:1})).toHaveText('数据库迁移基础课程（合成验证）');
  await expect(page.locator('.enablement-fact').filter({hasText:'预计投入'})).toContainText('未知');
  await expect(page.getByRole('heading',{name:'来源与人工核验',exact:true})).toBeVisible();
  await expect(page.locator('dt').filter({hasText:'核验人'}).locator('+ dd')).toHaveText('管理员一');
  await page.getByRole('link',{name:'返回资源中心',exact:true}).click();
  await page.getByRole('tab',{name:'实验',exact:true}).click();
  await expect(page.getByRole('link',{name:'数据库迁移演练实验（合成验证）',exact:true})).toBeVisible();
  await page.getByLabel('发布状态',{exact:true}).selectOption('unpublished');await page.getByRole('button',{name:'搜索资源',exact:true}).click();
  await expect(page.getByRole('heading',{name:'暂无符合条件的资源'})).toBeVisible();
});

test('RES-08 redirect is recorded as initiation and URL is server resolved',async({page,context,request})=>{
  await login(request,'user_a',page);
  await context.route('https://example.com/**',r=>r.fulfill({body:'Synthetic external platform; no network request sent.'}));
  await page.goto(`/enablement/resources/course/${course}?source_version=1`);
  const requestPromise=page.waitForRequest(r=>r.url().endsWith('/redirect'));
  const popupPromise=page.waitForEvent('popup');
  await page.getByRole('button',{name:'发起跳转',exact:true}).click();
  const outbound=await requestPromise;expect(outbound.postDataJSON()).toEqual({source_version:1});
  const popup=await popupPromise;await expect(popup).toHaveURL('https://example.com/course');
  await expect(page.getByRole('status')).toContainText('已记录发起跳转');
  for(const text of ['已访问','已学习','已完成'])await expect(page.locator('main').getByText(text,{exact:true})).toHaveCount(0);
  await popup.close();
});

test('PRT-01/CASE-05 partner shared case and center exchange authorized identifiers',async({page,request})=>{
  await login(request,'user_a',page);await page.goto('/partners/partner-1');
  await page.getByRole('link',{name:'制定发展方案',exact:true}).click();
  await expect(page).toHaveURL(/partner_id=partner-1/);
  await expect(page.getByText('具备制造知识库实施能力',{exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'当前可访问的证据引用',exact:true})).toBeVisible();
  await page.goto(`/enablement/resources/case/${sharedCase}?source_version=1`);
  await expect(page.getByRole('heading',{level:1})).toHaveText('伙伴迁移实践共享案例（合成验证）');
  await expect(page.locator('main')).not.toContainText('INTERNAL_SECRET_PHASE_B');
  await page.getByRole('link',{name:'验证伙伴',exact:true}).click();await expect(page).toHaveURL('/partners/partner-1');
  await page.getByRole('link',{name:'伙伴迁移实践共享案例（合成验证）',exact:true}).click();
  await page.getByRole('link',{name:'围绕此案例制定发展方案',exact:true}).click();
  await expect(page).toHaveURL(new RegExp(`case_id=${sharedCase}&case_version=1`));
  await expect(page.getByLabel('选择目标伙伴')).toHaveValue('');
  await expect(page.getByRole('link',{name:'伙伴迁移实践共享案例（合成验证）',exact:true})).toBeVisible();
  await expect(page.locator('main')).not.toContainText('INTERNAL_SECRET_PHASE_B');
});

test('MAT-01/NAV-02 project risks are context, old tasks and type filters remain real',async({page,request})=>{
  const headers=await login(request,'user_a',page);
  const before=await checked(await request.get(API+'/agent/tasks',{headers}));
  await page.goto('/tasks/task-a-ready');await page.getByRole('link',{name:'针对该项目制定发展方案',exact:true}).click();
  await expect(page.getByText('待能力发展流程复核',{exact:true})).toBeVisible();
  await expect(page.locator('main').getByText('A-ready',{exact:true})).toBeVisible();
  await expect(page.getByText('资料需复核',{exact:true})).toBeVisible();
  await expect(page.getByLabel('发展目标',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('选择目标伙伴')).toHaveValue('partner-1');
  await page.getByLabel('发展目标',{exact:true}).fill('人工整理诉求，不应创建任务');
  const after=await checked(await request.get(API+'/agent/tasks',{headers}));expect(after.total).toBe(before.total);
  await page.goto('/?task=task-a-ready');await expect(page.getByRole('link',{name:'针对该项目制定发展方案',exact:true})).toBeVisible();
  await page.goto('/tasks');await page.getByLabel('任务类型').selectOption('partner_match');await page.getByRole('button',{name:'搜索',exact:true}).click();
  await expect(page.locator('tbody').getByText('A-ready',{exact:true})).toBeVisible();
  await expect(page.locator('tbody')).not.toContainText('B-ready');
  await page.getByLabel('任务类型').selectOption('development_plan');await page.getByRole('button',{name:'搜索',exact:true}).click();
  await expect(page.locator('main').last()).not.toContainText('A-ready');
});

test('SEC user B cannot load user A context; source data clears after revocation',async({page,request})=>{
  const headers=await login(request,'user_b',page);
  expect((await request.get(API+'/enablement/context?partner_id=partner-1&task_id=task-a-ready',{headers})).status()).toBe(404);
  await page.goto('/enablement?partner_id=partner-1&task_id=task-a-ready');await expect(page.locator('main').getByRole('alert')).toBeVisible();
  await expect(page.locator('main').last()).not.toContainText('A-ready');
  await page.goto(`/enablement/resources/lab/${lab}?source_version=1`);
  await expect(page.getByRole('heading',{level:1})).toHaveText('数据库迁移演练实验（合成验证）');
  const url=API+'/admin/enablement/resources/'+lab;
  const row=await checked(await request.get(url,{headers:adminHeaders}));
  await checked(await request.post(url+'/unpublish',{headers:adminHeaders,data:{base_revision:row.revision,reason:'合成撤权验证',sensitive:true}}));
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('heading',{name:'数据库迁移演练实验（合成验证）',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'发起跳转',exact:true})).toHaveCount(0);
  await expect(page.locator('main').getByRole('alert')).toBeVisible();
});

for(const width of [1366,1920])test(`Phase B screenshots and layout ${width}`,async({page,request})=>{
  await login(request,'user_a',page);await page.setViewportSize({width,height:width===1366?768:1080});
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const directory=path.resolve('../artifacts/enablement-phase-c-regression');await mkdir(directory,{recursive:true});
  for(const [name,url,heading] of [
    ['center','/enablement','伙伴服务能力发展中心'],
    ['resources','/enablement?tab=resources','伙伴服务能力发展中心'],
    ['course',`/enablement/resources/course/${course}?source_version=1`,'数据库迁移基础课程（合成验证）'],
    ['shared-case',`/enablement/resources/case/${sharedCase}?source_version=1`,'伙伴迁移实践共享案例（合成验证）'],
    ['partner','/partners/partner-1','验证伙伴'],
    ['match','/tasks/task-a-ready','任务详情'],
    ['scenes','/scenes?category='+encodeURIComponent('能力发展'),'场景广场'],
    ['tasks','/tasks','我的任务'],
    ['project-context','/enablement?partner_id=partner-1&task_id=task-a-ready','伙伴服务能力发展中心'],
  ]){
    await page.goto(url);await expect(page.getByRole('heading',{name:heading,exact:true,level:1})).toBeVisible();
    await expect(page.getByText(/正在核验|正在读取资源|任务加载中|伙伴信息加载中/)).toHaveCount(0);
    if(name==='tasks')await expect(page.locator('tbody')).toBeVisible();
    if(name==='resources')await expect(page.getByRole('link',{name:'数据库迁移基础课程（合成验证）',exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    const nav=page.locator('aside').getByRole('link',{name:'伙伴服务能力发展中心',exact:true});await expect(nav).toBeInViewport();
    expect(await nav.evaluate(el=>{const p=el.closest('aside')!.getBoundingClientRect();const r=el.getBoundingClientRect();return r.left>=p.left&&r.right<=p.right;})).toBeTruthy();
    await page.addStyleTag({content:'nextjs-portal { display: none; }'});
    await page.screenshot({path:path.join(directory,`${name}-${width}.png`),fullPage:true});
  }
  expect(errors).toEqual([]);
});
