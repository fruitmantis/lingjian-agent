import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {fixtureLogin} from './identity-fixture';

// HTTP/DB/UI integration uses the explicitly enabled replay server. Classification
// stability against the live configured model is checked separately by the bounded smoke.
const API='http://localhost:8000';
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

for(const mode of ['match','development'] as const)test(`${mode} repeated off-topic submissions stop before task creation`,async({page,request})=>{
 test.setTimeout(90_000);
 const {total,errors}=await setup(page,request);const before=await total(),diagnostics=await errors();
 await page.goto(mode==='match'?'/':'/?mode=development');
 if(mode==='development')await page.getByLabel('选择目标伙伴').selectOption('partner-1');
 for(const text of offTopic)for(let repeat=0;repeat<3;repeat++){
  const endpoint=mode==='match'?'/agent/tasks':'/development/plans';
  await (mode==='match'?page.locator('#requirement'):page.getByLabel('发展方向',{exact:true})).fill(text);
  const response=page.waitForResponse(r=>r.url()===API+endpoint&&r.request().method()==='POST');
  await page.getByRole('button',{name:mode==='match'?'开始匹配':'生成能力发展建议',exact:true}).click();
  expect((await response).status()).toBe(422);
  await expect(page.getByText(messages[mode],{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'核对任务'})).toHaveCount(0);
 }
 expect(await total()).toBe(before);expect(await errors()).toEqual(diagnostics);
 await page.reload();await expect(page.getByRole('button',{name:'核对任务'})).toHaveCount(0);
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
 await expect(page.getByTestId('advisor-status')).toHaveText('建议可用');
 const after=await detail();expect(after.versions).toEqual(before.versions);expect(after.runs).toEqual(before.runs);
 expect(after.conversation).toEqual(before.conversation);expect(await errors()).toEqual(diagnostics);
});

test('known gate failure displays system message without an unconfirmed task',async({page,request})=>{
 await setup(page,request);
 await page.route(API+'/agent/tasks',route=>route.fulfill({status:502,json:{detail:'服务异常，请联系管理员。',submissionAccepted:false}}));
 await page.goto('/');await page.locator('#requirement').fill('寻找数据库伙伴');
 await page.getByRole('button',{name:'开始匹配',exact:true}).click();
 await expect(page.getByText('服务异常，请联系管理员。',{exact:true})).toBeVisible();
 await expect(page.getByText('暂未确认结果，请刷新查看。',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'核对任务'})).toHaveCount(0);
});
