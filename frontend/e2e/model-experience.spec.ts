import {test,expect,type Page} from '@playwright/test';
import {mockDeviceSession} from './device-session-fixture';
const raw='  企业知识库项目，希望找到实施伙伴。\n保留原文与交付约束。  ';
const names:Record<string,string>={a:'合成模型A',b:'合成模型B',c:'合成模型C'};
async function fixture(page:Page,admin=false,shared=false,grouped=false){
 const user={id:admin?'admin-model-qa':'user-model-qa',username:'model-qa',display_name:'合成测试用户',role:admin?'admin':'user',status:'active',must_change_password:false};
 await page.addInitScript(({user,admin})=>{localStorage.setItem(`banfei:${admin?'admin':'user'}:token`,'synthetic-model-token');localStorage.setItem(`banfei:${admin?'admin':'user'}:user`,JSON.stringify(user));},{user,admin});
 const state={posts:[] as Array<{path:string;body:any}>,records:new Map<string,any>(),removed:false,lose:false,followups:[] as any[],modelError:'timeout',partial:false,tests:0,saves:[] as any[],providerSaves:[] as any[],testPass:false,errors:[] as string[]};
 const stamp=new Date().toISOString();
 const configs=['a','b','c'].map((id,i)=>({id,name:names[id],providerId:'provider-'+(shared&&id==='b'?'a':id),providerName:names[id],modelName:'synthetic-'+id,temperature:0.2,topP:0.8,maxTokens:2048,enabled:true,userSelectable:true,apiKeyConfigured:true,apiKeySource:'db',defaultBindings:id==='a'?['partner_match']:id==='c'?['partner_development']:[],updatedAt:stamp}));
 const providers=['a','b','c'].map(id=>({id:'provider-'+id,name:names[id],baseUrl:'https://synthetic.invalid/v1',protocol:'openai_chat_completions',apiKeyConfigured:true,apiKeySource:'db',modelCount:1,updatedAt:stamp}));
 const opts={modelConfigId:'a',thinking:true,timeoutSeconds:300,timeoutRetries:3};const settings={agents:{partner_match:{...opts,name:'伙伴推荐',description:'根据项目需求寻找伙伴。',icon:'users',enabled:true},partner_development:{...opts,modelConfigId:'c',name:'伙伴发展',description:'提供发展建议。',icon:'trend',enabled:true}},processing:{...opts}};
 const fail=()=>[{stage:state.partial?'persistence':'understanding',stageLabel:state.partial?'结果保存':'需求理解',code:state.partial?'persistence':state.modelError,message:'untrusted raw error must not display',action:'',modelRelated:!state.partial}];
 const summary=(id:string,record:any)=>({id,task_type:record?.kind==='development'?'development_plan':'partner_match',requirement:record?.text||raw,createdAt:stamp,taskStatus:'failed',archivedAt:null});
 const plan=(id:string)=>{const record=state.records.get(id),existing=id==='existing-plan',follow=state.followups.at(-1),failed=existing?!!follow:true;return {plan:{id,current_version_id:existing?'version-current':null,status:'active',active_run_id:null},presentation:{state:existing?'available':'generation_failed',current_available:existing,latest_run_status:failed?'failed':'ready',latest_run_type:existing?'revise':'generate'},partner_name:'合成伙伴',request:record?.body.request||{raw_demand:'原发展目标'},executionInput:existing?(follow?.message||'原发展目标'):record?.text,failedInput:existing?follow?.message:null,modelSelection:{id:existing?(follow?.modelConfigId||'a'):record?.body.modelConfigId,name:names[existing?(follow?.modelConfigId||'a'):record?.body.modelConfigId]},progress:null,analysis:null,payload:existing?{answer:'原有效方案保持不变。',overview:{},stages:[],resource_gaps:[]}:null,versions:existing?[{id:'version-current',version_no:1}]:[],conversation:[],runs:[{id:existing?'followup-'+state.followups.length:'run-create',submission_id:follow?.submission_id||record?.body.submission_id||'original-run',run_type:existing?'revise':'generate',status:failed?'failed':'ready',created_at:stamp}],failureDetails:failed?fail():[],hidden:false,notice:null};};
 page.on('pageerror',e=>state.errors.push(e.message));
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname.replace(/^\/api/,'');
  if(path==='/auth/me')return route.fulfill({json:user});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/agents')return route.fulfill({json:Object.entries(settings.agents).map(([id,v])=>({id,...v}))});
  if(path==='/admin/agents')return route.fulfill({json:settings});
  if(path==='/admin/model-providers'&&req.method()==='GET')return route.fulfill({json:providers});
  if(path==='/admin/model-providers'&&req.method()==='POST'){const body=req.postDataJSON();state.providerSaves.push(body);const saved={...body,id:'provider-new',protocol:'openai_chat_completions',apiKey:undefined,apiKeyConfigured:!!body.apiKey,apiKeySource:'db',modelCount:0,updatedAt:new Date().toISOString()};providers.push(saved);return route.fulfill({status:201,json:saved});}
  if(path.startsWith('/admin/model-providers/')&&req.method()==='PUT'){const body=req.postDataJSON();state.providerSaves.push(body);const provider=providers.find(p=>p.id===path.split('/')[3])!;Object.assign(provider,{...body,apiKey:undefined,updatedAt:new Date().toISOString()});return route.fulfill({json:provider});}
  if(path==='/admin/model-configs'&&req.method()==='POST'){const body=req.postDataJSON();state.saves.push(body);const saved={...body,id:'new-model',defaultBindings:[],updatedAt:new Date().toISOString()};configs.push(saved);return route.fulfill({status:201,json:saved});}
  if(path==='/admin/model-configs'&&req.method()==='GET')return route.fulfill({json:configs});
  if(path.startsWith('/admin/model-configs/')&&path.endsWith('/test')){state.tests++;return route.fulfill({json:{success:state.testPass,message:state.testPass?'连接及 JSON 格式校验通过':'模型服务请求受限，请稍后重试',latencyMs:123}});}
  if(path.startsWith('/admin/model-configs/')&&req.method()==='PUT'){const body=req.postDataJSON();state.saves.push(body);const config=configs.find(c=>c.id===path.split('/')[3])!;Object.assign(config,body,{updatedAt:new Date().toISOString()});return route.fulfill({json:config});}
  if(path==='/partners')return route.fulfill({json:[{id:'partner-1',name:'合成伙伴'}]});
  if(path==='/enablement/context')return route.fulfill({json:{partner:url.searchParams.get('partner_id')?{id:'partner-1',name:'合成伙伴'}:null,evidence:[],project:url.searchParams.get('task_id')?{task_id:'source-task',requirement:'来源项目',risk_notes:'已有来源约束',risk_status:'未确认'}:null,shared_case:url.searchParams.get('case_id')?{source_type:'case',source_id:'case-1',source_version:2,title:'合成来源案例',summary:'获准的来源上下文'}:null}});
  if(path==='/agent/tasks'&&req.method()==='POST'){
   const body=req.postDataJSON();state.posts.push({path,body});state.records.set(body.requestId,{kind:'match',text:body.requirement,body});if(state.lose)return route.abort();return route.fulfill({status:202,json:{recordId:body.requestId,runId:'run',taskStatus:'failed'}});
  }
  if(path==='/development/plans'&&req.method()==='POST'){
   const body=req.postDataJSON(),id='development-'+(state.posts.length+1);state.posts.push({path,body});state.records.set(id,{kind:'development',text:body.request.development_direction,body});if(state.lose)return route.abort();return route.fulfill({status:202,json:{plan_id:id,run_id:'run-create'}});
  }
  if(path.startsWith('/development/submissions/')){const entry=[...state.records.entries()].find(([,r])=>r.body.submission_id===path.split('/').at(-1));return route.fulfill(entry?{json:{plan_id:entry[0],run_id:'run-create',status:'failed'}}:{status:404,json:{detail:'尚未受理'}});}
  if(path.endsWith('/conversation')&&req.method()==='POST'){state.followups.push(req.postDataJSON());return route.fulfill({status:202,json:{kind:'revise',plan_id:'existing-plan',run_id:'followup-'+state.followups.length}});}
  if(path.startsWith('/development/plans/'))return route.fulfill({json:plan(path.split('/')[3])});
  if(path==='/agent/tasks')return route.fulfill({json:{items:[...state.records.entries()].map(([id,r])=>summary(id,r)),total:state.records.size,page:1,pageSize:10,totalPages:1}});
  if(path.startsWith('/agent/tasks/')){const id=path.split('/')[3],record=state.records.get(id);if(!record&&id!=='existing-plan')return route.fulfill({status:404,json:{detail:'尚未创建'}});return route.fulfill({json:{...summary(id,record||{kind:'development'}),taskStatus:state.partial?'partial':'failed',recommendations:[],answer:state.partial?'已保存的推荐说明。':'',understanding:null,progress:null,opportunity:null,demandProfile:null,lastErrorStage:state.partial?'persistence':'understanding',failureDetails:fail(),modelSelection:{id:record?.body.modelConfigId||'b',name:names[record?.body.modelConfigId||'b']}}});}
  if(path==='/model-timeout-settings')return route.fulfill({json:{timeoutSeconds:300,timeoutRetries:3}});
  state.errors.push(req.method()+' '+path);return route.fulfill({status:404,json:{detail:'未定义合成接口'}});
 });
 await mockDeviceSession(page);
 await page.route('**/api/agents/*/models',route=>{const id=new URL(route.request().url()).pathname.split('/')[3];return route.fulfill({json:{models:configs.filter(c=>!state.removed||c.id!=='b').map(c=>({id:c.id,name:c.name,isDefault:c.id===(id==='partner_match'?'a':'c'),...(grouped?{providerId:c.providerId,providerName:providers.find(p=>p.id===c.providerId)!.name}:{})})),defaultModelConfigId:id==='partner_match'?'a':'c',agentEnabled:true,unavailableReason:null}});});
 return state;
}
async function choose(page:Page,name:string){await page.getByRole('button',{name:/选择模型：/}).click();await page.getByRole('menuitemradio',{name:new RegExp(name)}).click();}

