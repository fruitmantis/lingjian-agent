import {evidenceRoot} from "./evidence-path";
import {test,expect,type APIRequestContext,type Page} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
const API='http://127.0.0.1:8100',CANARY='INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE';
test.describe.configure({mode:'serial'});
let admin:Record<string,string>,user:Record<string,string>,other:Record<string,string>,tag:string,caseId:string;
async function login(r:APIRequestContext,name:string,page?:Page){const res=await r.post(API+'/auth/login',{data:{username:name,password:'ValidationPass123'}});expect(res.ok()).toBeTruthy();const session=await res.json();if(page)await page.addInitScript(s=>{localStorage.setItem('token',s.access_token);localStorage.setItem('user',JSON.stringify(s.user));},session);return {Authorization:`Bearer ${session.access_token}`};}
async function ok(res:Awaited<ReturnType<APIRequestContext['get']>>){expect(res.ok(),await res.text()).toBeTruthy();return res.status()===204?null:res.json();}
async function publish(r:APIRequestContext,url:string,row:{revision:number}){row=await ok(await r.patch(url+'/permissions',{headers:admin,data:{base_revision:row.revision,system_visible:true,model_allowed:true,partner_allowed:true,reason:'Phase C 合成权限验证'}}));await ok(await r.post(url+'/review',{headers:admin,data:{base_revision:row.revision,link_status:'available',content_checked:true,authorization_checked:true}}));return ok(await r.post(url+'/publish',{headers:admin,data:{base_revision:row.revision}}));}
function demand(goal:string){return {target_partner_id:'partner-1',request_source:'partner_manager',raw_demand:'保留原始发展诉求，仅用于合成测试',development_goal:goal,trainee_role:'交付工程师',trainee_count:3,known_baseline:'具备基础操作经验，尚需实操评估',duration_weeks:4,hours_per_week:3,constraints:Object.fromEntries(['language','site','account','network','environment','cost','budget'].map(k=>[k,'无要求'])),accepted_assumptions:{},targets:[{capability_tag_id:tag,requirement:'能够完成数据迁移验证',confirmed_gap:false,confirmation_note:''}],model_input_allowed:true,partner_goal_allowed:true};}
async function ready(r:APIRequestContext,id:string){await expect.poll(async()=>{const d=await ok(await r.get(API+'/development/plans/'+id,{headers:user}));return d.runs[0].status;},{timeout:30000}).toBe('ready');return ok(await r.get(API+'/development/plans/'+id,{headers:user}));}
async function snap(page:Page,name:string,width:number){await page.evaluate(()=>window.scrollTo(0,0));await page.addStyleTag({content:'nextjs-portal {display:none}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await expect(page.locator('aside').getByRole('link',{name:'伙伴服务能力发展中心',exact:true})).toBeInViewport();await page.screenshot({path:path.resolve(`${evidenceRoot}/${name}-${width}.png`),fullPage:true});}

test.beforeAll(async({request:r})=>{admin=await login(r,'admin1');user=await login(r,'user_a');other=await login(r,'user_b');await mkdir(path.resolve(evidenceRoot),{recursive:true});const tags=await ok(await r.get(API+'/development/capabilities',{headers:user}));tag=tags.find((t:{name:string})=>t.name==='数据库').id;
 for(const kind of ['course','lab']){const row=await ok(await r.post(API+'/admin/enablement/resources',{headers:admin,data:{base_revision:0,metadata:{resource_type:kind,title:`Phase C ${kind==='course'?'课程':'实验'}（合成验证）`,summary:'经过授权的合成学习内容',target_capability:'数据迁移',audience:'交付工程师',source_platform:'合成平台',source_url:`https://example.com/phase-c-${kind}`,capability_tag_ids:[tag]}}}));await publish(r,API+'/admin/enablement/resources/'+row.source_id,row);}
 const c=await ok(await r.post(API+'/cases',{headers:admin,data:{partner_id:'partner-1',title:'Phase C 内部证据',description:CANARY}}));caseId=c.id;const url=API+`/admin/cases/${caseId}/sharing`;const row=await ok(await r.put(url,{headers:admin,data:{base_revision:0,metadata:{title:'Phase C 共享学习案例（合成验证）',summary:'仅外发脱敏后的实践总结',methods:'核验、实施与复盘',contributor_role:'实施验证',source_platform:'合成平台',source_url:'https://example.com/phase-c-case',capability_tag_ids:[tag]}}}));await publish(r,url,row);
});

for(const width of [1366,1920])test(`DEV lifecycle browser and fourteen evidence states ${width}`,async({page,request:r})=>{
 test.setTimeout(180000);await login(r,'user_a',page);await page.setViewportSize({width,height:width===1366?768:1080});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/enablement?partner_id=partner-1');await expect(page.getByRole('button',{name:'生成发展方案',exact:true})).toBeVisible();await page.getByRole('button',{name:'生成发展方案',exact:true}).click();await expect(page.getByTestId('clarification')).toBeVisible();await page.getByLabel('按明确填写的假设继续').check();await snap(page,'02-clarification',width);
 for(const [name,value] of [['原始诉求','保留原始发展诉求'],['发展目标',`C_SLOW 数据迁移能力发展 ${width}`],['参训岗位','交付工程师'],['人员已知基础','具备基础操作经验，尚需实操评估'],['参训人数','3'],['周期（周）','4'],['每周投入（小时）','3']])await page.getByLabel(name,{exact:true}).fill(value);
 await page.getByLabel('添加目标能力').selectOption(tag);await page.getByLabel('本次目标要求',{exact:true}).fill('能够完成数据迁移验证');
 for(const label of ['语言','站点','账号条件','网络条件','实验环境','费用要求','预算'])await page.getByLabel(label,{exact:true}).fill('无要求');
 await page.getByLabel('允许将填写的发展目标',{exact:false}).check();await page.getByLabel('允许在伙伴可传递视图',{exact:false}).check();await snap(page,'01-request-form',width);
 const acceptedPromise=page.waitForResponse(res=>res.url()===API+'/development/plans'&&res.request().method()==='POST');await page.getByRole('button',{name:'生成发展方案',exact:true}).click();const accepted=await (await acceptedPromise).json();const id=accepted.plan_id;await expect(page).toHaveURL(`/tasks/${id}`);await expect(page.getByText('发展方案生成中',{exact:false})).toBeVisible();await snap(page,'03-generating',width);
 let d=await ready(r,id);await expect(page.getByTestId('stages')).toBeVisible();const v1=d.plan.current_version_id;await snap(page,'04-v1-draft',width);
 await page.getByRole('button',{name:'确认当前版本',exact:true}).click();await expect.poll(async()=> (await ok(await r.get(API+'/development/plans/'+id,{headers:user}))).plan.confirmed_version_id).toBe(v1);await page.reload();await expect(page.getByText('已确认版本：',{exact:false}).first()).toContainText('V1');await snap(page,'05-v1-confirmed',width);
 await page.getByRole('button',{name:'对话调整',exact:true}).click();await page.getByLabel('调整指令',{exact:true}).fill('缩短到三周并保留目标');await page.getByLabel('周期（周）',{exact:true}).fill('3');await page.getByRole('button',{name:'提交调整并生成新草稿',exact:true}).click();d=await ready(r,id);await expect.poll(async()=> (await ok(await r.get(API+'/development/plans/'+id,{headers:user}))).versions.length).toBe(2);d=await ready(r,id);expect(d.plan.confirmed_version_id).toBe(v1);await page.reload();await expect(page.getByTestId('diagnoses')).toBeVisible();await snap(page,'06-v2-draft-v1-confirmed',width);await page.getByTestId('diagnoses').scrollIntoViewIfNeeded();await snap(page,'07-diagnosis',width);await page.getByTestId('stages').scrollIntoViewIfNeeded();await snap(page,'08-stages',width);
 await page.getByRole('button',{name:'结构化编辑',exact:true}).click();await expect(page.getByTestId('structured-edit')).toBeVisible();await page.getByLabel('阶段标题',{exact:true}).fill('先修准备与实践');await snap(page,'10-structured-edit',width);const base=d.plan.current_version_id;
 // Another session saves while this browser still holds its editing baseline.
 const clean=d.payload.stages.map((s:{title:string;items:Record<string,unknown>[]})=>({title:s.title,items:s.items.map(i=>Object.fromEntries(['source_type','source_id','source_version','capability_tag_id','reason','estimated_hours','note'].map(k=>[k,i[k]])))}));
 await ok(await r.post(API+`/development/plans/${id}/edit`,{headers:user,data:{based_on_version_id:base,stages:clean}}));await page.getByRole('button',{name:'保存新草稿',exact:true}).click();await expect(page.locator('main').getByRole('alert')).toContainText('版本冲突');await snap(page,'14-conflict-old-version',width);await page.getByRole('button',{name:'取消编辑',exact:true}).click();
 await page.getByRole('button',{name:'伙伴可传递视图预览',exact:true}).click();await expect(page.getByTestId('transfer-preview')).toBeVisible();expect(await page.getByTestId('transfer-preview').innerText()).not.toContain(CANARY);await snap(page,'11-transferable',width);
 const transfer=await ok(await r.post(API+`/development/plans/${id}/copy`,{headers:user,data:{version_id:v1}}));expect(transfer.text).not.toContain(CANARY);expect(transfer.text).not.toContain(id);
 for(const suffix of ['', '/transferable','/candidates'])expect((await r.get(API+`/development/plans/${id}${suffix}`,{headers:other})).status()).toBe(404);
 await page.goto('/tasks');await page.getByLabel('任务类型').selectOption('development_plan');await page.getByRole('button',{name:'搜索',exact:true}).click();await expect(page.locator('tbody')).toContainText(`C_SLOW 数据迁移能力发展 ${width}`);await snap(page,'12-unified-tasks',width);
 const gap=await ok(await r.post(API+'/development/plans',{headers:user,data:{submission_id:randomUUID(),request:demand(`C_GAP 资源缺口 ${width}`)}}));await ready(r,gap.plan_id);await page.goto('/tasks/'+gap.plan_id);await expect(page.getByTestId('gaps')).toContainText('当前资源库未找到匹配项');await snap(page,'09-resource-gap',width);
 // A failed OpenAI-compatible revision keeps current and confirmed pointers intact.
 const prior=await ok(await r.get(API+'/development/plans/'+id,{headers:user}));
 await ok(await r.post(API+`/development/plans/${id}/revise`,{headers:user,data:{submission_id:randomUUID(),based_on_version_id:prior.plan.current_version_id,instruction:'C_FAIL 错误模型响应验证',request:prior.request}}));
 await expect.poll(async()=> (await ok(await r.get(API+'/development/plans/'+id,{headers:user}))).runs[0].status).toBe('failed');
 const failed=await ok(await r.get(API+'/development/plans/'+id,{headers:user}));expect(failed.plan.current_version_id).toBe(prior.plan.current_version_id);expect(failed.plan.confirmed_version_id).toBe(v1);
 await page.goto('/tasks/'+id);await expect(page.locator('main').getByText('本次处理未完成',{exact:false})).toBeVisible();await expect(page.getByTestId('stages')).toBeVisible();await snap(page,'15-failed-revision-old-version',width);
 // Revoke a case only after both viewport plans have been exercised; re-publish for the next viewport.
 const url=API+`/admin/cases/${caseId}/sharing`;let row=await ok(await r.get(url,{headers:admin}));await ok(await r.post(url+'/unpublish',{headers:admin,data:{base_revision:row.revision,reason:'合成敏感撤权验证',sensitive:true}}));
 await page.goto('/tasks/'+id);await expect(page.locator('main').getByText('来源授权已变化',{exact:false})).toBeVisible();await expect(page.getByTestId('stages')).toHaveCount(0);expect((await r.post(API+`/development/plans/${id}/copy`,{headers:user,data:{version_id:v1}})).status()).toBe(409);await snap(page,'13-revoked-history',width);
 row=await ok(await r.get(url,{headers:admin}));await publish(r,url,row);expect(errors).toEqual([]);
});


test('NFR-01 real HTTP creation P95 returns before mock generation',async({request:r})=>{
 test.setTimeout(90000);const owner=await login(r,'admin2');const durations:number[]=[];
 for(let n=0;n<20;n++){
  const started=performance.now();const accepted=await ok(await r.post(API+'/development/plans',{headers:owner,data:{submission_id:randomUUID(),request:demand(`接口时延合成验证 ${n}`)}}));durations.push(performance.now()-started);
  await expect.poll(async()=> (await ok(await r.get(API+'/development/plans/'+accepted.plan_id,{headers:owner}))).runs[0].status).toBe('ready');
  await ok(await r.patch(API+'/agent/tasks/'+accepted.plan_id+'/archive',{headers:owner}));
 }
 const p95=[...durations].sort((a,b)=>a-b)[18];expect(p95).toBeLessThan(1000);
 await writeFile(path.resolve(`${evidenceRoot}/http-creation-latency.json`),JSON.stringify({sample_count:20,p50_ms:[...durations].sort((a,b)=>a-b)[9],p95_ms:p95,max_ms:Math.max(...durations),environment:'HTTP 8100, SQLite /tmp, loopback OpenAI-compatible mock, serial submissions',real_model_calls:0},null,2));
});
