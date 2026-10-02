import {selectPartner} from './partner-select-helper';
import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {fixtureLogin} from './identity-fixture';

// HTTP/DB/UI integration uses the explicitly enabled replay server. Classification
// stability against the live configured model is checked separately by the bounded smoke.
const API='http://localhost/api';
const offTopic=['明天天气怎么样？','帮我安排三天旅游行程','写一个 Python 快速排序函数','写一首关于月亮的诗'];
const messages={match:'这里仅支持伙伴选择与推荐，请描述项目需求或询问相关推荐结果。',development:'这里仅支持伙伴能力发展建议，请描述发展方向或询问相关方案。'};
async function setup(page:Page,request:APIRequestContext){
 const user=await (await fixtureLogin(request,'user_a')).json();
 const admin=await (await fixtureLogin(request,'admin1')).json();
 await page.addInitScript(s=>{localStorage.setItem('banfei:user:token',s.access_token);localStorage.setItem('banfei:user:user',JSON.stringify(s.user));},user);
 const headers={Authorization:`Bearer ${user.access_token}`};
 const errors=async()=> (await (await request.get(API+'/admin/system/errors',{headers:{Authorization:`Bearer ${admin.access_token}`}})).json()).items;
 const total=async()=> (await (await request.get(API+'/agent/tasks',{headers})).json()).total;
 return {headers,errors,total};
}

for(const mode of ['match','development'] as const)test(`${mode} off-topic submissions persist before understanding and finish without business output`,async({page,request})=>{
 test.setTimeout(90000);
 const {headers,total,errors}=await setup(page,request);const before=await total(),diagnostics=await errors();
 for(const text of offTopic){
  await page.goto(mode==='match'?'/':'/?mode=development');
  await (mode==='match'?page.locator('#requirement'):page.getByLabel('发展方向',{exact:true})).fill(text);
  const endpoint=mode==='match'?'/agent/tasks':'/development/plans';
  const response=page.waitForResponse(r=>r.url()===API+endpoint&&r.request().method()==='POST');
  await page.getByRole('button',{name:'开始',exact:true}).click();const accepted=await response;
  expect(accepted.status()).toBe(202);const body=await accepted.json(),id=body.recordId||body.plan_id;
  await expect(page).toHaveURL(`/tasks/${id}`);await expect(page.getByText(messages[mode],{exact:true})).toBeVisible();
  const detail=await(await request.get(API+endpoint+'/'+id,{headers})).json();
  if(mode==='development'){expect(detail.versions).toHaveLength(0);expect(detail.payload).toBeNull();expect(detail.runs[0].status).toBe('ready');}
  else {expect(detail.recommendations).toHaveLength(0);expect(detail.taskStatus).toBe('ready');}
  await expect(page.getByRole('button',{name:'核对任务'})).toHaveCount(0);
 }
 expect(await total()).toBe(before+offTopic.length);expect(await errors()).toEqual(diagnostics);
});

test('out-of-scope follow-up keeps available advice and creates no new version',async({page,request})=>{
 const {headers,errors}=await setup(page,request);
 const submitted=await request.post(API+'/development/plans',{headers,data:{submission_id:randomUUID(),request:{target_partner_id:'partner-1',development_direction:'伙伴数据库迁移交付能力发展'}}});
 expect(submitted.status()).toBe(202);const {plan_id:id}=await submitted.json();
 const detail=async()=> (await (await request.get(API+'/development/plans/'+id,{headers})).json());
 await expect.poll(async()=>(await detail()).runs[0].status).toBe('ready');
 const before=await detail(),diagnostics=await errors();await page.goto('/tasks/'+id);
 await page.getByLabel('消息',{exact:true}).fill(offTopic[0]);
 await page.getByRole('button',{name:'发送',exact:true}).click();
 await expect(page.getByText(messages.development,{exact:true})).toBeVisible();
 await expect(page.getByTestId('advisor-status')).toHaveText('处理完成');await expect(page.getByTestId('advisor-main-answer')).toBeVisible();
 const after=await detail();expect(after.versions).toEqual(before.versions);expect(after.payload).toEqual(before.payload);expect(after.runs).toHaveLength(before.runs.length+1);expect(after.runs[0].status).toBe('ready');
 expect(after.conversation).toEqual(before.conversation);expect(await errors()).toEqual(diagnostics);
});

test('known gate failure displays system message without an unconfirmed task',async({page,request})=>{
 await setup(page,request);
 await page.route(API+'/agent/tasks',route=>route.fulfill({status:502,json:{detail:'服务异常，请联系管理员。',submissionAccepted:false}}));
 await page.goto('/');await page.locator('#requirement').fill('寻找数据库伙伴');
 await page.getByRole('button',{name:'开始',exact:true}).click();
 await expect(page.getByText('服务异常，请联系管理员。',{exact:true})).toBeVisible();
 await expect(page.getByText('暂未确认结果，请刷新查看。',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'核对任务'})).toHaveCount(0);
});
