import {selectPartner} from './partner-select-helper';
import {fixtureLogin} from "./identity-fixture";
import {evidenceRoot} from "./evidence-path";
import {test,expect,type APIRequestContext,type Page} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
const API='http://localhost/api';
test.describe.configure({mode:'serial'});
let adminHeaders:Record<string,string>;let course:string;let lab:string;let sharedCase:string;
async function login(request:APIRequestContext,username='user_a',page?:Page){
  const response=await fixtureLogin(request, username, 'ValidationPass123');
  expect(response.ok()).toBeTruthy();const session=await response.json();
  if(page)await page.addInitScript(s=>{localStorage.setItem(`banfei:${s.user.role}:token`, s.access_token); localStorage.setItem(`banfei:${s.user.role}:user`, JSON.stringify(s.user));},session);
  if(page&&username.startsWith('admin'))await login(request,'user_a',page);
  return {Authorization:`Bearer ${session.access_token}`};
}
async function checked(response:Awaited<ReturnType<APIRequestContext['get']>>){expect(response.ok(),`Unexpected API status ${response.status()}`).toBeTruthy();return response.json();}
async function publish(request:APIRequestContext,url:string,row:{revision:number}){
  row=await checked(await request.patch(url+'/permissions',{headers:adminHeaders,data:{base_revision:row.revision,system_visible:true,model_allowed:false,partner_allowed:false,reason:'合成自动化验证授权'}}));
  return checked(await request.post(url+'/publish',{headers:adminHeaders,data:{base_revision:row.revision}}));
}
test.beforeAll(async({request})=>{
  adminHeaders=await login(request,'admin1');
  const tags=await checked(await request.get(API+'/admin/capability-tags',{headers:adminHeaders}));
  const tag=tags.find((t:{name:string})=>t.name==='数据库')||tags[0];
  for(const kind of ['course','lab']){
    const row=await checked(await request.post(API+'/admin/enablement/resources',{headers:adminHeaders,data:{base_revision:0,metadata:{resource_type:kind,title:kind==='course'?'数据库迁移基础课程（合成验证）':'数据库迁移演练实验（合成验证）',summary:'通过迁移检查、验证与复盘，理解交付过程中的关键步骤。本条为自动化合成资源。',role_ids:['role-1','role-4'],zone_ids:['zone-1','zone-2'],level:'basic',duration_minutes:60,...(kind==='course'?{course_goals:'理解迁移验证',audience:'交付工程师',outline:'准备\n核验\n复盘'}:{lab_goals:'完成迁移校验',lab_requirements:'了解数据备份'}),source_url:`https://example.com/${kind}`}}}));
    await publish(request,API+'/admin/enablement/resources/'+row.source_id,row);
    if(kind==='course')course=row.source_id;else lab=row.source_id;
  }
  const base=await checked(await request.post(API+'/cases',{headers:adminHeaders,data:{partner_id:'partner-1',title:'伙伴迁移实践共享案例（合成验证）',description:'迁移验证实践，仅包含合成内容。',category_id:'technical-2',visible:true}}));sharedCase=base.id;
});

test('NAV-01/SCN-01 center preserves navigation and offers truthful scene entries',async({page,request})=>{
  await login(request,'admin1',page);await page.goto('/enablement');
  for(const name of ['开启新任务','场景广场','伙伴画像','全部任务','个人中心','管理后台','资源中心'])await expect(page.locator('aside').getByRole('link',{name,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'开始',exact:true})).toBeVisible();
  await selectPartner(page, 'partner-1');
  await expect(page.getByText('当前伙伴画像摘要',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'生成方案',exact:true})).toHaveCount(0);
  await page.goto('/scenes?category='+encodeURIComponent('能力发展'));
  for(const name of ['制定伙伴能力发展建议','查找课程与实验','学习优秀伙伴案例'])await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
  await page.getByRole('link',{name:'查看共享案例',exact:true}).click();
  await expect(page.getByRole('tab',{name:'案例',exact:true})).toHaveAttribute('aria-selected','true');
});