test('model menus retain independent drafts, choices and session text',async({page})=>{
 const s=await fixture(page);await page.goto('/');await page.locator('#requirement').fill(raw);await choose(page,names.b);await page.getByRole('tab',{name:'促发展',exact:true}).click();await page.getByRole('textbox',{name:'发展方向',exact:true}).fill('独立的发展草稿');await expect(page.getByRole('button',{name:'选择模型：'+names.c})).toBeVisible();await page.getByRole('tab',{name:'找伙伴',exact:true}).click();await expect(page.locator('#requirement')).toHaveValue(raw);await expect(page.getByRole('button',{name:'选择模型：'+names.b})).toBeVisible();await page.reload();await expect(page.locator('#requirement')).toHaveValue(raw);await expect(page.getByRole('button',{name:'选择模型：'+names.b})).toBeVisible();expect(s.posts).toHaveLength(0);expect(s.errors).toEqual([]);
});

test('failed match returns exact text and model, opens menu and creates a new id only on start',async({page})=>{
 const s=await fixture(page);await page.goto('/');await page.locator('#requirement').fill(raw);await choose(page,names.b);await page.getByRole('button',{name:'开始',exact:true}).click();await expect(page.getByRole('button',{name:'返回并切换模型',exact:true})).toBeVisible();await expect(page.getByText(/模型响应超时/)).toBeVisible();const original=s.posts[0].body.requestId;await page.getByRole('button',{name:'返回并切换模型',exact:true}).click();await expect(page.locator('#requirement')).toHaveValue(raw);await expect(page.getByRole('menu',{name:'选择模型'})).toBeVisible();expect(s.posts).toHaveLength(1);expect(page.url()).not.toContain(encodeURIComponent(raw));await page.getByRole('menuitemradio',{name:new RegExp(names.c)}).click();await page.getByRole('button',{name:'开始',exact:true}).click();await expect.poll(()=>s.posts.length).toBe(2);expect(s.posts[1].body.modelConfigId).toBe('c');expect(s.posts[1].body.requestId).not.toBe(original);expect(s.records.has(original)).toBe(true);expect(s.errors).toEqual([]);
});

