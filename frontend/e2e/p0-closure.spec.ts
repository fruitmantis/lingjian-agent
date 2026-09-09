import {randomUUID} from 'node:crypto';
import {test,expect} from '@playwright/test';
const API='http://127.0.0.1:8000';

for (const width of [1366,1920]) test(`P0 scene shortcuts, combined counts and development status ${width}`,async({page,request})=>{
  test.setTimeout(90000);
  await page.setViewportSize({width,height:width===1366?768:1080});
  const response=await request.post(API+'/auth/login',{data:{username:'admin1',password:'ValidationPass123'}});
  expect(response.ok()).toBeTruthy();const session=await response.json();
  await page.addInitScript(s=>{localStorage.setItem('token',s.access_token);localStorage.setItem('user',JSON.stringify(s.user));},session);
  const headers={Authorization:`Bearer ${session.access_token}`};
  await page.goto('/scenes');
  await page.getByLabel('搜索场景').fill('伙伴能力短板分析');
  const card=page.locator('article').filter({has:page.getByRole('heading',{name:'伙伴能力短板分析',exact:true})});
  await expect(card).not.toContainText('能力建设中');
  await card.getByRole('link',{name:'开始分析'}).click();
  await expect(page).toHaveURL('/?mode=development');
  await expect(page.getByRole('tab',{name:'能力发展',exact:true})).toHaveAttribute('aria-selected','true');
  for(const name of ['伙伴能力查询','伙伴AI画像','伙伴案例查询']){
    await page.goto('/scenes');await page.getByLabel('搜索场景').fill(name);
    const shortcut=page.locator('article').filter({has:page.getByRole('heading',{name,exact:true})});
    await expect(shortcut).toContainText('在伙伴洞察中查看');
    await shortcut.getByRole('link').click();await expect(page).toHaveURL('/partners');
  }
  const created=await request.post(API+'/development/plans',{headers,data:{submission_id:randomUUID(),request:{target_partner_id:'partner-1',development_direction:'数据库迁移能力',model_input_allowed:true}}});
  expect(created.status()).toBe(202);const accepted=await created.json();
  await expect.poll(async()=>{const r=await request.get(API+'/development/plans/'+accepted.plan_id,{headers});return (await r.json()).runs[0].status;},{timeout:20000}).toBe('ready');
  const totals=await (await request.get(API+'/admin/dashboard',{headers})).json();
  expect(totals.tasks).toBe(totals.partnerMatchTasks+totals.developmentTasks);
  expect(totals.monthTasks).toBe(totals.monthPartnerMatchTasks+totals.monthDevelopmentTasks);
  await page.goto('/admin');
  for(const [label,total,matching,development] of [['累计任务','tasks','partnerMatchTasks','developmentTasks'],['本月任务','monthTasks','monthPartnerMatchTasks','monthDevelopmentTasks']]){
    const metric=page.locator('.admin-metric-card').filter({has:page.getByText(label,{exact:true})});
    await expect(metric.locator('strong')).toHaveText(String(totals[total]));
    await expect(metric).toContainText(`项目找伙伴 ${totals[matching]} · 能力发展 ${totals[development]}`);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.goto('/admin/system');
  const status=page.locator('.ui-status-row').filter({has:page.getByText('能力发展',{exact:true})});
  await expect(status).toContainText('模型配置可用');
  await expect(status).toContainText('最近运行：生成 · 已完成');
  await expect(status).toContainText(/耗时 \d+\.\d 秒/);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