test('RES-02/03 courses and labs use shared taxonomy and compact details',async({page,request})=>{
  await login(request,'user_a',page);await page.goto('/resources');
  const title='数据库迁移基础课程（合成验证）';
  for(const name of ['迁移工程师','数据库工程师']) {
    await page.getByRole('button',{name,exact:true}).click();
    await expect(page.getByRole('link',{name:title,exact:true})).toHaveCount(1);
  }
  await page.getByRole('button',{name:'按专区',exact:true}).click();
  for(const name of ['CodeArts','ModelArts']){await page.getByRole('button',{name,exact:true}).click();await expect(page.getByRole('link',{name:title,exact:true})).toHaveCount(1);}
  await page.getByRole('group',{name:'资源层级'}).getByRole('button',{name:'进阶',exact:true}).click();
  await expect(page.getByRole('heading',{name:'暂无符合条件的资源'})).toBeVisible();
  await page.getByRole('group',{name:'资源层级'}).getByRole('button',{name:'基础',exact:true}).click();
  await page.getByLabel('搜索课程或实验').fill('不存在的课程');await page.getByRole('button',{name:'搜索',exact:true}).click();
  await expect(page.getByRole('heading',{name:'暂无符合条件的资源'})).toBeVisible();
  await page.getByLabel('搜索课程或实验').fill('');await page.getByRole('button',{name:'搜索',exact:true}).click();
  const card=page.locator('.learning-card').filter({hasText:title});
  await expect(card.locator('.learning-meta')).not.toContainText('分钟');await expect(card).not.toContainText('时长待补充');await expect(card).not.toContainText('人工核验');
  await page.getByRole('link',{name:title,exact:true}).click();
  await expect(page.locator('.learning-detail-heading')).not.toContainText('分钟');
  for(const name of ['课程目标','目标学员','课程大纲'])await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'前往课程',exact:true})).toBeVisible();
  await expect(page.getByRole('tab')).toHaveCount(0);await expect(page.locator('main')).not.toContainText('费用');
  await page.getByRole('link',{name:'返回资源中心',exact:true}).click();await page.getByRole('tab',{name:'实验',exact:true}).click();
  await expect(page.locator('.learning-card').filter({hasText:'数据库迁移演练实验（合成验证）'})).toContainText('60 分钟');
  await page.getByRole('link',{name:'数据库迁移演练实验（合成验证）',exact:true}).click();
  await expect(page.locator('.learning-detail-heading')).toContainText('60 分钟');
  for(const name of ['实验目标','基本要求'])await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'前往实验',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'课程大纲',exact:true})).toHaveCount(0);
});