test('development failure returns original partner and source context without posting again',async({page})=>{
 const s=await fixture(page);await page.goto('/?mode=development&partner_id=partner-1&task_id=source-task&case_id=case-1&case_version=2');await page.getByRole('textbox',{name:'发展方向',exact:true}).fill(raw);await choose(page,names.b);await page.getByRole('button',{name:'开始',exact:true}).click();await page.getByRole('button',{name:'返回并切换模型',exact:true}).click();await expect(page.getByRole('textbox',{name:'发展方向',exact:true})).toHaveValue(raw);await expect(page.getByRole('menu',{name:'选择模型'})).toBeVisible();await expect(page.getByTestId('task-transition')).toHaveCount(0);await expect(page.getByRole('tabpanel',{name:'促发展',exact:true}).getByTestId('source-context')).toBeVisible();expect(s.posts).toHaveLength(1);expect(s.posts[0].body.modelConfigId).toBe('b');expect(s.posts[0].body.request).toMatchObject({target_partner_id:'partner-1',source_task_id:'source-task',source_case_id:'case-1',source_case_version:2});expect(s.errors).toEqual([]);
});

test('failed followup restores raw question, retains current plan, and submits edited text in the same plan',async({page})=>{
 const s=await fixture(page);await page.goto('/tasks/existing-plan');await expect(page.getByTestId('advisor-main-answer')).toContainText('原有效方案保持不变');await choose(page,names.b);const input=page.getByRole('textbox',{name:'消息',exact:true});await input.fill(raw);await page.getByRole('button',{name:'发送',exact:true}).click();await expect(input).toHaveValue(raw);await expect(page.getByRole('button',{name:'返回续问并切换模型'})).toBeVisible();await expect(page.getByTestId('advisor-main-answer')).toContainText('原有效方案保持不变');await page.getByRole('button',{name:'返回续问并切换模型'}).click();await expect(input).toBeFocused();await page.getByRole('menuitemradio',{name:new RegExp(names.c)}).click();await input.fill(raw+'增加一个限制');await page.getByRole('button',{name:'发送',exact:true}).click();await expect.poll(()=>s.followups.length).toBe(2);expect(s.followups[0].modelConfigId).toBe('b');expect(s.followups[1]).toMatchObject({modelConfigId:'c',message:raw+'增加一个限制',based_on_version_id:'version-current'});expect(s.followups[1].submission_id).not.toBe(s.followups[0].submission_id);expect(new URL(page.url()).pathname).toBe('/tasks/existing-plan');expect(s.errors).toEqual([]);
});

for(const [code,text] of [['rate_limit','模型服务请求受限'],['provider','模型服务返回异常'],['invalid_result','模型返回内容未能完成解析']])test('specific safe model error '+code,async({page})=>{
 const s=await fixture(page);s.modelError=code;s.records.set('failed-task',{text:raw,body:{modelConfigId:'b'}});await page.goto('/tasks/failed-task');await expect(page.getByText(new RegExp(text))).toBeVisible();await expect(page.getByText('untrusted raw error must not display')).toHaveCount(0);await expect(page.getByRole('button',{name:'返回并切换模型',exact:true})).toBeVisible();expect(s.errors).toEqual([]);
});

test('partial persistence failure keeps saved output and is not labelled a model timeout',async({page})=>{
 const s=await fixture(page);s.partial=true;s.records.set('partial-task',{text:raw,body:{modelConfigId:'b'}});await page.goto('/tasks/partial-task');await expect(page.getByText('已保存的推荐说明。',{exact:true})).toBeVisible();await expect(page.getByText('结果保存失败，已有内容已保留。',{exact:true})).toBeVisible();await expect(page.getByText(/模型响应超时/)).toHaveCount(0);expect(s.errors).toEqual([]);
});

test('removed choice retains text and blocks submission instead of silently using default',async({page})=>{
 const s=await fixture(page);await page.goto('/');await page.locator('#requirement').fill(raw);await choose(page,names.b);s.removed=true;await page.getByRole('button',{name:'选择模型：'+names.b}).click();await expect(page.getByText('所选模型当前不可用，请重新选择。',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'开始',exact:true})).toBeDisabled();await expect(page.locator('#requirement')).toHaveValue(raw);expect(s.posts).toHaveLength(0);expect(s.errors).toEqual([]);
});

test('lost accepted match response uses its query, never repeats create',async({page})=>{
 const s=await fixture(page);s.lose=true;await page.goto('/');await page.locator('#requirement').fill(raw);await choose(page,names.b);await page.getByRole('button',{name:'开始',exact:true}).click();await expect(page).toHaveURL(/\/tasks\/[a-f0-9-]+$/);await expect(page.getByRole('button',{name:'返回并切换模型',exact:true})).toBeVisible();expect(s.posts).toHaveLength(1);expect(s.errors).toEqual([]);
});

test('lost development acknowledgement retains pending submission and queries before allowing another',async({page})=>{
 const s=await fixture(page);s.lose=true;await page.goto('/?mode=development');await page.getByRole('textbox',{name:'发展方向',exact:true}).fill(raw);await page.getByRole('button',{name:'开始',exact:true}).click();await expect(page.getByRole('button',{name:'刷新查看',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:/选择模型：/})).toBeDisabled();await page.getByRole('button',{name:'刷新查看',exact:true}).click();await expect(page).toHaveURL(/\/tasks\/development-1$/);expect(s.posts).toHaveLength(1);expect(s.errors).toEqual([]);
});

