import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import {evidenceRoot} from './evidence-path';
const API='http://127.0.0.1:8000';
for(const width of [1366,1920])test(`Unified task modes, source links and shared history ${width}`,async({page,request})=>{
 test.setTimeout(90000);
 const login=await request.post(API+'/auth/login',{data:{username:'user_a',password:'ValidationPass123'}});expect(login.ok()).toBeTruthy();const session=await login.json();
 await page.addInitScript(s=>{localStorage.setItem('token',s.access_token);localStorage.setItem('user',JSON.stringify(s.user));},session);
 const headers={Authorization:`Bearer ${session.access_token}`};
 await page.setViewportSize({width,height:width===1366?768:1080});
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const dir=path.resolve(`${evidenceRoot}/unified-entry`);await mkdir(dir,{recursive:true});
 async function shot(name:string){await page.evaluate(()=>window.scrollTo(0,0));await page.addStyleTag({content:'nextjs-portal{display:none}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();const nav=page.locator('aside').getByRole('link',{name:'资源中心',exact:true});await expect(nav).toBeInViewport();await page.screenshot({path:path.join(dir,`${name}-${width}.png`),fullPage:true});}
 async function development(){await expect(page.getByRole('heading',{name:'开启新任务',exact:true})).toBeVisible();await expect(page.getByRole('tablist',{name:'任务模式',exact:true}).getByRole('tab',{name:'能力发展',exact:true})).toHaveAttribute('aria-selected','true');expect(new URL(page.url()).pathname).toBe('/');await expect(page.locator('main')).not.toContainText('伙伴服务能力发展中心');}
 await page.goto('/');
 const nav=page.locator('aside');await expect(nav.getByText('伙伴服务能力发展中心',{exact:true})).toHaveCount(0);
 const links=await nav.locator('a').allTextContents();expect(links.indexOf('场景广场')).toBeLessThan(links.indexOf('伙伴洞察'));expect(links.indexOf('伙伴洞察')).toBeLessThan(links.indexOf('资源中心'));
 await expect(page.getByRole('tab',{name:'资源匹配',exact:true})).toHaveAttribute('aria-selected','true');
 await expect(page.getByRole('button',{name:'开始匹配',exact:true})).toBeVisible();await shot('01-project-match');
 await page.getByRole('tablist',{name:'任务模式',exact:true}).getByRole('tab',{name:'能力发展',exact:true}).click();await development();
 await page.getByLabel('选择目标伙伴').selectOption('partner-1');await expect(page.getByText('具备制造知识库实施能力',{exact:true})).toBeVisible();
 await page.getByLabel('发展方向',{exact:true}).fill('希望形成企业级 Agent 应用交付能力');
 for(const name of ['人数','周期','预算','环境','人工差距确认'])await expect(page.locator('main').getByLabel(name,{exact:true})).toHaveCount(0);
 await shot('02-development');
 // Two explicit inputs create a real task, without a resource-selection prerequisite.
 const posted=page.waitForRequest(r=>r.url()===API+'/development/plans'&&r.method()==='POST');
 await page.getByRole('button',{name:'生成能力发展建议',exact:true}).click();const body=(await posted).postDataJSON();expect(body.request.target_partner_id).toBe('partner-1');expect(body.request.development_direction).toContain('Agent');expect(body.request.source_task_id).toBeNull();
 await expect(page).toHaveURL(/\/tasks\/[^/?]+$/);const id=new URL(page.url()).pathname.split('/').pop()!;
 await expect.poll(async()=>{const r=await request.get(API+'/development/plans/'+id,{headers});return (await r.json()).runs[0].status;}).toBe('ready');
 await expect(page.getByTestId('advisor-status')).toHaveText('建议可用');await expect(page.getByRole('heading',{name:'继续问伴飞',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'高级编辑',exact:true})).not.toBeVisible();await shot('06-advisor-detail');
 await page.goto('/tasks');await page.getByLabel('任务类型').selectOption('development_plan');await page.getByRole('button',{name:'搜索',exact:true}).click();await expect(page.locator(`tbody a[href="/tasks/${id}"]`)).toBeVisible();await expect(page.locator('tbody tr').first()).toContainText('能力发展');await shot('07-unified-tasks');
 await page.goto('/partners/partner-1');await page.getByRole('link',{name:'制定发展建议',exact:true}).click();await development();await expect(page.getByLabel('选择目标伙伴')).toHaveValue('partner-1');await expect(page.getByText('具备制造知识库实施能力',{exact:true})).toBeVisible();await shot('04-partner-context');
 await page.goto('/tasks/task-a-ready');await page.getByRole('link',{name:'针对该伙伴制定发展建议',exact:true}).click();await development();expect(new URL(page.url()).searchParams.get('task_id')).toBe('task-a-ready');await expect(page.getByLabel('选择目标伙伴')).toHaveValue('partner-1');await expect(page.getByTestId('source-context')).toContainText('A-ready');await expect(page.getByTestId('source-context')).toContainText('待能力发展流程复核');await expect(page.getByLabel('发展方向',{exact:true})).toHaveValue('');await shot('05-project-context');
 await nav.getByRole('link',{name:'资源中心',exact:true}).click();await expect(page).toHaveURL('/resources');await expect(page.getByLabel('选择目标伙伴')).toHaveCount(0);await expect(page.getByRole('tab',{name:'课程',exact:true})).toBeVisible();await expect(page.getByText('正在读取资源…',{exact:true})).toHaveCount(0);await shot('03-resources');
 await page.goto('/scenes?category='+encodeURIComponent('能力发展'));await page.getByRole('link',{name:'制定发展建议',exact:true}).click();await development();
 await page.goto('/scenes?category='+encodeURIComponent('能力发展'));await page.getByRole('link',{name:'查找资源',exact:true}).click();await expect(page).toHaveURL(/\/resources(?:\?|$)/);
 await page.goto('/scenes?category='+encodeURIComponent('能力发展'));await page.getByRole('link',{name:'查看共享案例',exact:true}).click();await expect(page.getByRole('tab',{name:'案例',exact:true})).toHaveAttribute('aria-selected','true');
 // Old bookmarks preserve context but can no longer render a second workspace.
 await page.goto('/enablement?partner_id=partner-1&task_id=task-a-ready');await development();expect(new URL(page.url()).searchParams.get('task_id')).toBe('task-a-ready');await expect(page.getByLabel('选择目标伙伴')).toHaveValue('partner-1');
 await page.goto('/enablement?tab=resources&resource_type=case');await expect(page).toHaveURL('/resources?resource_type=case');await expect(page.getByRole('tab',{name:'案例',exact:true})).toHaveAttribute('aria-selected','true');
 expect(errors).toEqual([]);
});

// A pending matching task remains in shared history, without stealing the mode.
test('Switching mode during matching acknowledgement preserves explicit intent',async({page,request})=>{
 const res=await request.post(API+'/auth/login',{data:{username:'user_a',password:'ValidationPass123'}});const session=await res.json();
 await page.addInitScript(s=>{localStorage.setItem('token',s.access_token);localStorage.setItem('user',JSON.stringify(s.user));},session);
 await page.route(API+'/agent/tasks',async route=>{await new Promise(r=>setTimeout(r,1200));await route.continue();});
 await page.goto('/');await page.locator('#requirement').fill('统一入口切换验证项目');
 const pending=page.waitForResponse(r=>r.url()===API+'/agent/tasks'&&r.request().method()==='POST');
 await page.getByRole('button',{name:'开始匹配',exact:true}).click();
 await page.getByRole('tablist',{name:'任务模式'}).getByRole('tab',{name:'能力发展',exact:true}).click();
 const response=await pending;expect(response.status()).toBe(202);const {recordId}=await response.json();
 await expect(page.locator(`.sidebar-task-list a[href="/tasks/${recordId}"]`)).toBeVisible();
 await expect(page.getByRole('tablist',{name:'任务模式'}).getByRole('tab',{name:'能力发展',exact:true})).toHaveAttribute('aria-selected','true');
 expect(new URL(page.url()).searchParams.get('mode')).toBe('development');
 await page.getByRole('tab',{name:'资源匹配',exact:true}).click();await page.locator('#requirement').fill('另一个项目');await expect(page.getByRole('button',{name:'开始匹配',exact:true})).toBeEnabled();
});