// A category edit changes labels, never the resource identity or its published snapshot.
test('RES-admin adds renames and orders categories with a slim resource editor',async({page,request})=>{
  await login(request,'admin1',page);await page.goto('/admin/resources');
  await page.getByText('管理岗位 / 专区分类',{exact:true}).click();
  await page.getByLabel('新分类名称',{exact:true}).fill('自动化新岗位');await page.getByRole('button',{name:'新增分类',exact:true}).click();
  const input=page.locator('.resource-category-admin tbody input[aria-label^="分类名称 "][value="自动化新岗位"]');await expect(input).toBeVisible();
  const id=await input.getAttribute('aria-label');
  const row=page.getByRole('row').filter({has:page.getByLabel(id!,{exact:true})});
  await expect(row).toBeVisible();
  await row.getByRole('textbox').fill('自动化改名岗位');await row.getByRole('spinbutton').fill('999');await row.getByRole('button',{name:'保存分类'}).click();
  await expect(page.locator('input[value="自动化改名岗位"]')).toBeVisible();
  await expect(row.getByRole('button',{name:'保存分类'})).toBeEnabled();
  await page.getByRole('button',{name:'新增资源',exact:true}).click();
  await expect(page.getByLabel('自动化改名岗位',{exact:true})).toBeVisible();
  for(const label of ['费用条件','难度','来源平台','语言','账号要求'])await expect(page.getByLabel(label,{exact:true})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'发布前人工核验'})).toHaveCount(0);
  await page.getByLabel('资源名称',{exact:true}).fill('管理员精简录入测试课程');await page.getByLabel('简介',{exact:true}).fill('只用于隔离浏览器测试');
  await page.getByLabel('自动化改名岗位',{exact:true}).check();await page.getByLabel('CodeArts',{exact:true}).check();
  await page.getByLabel('层级',{exact:true}).selectOption('advanced');
  await expect(page.getByLabel('时长（分钟）',{exact:true})).toHaveCount(0);
  await page.getByLabel('资源类型',{exact:true}).selectOption('lab');await page.getByLabel('时长（分钟）',{exact:true}).fill('30');
  await page.getByLabel('资源类型',{exact:true}).selectOption('course');await expect(page.getByLabel('时长（分钟）',{exact:true})).toHaveCount(0);
  await page.getByLabel('课程目标',{exact:true}).fill('了解分类管理');await page.getByLabel('目标学员',{exact:true}).fill('工程师');await page.getByLabel('课程大纲',{exact:true}).fill('分类与检索');
  await page.getByLabel('跳转链接',{exact:true}).fill('https://example.com/new-course');await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  await expect(page.getByRole('heading',{name:'发布管理',exact:true})).toBeVisible();
  await page.getByLabel('系统内可见',{exact:true}).check();await page.getByLabel('授权或下架原因').fill('测试授权');await page.getByRole('button',{name:'保存用途授权',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('用途授权已保存');await page.getByRole('button',{name:'发布新版本',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('已发布新的独立版本');
  await page.goto('/resources');await page.getByRole('button',{name:'自动化改名岗位',exact:true}).click();
  await expect(page.getByRole('link',{name:'管理员精简录入测试课程',exact:true})).toBeVisible();
});

test('RES-08 redirect is recorded as initiation and URL is server resolved',async({page,context,request})=>{
  await login(request,'user_a',page);
  await context.route('https://example.com/**',r=>r.fulfill({body:'Synthetic external platform; no network request sent.'}));
  await page.goto(`/enablement/resources/course/${course}?source_version=1`);
  const requestPromise=page.waitForRequest(r=>r.url().endsWith('/redirect'));
  const popupPromise=page.waitForEvent('popup');
  await page.getByRole('button',{name:'前往课程',exact:true}).click();
  const outbound=await requestPromise;expect(outbound.postDataJSON()).toEqual({source_version:1});
  const popup=await popupPromise;await expect(popup).toHaveURL('https://example.com/course');
  await expect(page.getByRole('status')).toContainText('已记录发起跳转');
  for(const text of ['已访问','已学习','已完成'])await expect(page.locator('main').getByText(text,{exact:true})).toHaveCount(0);
  await popup.close();
});

test('PRT-01/CASE-05 partner shared case and center exchange authorized identifiers',async({page,request})=>{
  await login(request,'user_a',page);await page.goto('/partners/partner-1');
  await page.getByRole('link',{name:'制定发展建议',exact:true}).click();
  await expect(page).toHaveURL(/partner_id=partner-1/);
  await expect(page.getByText('当前伙伴画像摘要',{exact:true})).toBeVisible();
  await page.getByText('当前伙伴画像摘要',{exact:true}).click();await page.getByText('查看获准引用的依据',{exact:true}).click();await expect(page.getByRole('heading',{name:'当前可访问的证据引用',exact:true})).toBeVisible();
  await page.goto(`/enablement/resources/case/${sharedCase}?source_version=1`);
  await expect(page.getByRole('heading',{level:1})).toHaveText('伙伴迁移实践共享案例（合成验证）');
  await expect(page.locator('main')).not.toContainText('INTERNAL_SECRET_PHASE_B');
  await page.getByRole('link',{name:'验证伙伴',exact:true}).click();await expect(page).toHaveURL('/partners/partner-1');
  await page.getByRole('link',{name:'伙伴迁移实践共享案例（合成验证）',exact:true}).click();
  await page.getByRole('link',{name:'围绕此案例制定发展建议',exact:true}).click();
  await expect(page).toHaveURL(new RegExp(`case_id=${sharedCase}`));
  await expect(page.getByLabel('关联已有伙伴资料（可选）',{exact:true})).toHaveAttribute('data-partner-id','partner-1');
  await expect(page.getByRole('link',{name:'伙伴迁移实践共享案例（合成验证）',exact:true})).toBeVisible();
  await expect(page.locator('main')).not.toContainText('INTERNAL_SECRET_PHASE_B');
});

test('MAT-01/NAV-02 project risks are context, old tasks and type filters remain real',async({page,request})=>{
  const headers=await login(request,'user_a',page);
  const before=await checked(await request.get(API+'/agent/tasks',{headers}));
  await page.goto('/tasks/task-a-ready');await page.getByRole('link',{name:'针对该伙伴制定发展建议',exact:true}).click();
  await expect(page.getByText('待能力发展流程复核',{exact:true})).toBeVisible();
  await expect(page.locator('main').getByText('A-ready',{exact:true})).toBeVisible();
  await expect(page.getByText('资料需复核',{exact:true})).toBeVisible();
  await expect(page.getByLabel('发展方向',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('关联已有伙伴资料（可选）',{exact:true})).toHaveAttribute('data-partner-id','partner-1');
  await page.getByLabel('发展方向',{exact:true}).fill('人工整理诉求，不应创建任务');
  const after=await checked(await request.get(API+'/agent/tasks',{headers}));expect(after.total).toBe(before.total);
  await page.goto('/?task=task-a-ready');await expect(page.getByRole('link',{name:'针对该伙伴制定发展建议',exact:true})).toBeVisible();
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
  await expect(page.getByRole('button',{name:'前往课程',exact:true})).toHaveCount(0);
  await expect(page.locator('main').getByRole('alert')).toBeVisible();
});

for(const width of [1366,1920])test(`Phase B screenshots and layout ${width}`,async({page,request})=>{
  await login(request,'user_a',page);await page.setViewportSize({width,height:width===1366?768:1080});
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const directory=path.resolve(`${evidenceRoot}/regression`);await mkdir(directory,{recursive:true});
  for(const [name,url,heading] of [
    ['center','/enablement','开启新任务'],
    ['resources','/enablement?tab=resources','资源中心'],
    ['course',`/enablement/resources/course/${course}?source_version=1`,'数据库迁移基础课程（合成验证）'],
    ['shared-case',`/enablement/resources/case/${sharedCase}?source_version=1`,'伙伴迁移实践共享案例（合成验证）'],
    ['partner','/partners/partner-1','验证伙伴'],
    ['match','/tasks/task-a-ready','任务详情'],
    ['scenes','/scenes?category='+encodeURIComponent('能力发展'),'场景广场'],
    ['tasks','/tasks','我的任务'],
    ['project-context','/enablement?partner_id=partner-1&task_id=task-a-ready','开启新任务'],
  ]){
    await page.goto(url);await expect(page.getByRole('heading',{name:heading,exact:true,level:1})).toBeVisible();
    await expect(page.getByText(/正在核验|正在读取资源|任务加载中|伙伴信息加载中/)).toHaveCount(0);
    if(name==='tasks')await expect(page.locator('tbody')).toBeVisible();
    if(name==='resources')await expect(page.getByRole('link',{name:'数据库迁移基础课程（合成验证）',exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    const nav=page.locator('aside').getByRole('link',{name:'资源中心',exact:true});await expect(nav).toBeInViewport();
    expect(await nav.evaluate(el=>{const p=el.closest('aside')!.getBoundingClientRect();const r=el.getBoundingClientRect();return r.left>=p.left&&r.right<=p.right;})).toBeTruthy();
    await page.addStyleTag({content:'nextjs-portal { display: none; }'});
    await page.screenshot({path:path.join(directory,`${name}-${width}.png`),fullPage:true});
  }
  expect(errors).toEqual([]);
});

test('RES mobile cards and detail wrap without horizontal overflow',async({page,request})=>{
  await login(request,'user_a',page);await page.setViewportSize({width:390,height:844});
  await page.goto('/resources');await expect(page.locator('.learning-card').first()).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const directory=path.resolve(`${evidenceRoot}/regression`);await mkdir(directory,{recursive:true});
  await page.screenshot({path:path.join(directory,'resources-390.png'),fullPage:true});
  await page.goto(`/resources/course/${course}?source_version=1`);await expect(page.getByRole('button',{name:'前往课程',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:path.join(directory,'course-390.png'),fullPage:true});
});