test('admin provider and model editors separate save from saved model test and invalidate old results',async({page})=>{
 const s=await fixture(page,true);await page.setViewportSize({width:1440,height:960});await page.goto('/admin/models');
 await page.getByRole('tab',{name:'模型提供商',exact:true}).click();await page.getByRole('button',{name:new RegExp(names.b)}).click();
 await page.getByRole('article',{name:names.b,exact:true}).getByRole('button',{name:'编辑',exact:true}).click();
 await page.getByLabel('显示名称',{exact:true}).fill('合成连接修改名');await page.getByLabel('允许用户手动选择',{exact:false}).uncheck();
 await page.getByRole('button',{name:'保存模型',exact:true}).click();await expect.poll(()=>s.saves.length).toBe(1);expect(s.tests).toBe(0);
 expect(s.saves[0]).toMatchObject({providerId:'provider-b',name:'合成连接修改名',userSelectable:false,topP:0.8,enabled:true});expect(s.saves[0].apiKey).toBeUndefined();expect(s.saves[0].baseUrl).toBeUndefined();
 await page.getByRole('button',{name:'测试连接',exact:true}).click();await expect(page.getByText('本次测试失败',{exact:true})).toBeVisible();await expect(page.getByText(/123 ms/)).toBeVisible();
 await page.getByLabel('模型 ID',{exact:true}).fill('changed-synthetic-id');await expect(page.getByText('配置已变更',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'测试连接',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'保存模型',exact:true}).click();s.testPass=true;await page.getByRole('button',{name:'测试连接',exact:true}).click();await expect(page.getByText('本次测试通过',{exact:true})).toBeVisible();expect(s.tests).toBe(2);
 await page.screenshot({path:test.info().outputPath('03-model-editor.png'),fullPage:true});
 await page.getByRole('button',{name:'取消',exact:true}).click();await page.getByRole('button',{name:'编辑提供商',exact:true}).click();
 await expect(page.getByText('已保存凭据',{exact:false})).toBeVisible();await page.getByRole('button',{name:'更换',exact:true}).click();await expect(page.getByLabel('替换 API Key',{exact:true})).toHaveValue('');
 await page.getByLabel('替换 API Key',{exact:true}).fill('synthetic-replacement-only');await page.screenshot({path:test.info().outputPath('02-provider-editor.png'),fullPage:true});
 await page.getByRole('button',{name:'保存提供商',exact:true}).click();expect(s.tests).toBe(2);expect(s.providerSaves).toHaveLength(1);
 await expect(page.getByText('配置已变更',{exact:true})).toBeVisible();expect(s.errors).toEqual([]);
});

for(const width of [1440,390])test('refined model menu keyboard and viewport '+width,async({page})=>{
 await fixture(page);await page.setViewportSize({width,height:width===390?844:960});const long='用于验证窄屏长名称展示的合成连接（仅测试）';
 await page.route('**/api/agents/*/models',route=>route.fulfill({json:{models:[{id:'a',name:names.a,isDefault:true},{id:'b',name:long,isDefault:false},{id:'c',name:names.c,isDefault:false}],defaultModelConfigId:'a',agentEnabled:true,unavailableReason:null}}));
 await page.goto('/');await page.locator('#requirement').fill(raw);await choose(page,long);const trigger=page.getByRole('button',{name:'选择模型：'+long});await trigger.focus();await page.keyboard.press('Enter');const menu=page.getByRole('menu',{name:'选择模型'});await expect(menu).toBeVisible();
 const first=page.getByRole('menuitemradio',{name:new RegExp(names.a)}),last=page.getByRole('menuitemradio',{name:names.c,exact:true}),selected=page.getByRole('menuitemradio',{name:long});
 await page.keyboard.press('ArrowUp');await expect(last).toBeFocused();await expect(selected).toHaveAttribute('aria-checked','true');
 await page.keyboard.press('ArrowDown');await expect(first).toBeFocused();await page.keyboard.press('ArrowUp');await expect(last).toBeFocused();
 await page.keyboard.press('ArrowUp');await expect(selected).toBeFocused();await expect(trigger).toHaveAttribute('aria-expanded','true');
 await page.keyboard.press('Escape');await expect(menu).toHaveCount(0);await expect(trigger).toBeFocused();await page.keyboard.press('Enter');
 await page.keyboard.press('ArrowDown');await expect(first).toBeFocused();const box=await menu.boundingBox();expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(width);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:test.info().outputPath('refined-model-menu-'+width+'.png'),fullPage:true});await page.keyboard.press('Escape');await expect(menu).toHaveCount(0);await expect(trigger).toBeFocused();
});

test('non-model followup save failure restores question without suggesting a model timeout',async({page})=>{
 const s=await fixture(page);s.partial=true;await page.goto('/tasks/existing-plan');await expect(page.getByTestId('advisor-main-answer')).toContainText('原有效方案保持不变');const input=page.getByRole('textbox',{name:'消息',exact:true});await input.fill(raw);await page.getByRole('button',{name:'发送',exact:true}).click();await expect(input).toHaveValue(raw);await expect(page.getByRole('button',{name:'返回续问',exact:true})).toBeVisible();await expect(page.getByText('结果保存失败，已有内容已保留。',{exact:true})).toBeVisible();await expect(page.getByText(/模型响应超时/)).toHaveCount(0);await page.getByRole('button',{name:'返回续问',exact:true}).click();await expect(input).toBeFocused();await expect(page.getByRole('menu',{name:'选择模型'})).toHaveCount(0);await expect(page.getByTestId('advisor-main-answer')).toContainText('原有效方案保持不变');expect(s.followups).toHaveLength(1);expect(s.errors).toEqual([]);
});


for(const width of [1440,390])test('refined admin connection hover stays neutral '+width,async({page})=>{
 const s=await fixture(page,true);await page.setViewportSize({width,height:width===390?844:1000});await page.goto('/admin/models');
 await page.getByRole('tab',{name:'模型提供商',exact:true}).click();await page.mouse.move(0,0);
 const chosen=page.getByRole('button',{name:new RegExp(names.a)}),other=page.getByRole('button',{name:new RegExp(names.b)});
 await expect(chosen).toHaveAttribute('aria-pressed','true');await expect(chosen).toHaveCSS('background-color','rgb(255, 255, 255)');
 await other.hover();await expect(other).toHaveCSS('background-color','rgb(240, 240, 237)');await expect(other).toHaveCSS('color','rgb(23, 23, 23)');await expect(other).toHaveAttribute('aria-pressed','false');
 await expect(chosen).toHaveAttribute('aria-pressed','true');await expect(chosen).toHaveCSS('background-color','rgb(255, 255, 255)');
 await page.screenshot({path:test.info().outputPath('admin-neutral-hover-'+width+'.png'),fullPage:true});
 await chosen.hover();await expect(chosen).toHaveCSS('background-color','rgb(255, 255, 255)');await expect(chosen).toHaveCSS('color','rgb(23, 23, 23)');
 expect(await chosen.evaluate(el=>getComputedStyle(el,'::before').backgroundColor)).toBe('rgb(199, 0, 11)');
 expect(await chosen.evaluate(el=>getComputedStyle(el,'::before').width)).toBe('3px');
 await other.click();await expect(other).toHaveAttribute('aria-pressed','true');await expect(other).toHaveCSS('background-color','rgb(255, 255, 255)');await expect(page.getByRole('heading',{name:names.b,exact:true})).toBeVisible();
 expect(s.tests).toBe(0);expect(s.saves).toHaveLength(0);expect(s.errors).toEqual([]);
});


