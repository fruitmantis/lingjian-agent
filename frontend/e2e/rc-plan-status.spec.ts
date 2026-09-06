import {test,expect,type APIResponse} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import {evidenceRoot} from './evidence-path';
const API='http://127.0.0.1:8100';
async function ok(res:APIResponse){expect(res.ok(),await res.text()).toBeTruthy();return res.status()===204?null:res.json();}
for(const width of [1366,1920])test(`RC plan availability, list, sidebar and detail ${width}`,async({page,request:r})=>{
 test.setTimeout(180000);
 const session=await ok(await r.post(API+'/auth/login',{data:{username:'user_a',password:'ValidationPass123'}}));
 const headers={Authorization:`Bearer ${session.access_token}`};
 await page.addInitScript(s=>{localStorage.setItem('token',s.access_token);localStorage.setItem('user',JSON.stringify(s.user));},session);
 await page.setViewportSize({width,height:width===1366?768:1080});
 const tags=await ok(await r.get(API+'/development/capabilities',{headers}));
 const demand={target_partner_id:'partner-1',raw_demand:'仅用于 RC 状态合成验证',development_goal:`RC 状态合成验证 ${width}`,trainee_role:'交付工程师',trainee_count:3,known_baseline:'需进行人员基础评估',duration_weeks:4,hours_per_week:3,constraints:Object.fromEntries(['language','site','account','network','environment','cost','budget'].map(k=>[k,'无要求'])),accepted_assumptions:{},targets:[{capability_tag_id:tags[0].id,requirement:'独立实施',confirmed_gap:false}],model_input_allowed:true,partner_goal_allowed:true};
 const accepted=await ok(await r.post(API+'/development/plans',{headers,data:{submission_id:randomUUID(),request:demand}}));const id=accepted.plan_id;
 const detail=()=>r.get(API+'/development/plans/'+id,{headers}).then(ok);
 async function wait(status:string){await expect.poll(async()=> (await detail()).runs[0].status).toBe(status);return detail();}
 const folder=path.resolve(evidenceRoot,'rc-states');await mkdir(folder,{recursive:true});
 async function snapshot(name:string){await page.evaluate(()=>window.scrollTo(0,0));await page.addStyleTag({content:'nextjs-portal{display:none}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:path.join(folder,`${name}-${width}.png`),fullPage:true});}
 async function verify(name:string,primary:string,versions:string[],latest:string,archived=false){
  await page.goto('/tasks/'+id);
  const main=page.locator('main').getByTestId('plan-status').first();
  await expect(main.getByTestId('plan-primary')).toHaveText(primary);
  for(const v of versions)await expect(main).toContainText(v);
  await expect(main.getByTestId('plan-latest-run')).toHaveText(latest);
  const sidebar=page.locator(`aside [data-task-id="${id}"]`);
  await expect(sidebar.getByTestId('plan-primary')).toHaveText(primary);
  await expect(sidebar.getByTestId('plan-latest-run')).toHaveText(latest);
  await sidebar.scrollIntoViewIfNeeded();await expect(sidebar).toBeInViewport();
  for(const badge of [main.getByTestId('plan-primary'),sidebar.getByTestId('plan-primary')]){
   expect(await badge.evaluate(el=>{const box=el.getBoundingClientRect();const hit=document.elementFromPoint(box.x+box.width/2,box.y+box.height/2);return !!hit&&(el.contains(hit)||hit.contains(el));})).toBeTruthy();
  }
  const box=await main.boundingBox();expect(box && box.x>=0 && box.x+box.width<=width).toBeTruthy();
  await snapshot(name+'-detail-sidebar');
  await page.goto('/tasks');if(archived)await page.getByRole('button',{name:'已归档',exact:true}).click();
  await page.getByPlaceholder('搜索需求内容').fill(demand.development_goal);await page.getByRole('button',{name:'搜索',exact:true}).click();
  const row=page.locator('tbody tr').filter({hasText:demand.development_goal});
  await expect(row).toHaveCount(1);await expect(row.getByTestId('plan-primary')).toHaveText(primary);await expect(row.getByTestId('plan-latest-run')).toHaveText(latest);
  if(primary==='方案可用')await expect(row.getByTestId('plan-primary')).not.toHaveClass(/failed/);
  await snapshot(name+'-list');
 }
 let d=await wait('ready');const v1=d.plan.current_version_id;
 await verify('01-v1-draft','草稿可用',['当前草稿 V1','尚未确认'],'最近生成成功');
 // Force the selected older-task path while retaining real authenticated detail/actions.
 await page.route(/\/agent\/tasks\?/,async route=>{const response=await route.fetch();const data=await response.json();data.items=data.items.filter((x:{id:string})=>x.id!==id);await route.fulfill({response,json:data});});
 await page.goto('/tasks/'+id);await expect(page.locator(`aside .sidebar-selected-task [data-task-id="${id}"]`)).toBeVisible();
 await page.getByRole('button',{name:'确认当前版本',exact:true}).click();
 await expect(page.locator(`aside [data-task-id="${id}"]`)).toContainText('已确认 V1');
 await page.unroute(/\/agent\/tasks\?/);
 await verify('02-v1-confirmed','方案可用',['当前版本 V1','已确认 V1'],'最近生成成功');
 await ok(await r.post(API+`/development/plans/${id}/revise`,{headers,data:{submission_id:randomUUID(),based_on_version_id:v1,instruction:'C_FAIL 合成错误返回',request:demand}}));await wait('failed');
 await verify('04-failed-revise','方案可用',['当前版本 V1','已确认 V1'],'最近调整失败');
 execFileSync(path.resolve('../.venv/bin/python'),['-m','backend.tests.support.rc_interrupted_fixture',id],{cwd:path.resolve('..')});await wait('interrupted');
 await verify('05-interrupted-revise','方案可用',['当前版本 V1','已确认 V1'],'最近调整中断');
 await ok(await r.post(API+`/development/plans/${id}/revise`,{headers,data:{submission_id:randomUUID(),based_on_version_id:v1,instruction:'缩短周期',request:demand}}));d=await wait('ready');expect(d.plan.confirmed_version_id).toBe(v1);
 await verify('03-v2-draft','方案可用',['当前草稿 V2','已确认 V1'],'最近调整成功');
 await page.goto('/tasks/'+id);await page.getByRole('button',{name:'归档方案',exact:true}).click();
 await expect(page.locator(`aside [data-task-id="${id}"]`).getByTestId('plan-primary')).toHaveText('已归档');
 await verify('06-archived','已归档',['当前草稿 V2','已确认 V1'],'最近调整成功',true);
 expect((await detail()).plan.confirmed_version_id).toBe(v1);
});
