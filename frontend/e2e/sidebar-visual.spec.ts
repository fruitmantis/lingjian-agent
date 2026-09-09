import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';

for(const width of [1366,1920])test(`task history typography and status hierarchy ${width}`,async({page})=>{
  await page.setViewportSize({width,height:width===1366?768:1080});
  await page.addInitScript(()=>localStorage.setItem('token','synthetic-browser-only'));
  const presentation={state:'available',current_version:1,confirmed_version:1,current_is_confirmed:true,current_available:true,confirmed_available:true,latest_run_status:'failed',latest_run_type:'revise'};
  const records=Array.from({length:10},(_,index)=>({id:`history-${index}`,requirement:index===1?'合成伙伴 · Agent 应用交付':`华北某医院数据库迁移项目伙伴需求 ${index}`,createdAt:new Date(Date.UTC(2026,8,8-index,10)).toISOString(),taskStatus:index===1?'failed':index===2?'partial':'ready',task_type:index===1?'development_plan':'partner_match',planPresentation:index===1?presentation:null,archivedAt:null,recommendations:[],opportunity:null}));
  let writes=0;const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route(/https?:\/\/(127\.0\.0\.1|localhost):8000\//,route=>{
    if(route.request().method()!=='GET'){writes++;return route.abort();}
    const p=new URL(route.request().url()).pathname;
    if(p==='/auth/me')return route.fulfill({json:{id:'visual-user',username:'visual-user',role:'admin',status:'active',must_change_password:false}});
    if(p==='/agent/tasks')return route.fulfill({json:{items:records,total:records.length,page:1,pageSize:10,totalPages:1}});
    if(p.startsWith('/agent/tasks/'))return route.fulfill({json:records.find(x=>x.id===p.split('/').pop())});
    return route.fulfill({json:[]});
  });
  await page.goto('/tasks/history-0');
  const list=page.locator('.sidebar-task-list'),selected=list.locator('[data-task-id="history-0"]'),plan=list.locator('[data-task-id="history-1"]');
  await expect(list.locator('a.sidebar-task-item')).toHaveCount(10);
  await expect(selected).toHaveAttribute('aria-current','page');
  await expect(selected.locator('strong')).toHaveCSS('font-weight','700');
  await expect(selected.locator('time')).toHaveCSS('font-weight','400');
  await expect(selected.locator('em')).toHaveCSS('font-weight','400');
  await expect(selected).toHaveCSS('border-radius','8px');
  await expect(selected).toHaveCSS('box-shadow','none');
  await expect(selected).toContainText('项目找伙伴');
  await expect(selected).toHaveAttribute('title',records[0].requirement);
  await expect(plan.getByTestId('plan-primary')).toHaveText('方案可用');
  await expect(plan).toContainText('已确认 V1');
  await expect(plan.getByTestId('plan-latest-run')).toHaveText('最近调整失败');
  await expect(plan.getByTestId('plan-primary')).not.toHaveClass(/failed/);
  await expect(plan).toContainText('能力发展');
  await expect(list.locator('[data-task-id="history-2"]')).toContainText('部分完成');
  expect(await list.evaluate(e=>e.scrollHeight>e.clientHeight)).toBeTruthy();
  await page.mouse.move(width-10,10);await page.evaluate(()=>document.fonts.ready);
  await mkdir('/tmp/sidebar-refinement',{recursive:true});
  await page.screenshot({path:`/tmp/sidebar-refinement/history-${width}.png`,fullPage:true});
  const quiet=await list.evaluate(e=>getComputedStyle(e).scrollbarColor);
  await list.hover();expect(await list.evaluate(e=>getComputedStyle(e).scrollbarColor)).not.toBe(quiet);
  presentation.latest_run_status='interrupted';
  await page.evaluate(()=>window.dispatchEvent(new Event('lingjian:tasks-changed')));
  await expect(plan.getByTestId('plan-latest-run')).toHaveText('最近调整中断');
  await expect(plan.getByTestId('plan-primary')).toHaveText('方案可用');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  expect(writes).toBe(0);expect(errors).toEqual([]);
});