for(const width of [1440,390])test('provider overview, provider editor and model editor fit viewport '+width,async({page})=>{
 const s=await fixture(page,true);await page.setViewportSize({width,height:width===390?844:960});
 await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 await expect(page.getByRole('heading',{name:names.a,exact:true})).toBeVisible();
 await expect(page.getByText('OpenAI Chat Completions',{exact:true})).toBeVisible();
 await expect(page.getByText('✓ 用户可选',{exact:true})).toBeVisible();
 const fits=async()=>expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await fits();await page.screenshot({path:test.info().outputPath('01-provider-overview-'+width+'.png'),fullPage:true});
 await page.getByRole('button',{name:'编辑提供商',exact:true}).click();
 await expect(page.getByLabel('API 协议',{exact:true})).toHaveAttribute('readonly','');
 await expect(page.getByLabel('提供商名称',{exact:true})).toHaveValue(names.a);
 await fits();await page.screenshot({path:test.info().outputPath('02-provider-editor-'+width+'.png'),fullPage:true});
 await page.getByRole('button',{name:'取消',exact:true}).click();await page.getByRole('article',{name:names.a,exact:true}).getByRole('button',{name:'编辑',exact:true}).click();
 await expect(page.getByLabel('启用模型',{exact:true})).toBeChecked();await expect(page.getByText('找伙伴默认',{exact:true})).toBeVisible();
 await page.getByText('高级参数',{exact:false}).click();await page.getByLabel('temperature',{exact:true}).fill('0');
 await expect(page.getByRole('button',{name:'测试连接',exact:true})).toBeDisabled();
 await fits();await page.screenshot({path:test.info().outputPath('03-model-editor-'+width+'.png'),fullPage:true});
 expect(s.tests).toBe(0);expect(s.saves).toHaveLength(0);expect(s.providerSaves).toHaveLength(0);expect(s.errors).toEqual([]);
});

test('new provider precedes new model and neither save calls inference',async({page})=>{
 const s=await fixture(page,true);await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 await page.getByRole('button',{name:'＋ 添加提供商',exact:true}).click();await page.getByLabel('提供商名称',{exact:true}).fill('新增合成提供商');await page.getByLabel('API 地址',{exact:false}).fill('https://new-synthetic.invalid/v1');await page.getByLabel('替换 API Key',{exact:true}).fill('synthetic-new-provider');
 await page.getByRole('button',{name:'保存提供商',exact:true}).click();await expect(page.getByRole('heading',{name:'新增合成提供商',exact:true})).toBeVisible();
 expect(s.providerSaves).toHaveLength(1);expect(s.tests).toBe(0);
 await page.getByRole('button',{name:'＋ 添加模型',exact:true}).click();await page.getByLabel('显示名称',{exact:true}).fill('新增合成模型');await page.getByLabel('模型 ID',{exact:true}).fill('synthetic-new-id');await page.getByLabel('允许用户手动选择',{exact:false}).check();await page.getByRole('button',{name:'保存模型',exact:true}).click();
 await expect(page.getByRole('button',{name:'测试连接',exact:true})).toBeEnabled();
 expect(s.saves).toHaveLength(1);expect(s.saves[0]).toMatchObject({providerId:'provider-new',name:'新增合成模型',modelName:'synthetic-new-id',userSelectable:true});
 expect(s.tests).toBe(0);expect(s.errors).toEqual([]);
});


test('shared provider owns two models and connection edits invalidate both saved test results',async({page})=>{
 const s=await fixture(page,true,true);s.testPass=true;await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 await expect(page.getByText('共享连接配置 · 2 个模型',{exact:true})).toBeVisible();
 for(const name of [names.a,names.b]){await page.getByRole('article',{name,exact:true}).getByRole('button',{name:'测试',exact:true}).click();await expect(page.getByRole('article',{name,exact:true}).getByText('本次测试通过',{exact:true})).toBeVisible();}
 expect(s.tests).toBe(2);await page.getByRole('button',{name:'编辑提供商',exact:true}).click();
 await expect(page.getByText('用于 '+names.a+'、'+names.b,{exact:true})).toBeVisible();
 await page.getByLabel('API 地址',{exact:false}).fill('https://synthetic.invalid/compatible/v1');await page.getByRole('button',{name:'保存提供商',exact:true}).click();
 await expect(page.getByText('配置已变更',{exact:true})).toHaveCount(2);expect(s.tests).toBe(2);expect(s.providerSaves).toHaveLength(1);
 expect(s.providerSaves[0].apiKey).toBeUndefined();expect(s.errors).toEqual([]);
});


