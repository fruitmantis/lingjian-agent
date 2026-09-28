import {test, expect, type Page} from '@playwright/test';
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

import {fixture, plan, match, partner} from './coze-fixtures';

for(const [width,height] of [[1366,768],[1920,1080],[390,844]])test(`representative pages ${width}x${height}`,async({page,context})=>{
  await page.setViewportSize({width,height});const {requests,unexpected}=await fixture(page);
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  // Popups share the same network boundary, so even jump tests stay synthetic.
  await context.route('https://example.com/**',r=>r.fulfill({contentType:'text/html',body:'<h1>合成跳转目标</h1>'}));
  const phase=process.env.COZE_CAPTURE_PHASE||'after';
  const directory=path.resolve(process.env.COZE_EVIDENCE_DIR || `../artifacts/coze-ui/${phase}`);await mkdir(directory,{recursive:true});
  const measurements:unknown[]=[];
  async function capture(name:string) {
    await page.evaluate(()=>document.fonts.ready);
    await page.addStyleTag({content:'nextjs-portal{display:none}'});
    await page.evaluate(()=>window.scrollTo(0,0));
    const measure=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,width:innerWidth,sidebar:document.querySelector('aside')?.getBoundingClientRect().width,body:document.querySelector('.page-content>.page')?.getBoundingClientRect().width}));
    measurements.push({name,...measure});
    if(phase==='after')expect(measure.scrollWidth,`${name} horizontal overflow`).toBeLessThanOrEqual(width);
    await page.screenshot({path:path.join(directory,`${name}-${width}.png`),fullPage:true,mask:[page.locator('.identity-key-value'),page.locator('[data-testid="identity-key"]')]});
    await page.screenshot({path:path.join(directory,`${name}-${width}-viewport.png`),mask:[page.locator('.identity-key-value')]});
  }
  await page.goto('/');await expect(page.getByRole('tab',{name:'资源匹配',exact:true})).toHaveAttribute('aria-selected','true');
  await page.locator('#requirement').fill(match.requirement);await capture('01-new-match');
  await page.getByRole('tablist',{name:'任务模式',exact:true}).getByRole('tab',{name:'能力发展',exact:true}).click();await page.getByLabel('选择目标伙伴').selectOption(partner.id);
  await expect(page.getByText('当前伙伴画像摘要',{exact:true})).toBeVisible();
  await page.getByLabel('发展方向',{exact:true}).fill(plan.request.development_direction);await capture('02-new-development');
  await page.goto('/tasks/coze-plan');await expect(page.getByTestId('advisor-main-answer')).toContainText('先完成小范围验证');await capture('03-development-detail');
  await page.goto('/tasks/coze-match');await expect(page.getByText('风险或缺口',{exact:true})).toBeVisible();await capture('04-match-detail');
  for(const type of ['course','lab','case']) {
    await page.goto(`/resources?resource_type=${type}`);await expect(page.locator('.enablement-resource-grid article')).toHaveCount(6);await capture(`05-resources-${type}`);
  }
  await writeFile(path.join(directory,`measurements-${width}.json`),JSON.stringify(measurements,null,2));
  if(phase==='before'){expect(unexpected).toEqual([]);expect(errors).toEqual([]);return;}
  await page.goto('/?mode=development');await page.getByLabel('选择目标伙伴').selectOption(partner.id);
  await expect(page).toHaveURL(/partner_id=coze-partner/);
  await expect(page.locator('.development-profile > summary')).toBeVisible();
  await page.locator('.development-profile > summary').click();await expect(page.getByText(partner.ai_profile,{exact:true})).toBeVisible();
  await page.getByLabel('发展方向',{exact:true}).fill('优先验证系统集成');await page.getByRole('button',{name:'生成能力发展建议',exact:true}).click();
  await expect(page).toHaveURL(/\/tasks\/coze-plan$/);
  await page.getByLabel('消息',{exact:true}).fill('先验证哪些环节？');await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByTestId('conversation')).toContainText('建议先对照接口清单');
  await page.locator('.advisor-more>summary').click();await page.getByRole('button',{name:'历史版本',exact:true}).click();
  await expect(page.getByTestId('version-history')).toBeVisible();await page.getByRole('button',{name:'收起历史版本',exact:true}).click();
  await page.locator('.advisor-more>summary').click();await page.getByRole('button',{name:'运行记录',exact:true}).click();await expect(page.getByTestId('run-records')).toBeVisible();
  await page.goto('/resources');await page.getByRole('button',{name:'按专区',exact:true}).click();await page.getByRole('button',{name:'人工智能',exact:true}).click();await page.getByRole('button',{name:'进阶',exact:true}).click();
  await page.getByLabel('搜索课程或实验').fill('Agent');await page.getByRole('button',{name:'搜索',exact:true}).click();
  await expect.poll(()=>requests.some(r=>r.path.includes('zone_id=zone-1')&&r.path.includes('level=advanced')&&r.path.includes('q=Agent'))).toBeTruthy();
  await page.locator('.learning-card h2 a').first().click();await expect(page.getByRole('heading',{name:'课程目标',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'前往课程',exact:true}).click();await expect(page.getByRole('status')).toContainText('已记录发起跳转');
  await page.goto('/resources?resource_type=case');await page.getByLabel('一级分类',{exact:true}).selectOption({index:1});await page.getByLabel('二级分类',{exact:true}).selectOption({index:1});
  await page.locator('.enablement-resource-card h2 a').first().click();await expect(page.getByRole('heading',{name:'案例文件',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'围绕此案例制定发展建议',exact:true}).click();await expect(page).toHaveURL(/mode=development.*case_id=case-0/);
  await page.goto('/');await page.locator('#requirement').fill(match.requirement);await page.getByRole('button',{name:'开始匹配',exact:true}).click();
  await expect.poll(()=>requests.some(r=>r.path==='/agent/tasks'&&r.method==='POST')).toBeTruthy();
  const creation=requests.find(r=>r.path==='/development/plans'&&r.method==='POST')!;
  expect(creation.body.request.target_partner_id).toBe(partner.id);
  expect(creation.body.request.development_direction).toBe('优先验证系统集成');
  expect(requests.find(r=>r.path.endsWith('/conversation'))!.body.based_on_version_id).toBe('v1');
  await page.goto('/');await page.locator('.home-scene-disclosure > summary').focus();await page.keyboard.press('Enter');
  await expect(page.getByRole('tablist',{name:'推荐场景分类',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'换一批',exact:true}).click();
  if(width===390) {
    const toggle=page.getByRole('button',{name:'展开导航',exact:true});await toggle.click();
    await expect(page.locator('aside').getByRole('link',{name:'个人中心',exact:true})).toBeVisible();
    await page.locator('aside').getByRole('link',{name:'资源中心',exact:true}).click();
    await expect(page.getByRole('button',{name:'展开导航',exact:true})).toHaveAttribute('aria-expanded','false');
  }
  await page.goto('/resources');await page.emulateMedia({reducedMotion:'reduce'});
  const first=page.locator('.learning-card').first();await page.keyboard.press('Tab');await first.locator('h2 a').focus();await expect(first).toHaveCSS('outline-style','solid');
  await first.hover();await expect(first).toHaveCSS('transform','none');
  expect(unexpected).toEqual([]);expect(errors).toEqual([]);
});
