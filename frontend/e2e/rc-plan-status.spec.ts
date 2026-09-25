import {fixtureLogin} from "./identity-fixture";
import {test,expect,type APIResponse} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import {evidenceRoot} from './evidence-path';
const API='http://localhost:8000';
async function ok(res:APIResponse){expect(res.ok(),await res.text()).toBeTruthy();return res.status()===204?null:res.json();}
for(const width of [1366,1920])test(`RC plan availability, list, sidebar and detail ${width}`,async({page,request:r})=>{
 test.setTimeout(180000);
 const session=await ok(await fixtureLogin(r, 'user_a', 'ValidationPass123'));
 const headers={Authorization:`Bearer ${session.access_token}`};
 await page.addInitScript(s=>{localStorage.setItem(`banfei:${s.user.role}:token`, s.access_token); localStorage.setItem(`banfei:${s.user.role}:user`, JSON.stringify(s.user));},session);
 await page.setViewportSize({width,height:width===1366?768:1080});
 const tags=await ok(await r.get(API+'/development/capabilities',{headers}));
 const demand={target_partner_id:'partner-1',raw_demand:'仅用于 RC 状态合成验证',development_goal:`RC 状态合成验证 ${width}`,trainee_role:'交付工程师',trainee_count:3,known_baseline:'需进行人员基础评估',duration_weeks:4,hours_per_week:3,constraints:Object.fromEntries(['language','site','account','network','environment','cost','budget'].map(k=>[k,'无要求'])),accepted_assumptions:{},targets:[{capability_tag_id:tags[0].id,requirement:'独立实施',confirmed_gap:false}],model_input_allowed:true,partner_goal_allowed:true};
 const accepted=await ok(await r.post(API+'/development/plans',{headers,data:{submission_id:randomUUID(),request:demand}}));const id=accepted.plan_id;
 const detail=()=>r.get(API+'/development/plans/'+id,{headers}).then(ok);
 async function wait(status:string){await expect.poll(async()=> (await detail()).runs[0].status).toBe(status);return detail();}
 const folder=path.resolve(evidenceRoot,'rc-states');await mkdir(folder,{recursive:true});
 async function snapshot(name:string){expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();}

 async function verify(name:string,primary:string,version:number,archived=false){
  await page.goto('/tasks/'+id);
  await page.getByText('更多',{exact:true}).click();
  await expect(page.getByRole('button',{name:'设为当前采用版本',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'历史版本',exact:true}).click();
  const history=page.getByTestId('version-history');
  await expect(history.getByTestId('plan-primary')).toHaveText(primary);
  await expect(history).toContainText(`V${version} · 当前版本`);
  await expect(page.locator('main')).not.toContainText(/草稿|尚未确认|当前采用|已采用版本/);
  const sidebar=page.locator(`aside [data-task-id="${id}"]`);
  await expect(sidebar.getByTestId('plan-primary')).toHaveText(primary);
  await expect(sidebar.getByTestId('plan-latest-run')).toHaveCount(0);
  await snapshot(name+'-detail');
  const listResponse=(status:string)=>page.waitForResponse(response=>{const url=new URL(response.url());return url.pathname==='/agent/tasks'&&url.searchParams.get('pageSize')==='20'&&url.searchParams.get('status')===status&&response.ok();});
  await Promise.all([listResponse('active'),page.goto('/tasks')]);
  await expect(page.getByText('加载中...', {exact:true})).toHaveCount(0);
  if(archived){await Promise.all([listResponse('archived'),page.getByRole('button',{name:'已归档',exact:true}).click()]);await expect(page.getByText('加载中...', {exact:true})).toHaveCount(0);}
  await page.getByRole('combobox',{name:'任务类型'}).selectOption('development_plan');
  await page.getByRole('button',{name:'搜索',exact:true}).click();
  const row=page.locator('tr').filter({hasText:demand.development_goal});
  await expect(row).toHaveCount(1);await expect(row.getByTestId('plan-primary')).toHaveText(primary);
  await expect(row.getByTestId('plan-latest-run')).toHaveCount(0);
  await expect(row.locator('.task-failure-control')).toHaveCount(0);
  if(primary==='已生成')await expect(row.getByTestId('plan-primary')).not.toHaveClass(/failed/);
  await snapshot(name+'-list');
 }
 let d=await wait('ready');const v1=d.plan.current_version_id;
 expect(d.plan).not.toHaveProperty('confirmed_version_id');
 await verify('01-v1-current','已生成',1);
 // Selected older tasks use the same current-only status as the full list.
 await page.route(/\/agent\/tasks\?/,async route=>{const response=await route.fetch();const data=await response.json();data.items=data.items.filter((x:{id:string})=>x.id!==id);await route.fulfill({response,json:data});});
 await page.goto('/tasks/'+id);await expect(page.locator(`aside .sidebar-selected-task [data-task-id="${id}"]`)).toBeVisible();
 await expect(page.locator(`aside [data-task-id="${id}"]`).getByTestId('plan-primary')).toHaveText('已生成');
 await page.unroute(/\/agent\/tasks\?/);
 await ok(await r.post(API+`/development/plans/${id}/revise`,{headers,data:{submission_id:randomUUID(),based_on_version_id:v1,instruction:'C_FAIL 合成错误返回',request:demand}}));await wait('failed');
 expect((await detail()).plan.current_version_id).toBe(v1);
 await verify('02-failed-revise','已生成',1);
 execFileSync(path.resolve('../.venv/bin/python'),['-m','backend.tests.support.rc_interrupted_fixture',id],{cwd:path.resolve('..')});await wait('interrupted');
 await verify('03-interrupted-revise','已生成',1);
 await ok(await r.post(API+`/development/plans/${id}/revise`,{headers,data:{submission_id:randomUUID(),based_on_version_id:v1,instruction:'缩短周期',request:demand}}));d=await wait('ready');
 expect(d.plan.current_version_id).not.toBe(v1);expect(d.versions).toHaveLength(2);
 await verify('04-v2-current','已生成',2);
 await page.goto('/tasks/'+id);await page.getByText('更多',{exact:true}).click();await page.getByRole('button',{name:'归档方案',exact:true}).click();
 await expect(page.locator(`aside [data-task-id="${id}"]`).getByTestId('plan-primary')).toHaveText('已归档');
 await verify('05-archived','已归档',2,true);
 expect((await detail()).plan.current_version_id).toBe(d.plan.current_version_id);
});