for(const width of [1440,390])test('cancel adding provider restores previously selected provider and models '+width,async({page})=>{
 const s=await fixture(page,true);await page.setViewportSize({width,height:width===390?844:960});
 await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 const previous=page.getByRole('button',{name:new RegExp(names.b)});
 await previous.click();await expect(previous).toHaveAttribute('aria-pressed','true');
 await expect(page.getByRole('article',{name:names.b,exact:true})).toBeVisible();
 await page.getByRole('button',{name:'＋ 添加提供商',exact:true}).click();
 await expect(page.getByRole('heading',{name:'添加提供商',exact:true})).toBeVisible();
 await expect(page.getByLabel('提供商名称',{exact:true})).toHaveValue('');
 await expect(page.getByRole('button',{name:'删除提供商',exact:true})).toHaveCount(0);
 await expect(page.getByText('尚未添加模型',{exact:true})).toBeVisible();
 await page.getByLabel('提供商名称',{exact:true}).fill('取消的提供商草稿');
 await page.getByLabel('API 地址',{exact:false}).fill('https://cancelled.invalid/v1');
 await page.getByLabel('替换 API Key',{exact:true}).fill('synthetic-discarded-key');
 await page.getByRole('button',{name:'取消',exact:true}).click();
 await expect(previous).toHaveAttribute('aria-pressed','true');
 await expect(page.getByRole('heading',{name:names.b,exact:true})).toBeVisible();
 await expect(page.getByRole('article',{name:names.b,exact:true})).toBeVisible();
 await expect(page.getByRole('article',{name:names.a,exact:true})).toHaveCount(0);
 await expect(page.getByText('选择提供商，或添加一个模型提供商。',{exact:true})).toHaveCount(0);
 await expect(page.getByText('https://synthetic.invalid/v1',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'＋ 添加提供商',exact:true}).click();
 await expect(page.getByLabel('提供商名称',{exact:true})).toHaveValue('');
 await expect(page.getByLabel('API 地址',{exact:false})).toHaveValue('');
 await expect(page.getByLabel('替换 API Key',{exact:true})).toHaveValue('');
 await page.getByRole('button',{name:'取消',exact:true}).click();
 await expect(page.getByRole('article',{name:names.b,exact:true})).toBeVisible();
 expect(s.providerSaves).toHaveLength(0);expect(s.saves).toHaveLength(0);expect(s.tests).toBe(0);expect(s.errors).toEqual([]);
 await page.screenshot({path:test.info().outputPath('cancel-add-provider-restores-selection-'+width+'.png'),fullPage:true});
});

test('cancel existing provider and model edits retains their saved values and selection',async({page})=>{
 const s=await fixture(page,true);await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 const previous=page.getByRole('button',{name:new RegExp(names.b)});await previous.click();
 await page.getByRole('button',{name:'编辑提供商',exact:true}).click();
 await page.getByLabel('提供商名称',{exact:true}).fill('未保存的提供商名称');
 await page.getByLabel('API 地址',{exact:false}).fill('https://discarded.invalid/v1');
 await page.getByRole('button',{name:'取消',exact:true}).click();
 await expect(previous).toHaveAttribute('aria-pressed','true');await expect(page.getByRole('heading',{name:names.b,exact:true})).toBeVisible();
 await page.getByRole('button',{name:'编辑提供商',exact:true}).click();
 await expect(page.getByLabel('提供商名称',{exact:true})).toHaveValue(names.b);
 await expect(page.getByLabel('API 地址',{exact:false})).toHaveValue('https://synthetic.invalid/v1');
 await expect(page.getByText('已保存凭据',{exact:false})).toBeVisible();
 await page.getByRole('button',{name:'取消',exact:true}).click();
 const row=page.getByRole('article',{name:names.b,exact:true});
 await row.getByRole('button',{name:'编辑',exact:true}).click();
 await page.getByLabel('显示名称',{exact:true}).fill('未保存的模型名称');await page.getByLabel('模型 ID',{exact:true}).fill('discarded-model-id');
 await page.getByRole('button',{name:'取消',exact:true}).click();
 await expect(previous).toHaveAttribute('aria-pressed','true');await expect(row).toBeVisible();
 await expect(row.getByText('synthetic-b',{exact:true})).toBeVisible();
 await row.getByRole('button',{name:'编辑',exact:true}).click();
 await expect(page.getByLabel('显示名称',{exact:true})).toHaveValue(names.b);
 await expect(page.getByLabel('模型 ID',{exact:true})).toHaveValue('synthetic-b');
 await page.getByRole('button',{name:'取消',exact:true}).click();
 expect(s.providerSaves).toHaveLength(0);expect(s.saves).toHaveLength(0);expect(s.tests).toBe(0);expect(s.errors).toEqual([]);
});

test('cancel adding provider from initial empty list returns to the empty state',async({page})=>{
 const s=await fixture(page,true);
 await page.route('**/api/admin/model-providers',route=>route.fulfill({json:[]}));
 await page.route('**/api/admin/model-configs',route=>route.fulfill({json:[]}));
 await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 await expect(page.getByText('暂无模型提供商。',{exact:true})).toBeVisible();
 await expect(page.getByText('选择提供商，或添加一个模型提供商。',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'＋ 添加提供商',exact:true}).click();
 await page.getByLabel('提供商名称',{exact:true}).fill('取消的空态草稿');
 await page.getByRole('button',{name:'取消',exact:true}).click();
 await expect(page.getByText('暂无模型提供商。',{exact:true})).toBeVisible();
 await expect(page.getByText('选择提供商，或添加一个模型提供商。',{exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'添加提供商',exact:true})).toHaveCount(0);
 expect(s.providerSaves).toHaveLength(0);expect(s.saves).toHaveLength(0);expect(s.tests).toBe(0);expect(s.errors).toEqual([]);
});


async function openProvider(page:Page,name:string){
 await page.getByRole('button',{name:/选择模型：/}).click();
 await page.getByRole('menuitem',{name:new RegExp('^'+name)}).click();
}
async function chooseGrouped(page:Page,provider:string,model:string){
 await openProvider(page,provider);
 await page.getByRole('menuitemradio',{name:new RegExp(model)}).click();
}
const savedMatchModel=(page:Page)=>page.evaluate(()=>JSON.parse(sessionStorage.getItem('banfei:model-draft:user-model-qa:partner_match:draft')||'{}').modelConfigId);

test('compact provider menu uses32px rows and navigation never selects a model',async({page})=>{
 const state=await fixture(page,false,false,true);await page.setViewportSize({width:1440,height:960});
 await page.goto('/');await page.locator('#requirement').fill(raw);
 const trigger=page.getByRole('button',{name:'选择模型：'+names.a});
 await expect(trigger).toBeVisible();await trigger.click();
 const menu=page.getByRole('menu',{name:'选择模型',exact:true});
 const provider=menu.getByRole('menuitem',{name:new RegExp('^'+names.b)});
 await provider.hover();
 expect((await menu.boundingBox())!.width).toBe(280);
 expect((await provider.boundingBox())!.height).toBe(32);
 expect((await menu.getByText('选择供应商',{exact:true}).boundingBox())!.height).toBe(32);
 await expect(provider).toHaveCSS('font-size','14px');await expect(provider).toHaveCSS('padding-top','4px');
 await expect(provider).toHaveCSS('padding-bottom','4px');await expect(provider).toHaveCSS('background-color','rgb(245, 245, 243)');
 await page.screenshot({path:test.info().outputPath('compact-provider-desktop.png'),fullPage:true});
 await provider.click();
 await expect(menu.getByRole('menuitemradio',{name:names.b,exact:true})).toHaveAttribute('aria-checked','false');
 const back=menu.getByRole('menuitem',{name:'返回供应商',exact:true});
 expect((await back.boundingBox())!.height).toBe(32);
 expect((await menu.getByRole('menuitemradio',{name:names.b,exact:true}).boundingBox())!.height).toBe(32);
 await expect(trigger).toBeVisible();expect(await savedMatchModel(page)).toBe('a');
 await page.screenshot({path:test.info().outputPath('compact-model-desktop.png'),fullPage:true});
 await back.click();await expect(provider).toBeFocused();expect(await savedMatchModel(page)).toBe('a');
 await provider.click();await page.keyboard.press('Escape');await expect(menu).toHaveCount(0);await expect(trigger).toBeFocused();
 await trigger.click();await expect(menu.getByText('选择供应商',{exact:true})).toBeVisible();await expect(menu.getByRole('menuitemradio')).toHaveCount(0);
 await page.locator('#requirement').click({position:{x:12,y:12}});await expect(menu).toHaveCount(0);expect(await savedMatchModel(page)).toBe('a');
 expect(state.posts).toHaveLength(0);expect(state.errors).toEqual([]);
});

test('compact provider menu keyboard first item arrows return escape and tab',async({page})=>{
 const state=await fixture(page,false,true,true);await page.goto('/');
 const trigger=page.getByRole('button',{name:'选择模型：'+names.a});await trigger.focus();await page.keyboard.press('Enter');
 const first=page.getByRole('menuitem',{name:new RegExp('^'+names.a)}),last=page.getByRole('menuitem',{name:new RegExp('^'+names.c)});
 await page.keyboard.press('ArrowUp');await expect(last).toBeFocused();
 await page.keyboard.press('ArrowDown');await expect(first).toBeFocused();
 await page.keyboard.press('ArrowRight');
 const a=page.getByRole('menuitemradio',{name:new RegExp(names.a)}),b=page.getByRole('menuitemradio',{name:names.b,exact:true});
 await expect(a).toBeFocused();await expect(a).toHaveAttribute('aria-checked','true');
 await page.keyboard.press('ArrowDown');await expect(b).toBeFocused();expect(await savedMatchModel(page)).toBe('a');
 await page.keyboard.press('ArrowLeft');await expect(first).toBeFocused();
 await page.keyboard.press('Enter');await expect(a).toBeFocused();await page.keyboard.press('ArrowUp');
 await expect(page.getByRole('menuitem',{name:'返回供应商'})).toBeFocused();await page.keyboard.press('Enter');await expect(first).toBeFocused();
 await page.keyboard.press('Escape');await expect(trigger).toBeFocused();
 await page.keyboard.press('ArrowDown');await expect(first).toBeFocused();await page.keyboard.press('Tab');
 await expect(page.getByRole('menu',{name:'选择模型'})).toHaveCount(0);await expect(trigger).not.toBeFocused();
 await trigger.focus();await page.keyboard.press('Enter');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
 await expect(a).toBeFocused();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
 await expect(page.getByRole('button',{name:'选择模型：'+names.b})).toBeFocused();expect(await savedMatchModel(page)).toBe('b');
 expect(state.posts).toHaveLength(0);expect(state.errors).toEqual([]);
});

test('compact provider menu preserves distinct provider ids and duplicate model names',async({page})=>{
 const state=await fixture(page,false,false,true);
 await page.route('**/api/agents/*/models',route=>route.fulfill({json:{models:[
  {id:'a',name:'同名模型',providerId:'first-provider',providerName:'同名供应商',isDefault:true},
  {id:'b',name:'同名模型',providerId:'second-provider',providerName:'同名供应商',isDefault:false}
 ],defaultModelConfigId:'a',agentEnabled:true,unavailableReason:null}}));
 await page.goto('/');await page.locator('#requirement').fill(raw);
 await page.getByRole('button',{name:'选择模型：同名模型'}).click();
 const providers=page.getByRole('menuitem',{name:/^同名供应商/});await expect(providers).toHaveCount(2);
 await providers.nth(1).click();await page.getByRole('menuitemradio',{name:'同名模型',exact:true}).click();
 expect(await savedMatchModel(page)).toBe('b');await page.getByRole('button',{name:'开始',exact:true}).click();
 await expect.poll(()=>state.posts.length).toBe(1);expect(state.posts[0].body.modelConfigId).toBe('b');expect(state.errors).toEqual([]);
});

test('compact provider menu default current and independent business drafts remain separate',async({page})=>{
 const state=await fixture(page,false,false,true);await page.goto('/');await page.locator('#requirement').fill(raw);
 await chooseGrouped(page,names.b,names.b);await page.getByRole('button',{name:'选择模型：'+names.b}).click();
 const defaultProvider=page.getByRole('menuitem',{name:new RegExp('^'+names.a)}),currentProvider=page.getByRole('menuitem',{name:new RegExp('^'+names.b)});
 await expect(defaultProvider.getByText('含默认模型',{exact:true})).toBeVisible();await expect(defaultProvider.getByText('当前',{exact:true})).toHaveCount(0);
 await expect(currentProvider.getByText('当前',{exact:true})).toHaveCSS('color','rgb(199, 0, 11)');
 await currentProvider.click();const selected=page.getByRole('menuitemradio',{name:names.b,exact:true});await expect(selected).toHaveAttribute('aria-checked','true');
 await expect(selected.locator('span').last()).toHaveCSS('color','rgb(199, 0, 11)');await page.keyboard.press('Escape');
 await page.getByRole('tab',{name:'促发展',exact:true}).click();await page.getByRole('textbox',{name:'发展方向',exact:true}).fill('独立发展草稿');
 await expect(page.getByRole('button',{name:'选择模型：'+names.c})).toBeVisible();await chooseGrouped(page,names.a,names.a);
 await page.getByRole('tab',{name:'找伙伴',exact:true}).click();await expect(page.getByRole('button',{name:'选择模型：'+names.b})).toBeVisible();await expect(page.locator('#requirement')).toHaveValue(raw);
 await page.reload();await expect(page.getByRole('button',{name:'选择模型：'+names.b})).toBeVisible();
 expect(state.posts).toHaveLength(0);expect(state.errors).toEqual([]);
});

test('compact provider menu refreshed empty supplier retains back without selecting',async({page})=>{
 const state=await fixture(page,false,false,true);
 const models=['a','b','c'].map(id=>({id,name:names[id],providerId:'provider-'+id,providerName:names[id],isDefault:id==='a'}));
 let hold=false,release:(()=>void)|undefined;
 await page.route('**/api/agents/*/models',async route=>{
  const match=route.request().url().includes('/partner_match/');let rows=models;
  if(match&&hold){hold=false;await new Promise<void>(resolve=>{release=resolve;});rows=models.filter(m=>m.id!=='b');}
  return route.fulfill({json:{models:rows,defaultModelConfigId:match?'a':'c',agentEnabled:true,unavailableReason:null}});
 });
 await page.goto('/');const trigger=page.getByRole('button',{name:'选择模型：'+names.a});await expect(trigger).toBeVisible();
 hold=true;await trigger.click();await page.getByRole('menuitem',{name:new RegExp('^'+names.b)}).click();
 await expect(page.getByRole('menuitemradio',{name:names.b,exact:true})).toBeVisible();await expect.poll(()=>!!release).toBe(true);release!();
 await expect(page.getByText('该供应商暂无可选模型。',{exact:true})).toBeVisible();
 const back=page.getByRole('menuitem',{name:'返回供应商'});await expect(back).toBeVisible();await expect(back).toBeFocused();
 await expect(trigger).toBeVisible();expect(await savedMatchModel(page)).toBe('a');
 await back.click();await expect(page.getByText('选择供应商',{exact:true})).toBeVisible();await expect(page.getByRole('menuitem',{name:new RegExp('^'+names.b)})).toHaveCount(0);
 expect(await savedMatchModel(page)).toBe('a');expect(state.posts).toHaveLength(0);expect(state.errors).toEqual([]);
});

test('compact provider menu keeps followup plan and restored text across supplier changes',async({page})=>{
 const state=await fixture(page,false,false,true);await page.goto('/tasks/existing-plan');
 await chooseGrouped(page,names.b,names.b);const input=page.getByRole('textbox',{name:'消息',exact:true});await input.fill(raw);
 await page.getByRole('button',{name:'发送',exact:true}).click();await expect(input).toHaveValue(raw);
 await page.getByRole('button',{name:'返回续问并切换模型'}).click();
 await expect(page.getByText('选择供应商',{exact:true})).toBeVisible();await expect(page.getByRole('menuitemradio')).toHaveCount(0);
 await page.getByRole('menuitem',{name:new RegExp('^'+names.c)}).click();await page.getByRole('menuitemradio',{name:new RegExp(names.c)}).click();
 await expect(input).toHaveValue(raw);await expect(page.getByTestId('advisor-main-answer')).toContainText('原有效方案保持不变');
 expect(state.followups).toHaveLength(1);expect(state.followups[0].modelConfigId).toBe('b');expect(state.errors).toEqual([]);
});

for(const width of [1440,390])test('compact provider menu long readable names and viewport '+width,async({page})=>{
 const state=await fixture(page,false,false,true);await page.setViewportSize({width,height:width===390?844:960});
 const long='用于验证长模型名完整可读并保留当前模型身份的合成选项';
 const models=[{id:'a',name:names.a,providerId:'pa',providerName:'供应商甲',isDefault:true},...Array.from({length:20},(_,i)=>({id:'b'+i,name:long+' '+i,providerId:'pb',providerName:'供应商乙',isDefault:false}))];
 await page.route('**/api/agents/*/models',route=>route.fulfill({json:{models,defaultModelConfigId:'a',agentEnabled:true,unavailableReason:null}}));
 await page.goto('/');await openProvider(page,'供应商乙');
 const chosen=page.getByRole('menuitemradio',{name:long+' 18',exact:true});await chosen.click();
 const trigger=page.getByRole('button',{name:'选择模型：'+long+' 18'});await expect(trigger).toBeVisible();
 await expect(trigger.locator('span').first()).toHaveCSS('text-overflow','ellipsis');
 await openProvider(page,'供应商乙');await expect(chosen).toHaveAttribute('aria-checked','true');
 await expect(chosen).toHaveCSS('white-space','normal');await expect(chosen.locator('span').first()).toHaveText(long+' 18');
 const menu=page.getByRole('menu',{name:'选择模型'}),box=await menu.boundingBox();expect(box!.width).toBe(280);expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(width);if(width===390)expect(box!.x+box!.width).toBeCloseTo(width-16,0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(await menu.locator('div').first().evaluate(node=>node.scrollHeight>node.clientHeight)).toBe(true);
 await page.screenshot({path:test.info().outputPath('compact-long-menu-'+width+'.png'),fullPage:true});
 expect(state.posts).toHaveLength(0);expect(state.errors).toEqual([]);
});

test.describe('compact provider touch targets',()=>{
 test.use({viewport:{width:390,height:844},hasTouch:true});
 test('compact provider menu touch rows are44px',async({page})=>{
  await fixture(page,false,false,true);await page.goto('/');await page.getByRole('button',{name:/选择模型：/}).click();
  const provider=page.getByRole('menuitem',{name:new RegExp('^'+names.b)});await expect(provider).toBeVisible();
  expect((await provider.boundingBox())!.height).toBe(44);await provider.click();
  expect((await page.getByRole('menuitem',{name:'返回供应商'}).boundingBox())!.height).toBe(44);
  expect((await page.getByRole('menuitemradio',{name:names.b,exact:true}).boundingBox())!.height).toBe(44);
  await page.screenshot({path:test.info().outputPath('compact-touch-menu.png'),fullPage:true});
 });
});
