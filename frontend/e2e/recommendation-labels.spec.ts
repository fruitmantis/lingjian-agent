import {mockDeviceSession} from './device-session-fixture';
import {test,expect,type Page} from '@playwright/test';

const stamp='2026-10-16T00:00:00Z';
const raw='伙伴发展经理原话：伙伴匹配与伙伴发展，保留原文。';
const options={modelConfigId:'naming-model',thinking:true,timeoutSeconds:300,timeoutRetries:3};
const settings={agents:{partner_match:{...options,name:'伙伴匹配',description:raw,icon:'users',enabled:true},partner_development:{...options,name:'伙伴发展',description:raw,icon:'trend',enabled:true}},processing:{...options}};
const snapshot=JSON.stringify(settings);
const match={id:'names-match',requirement:raw,createdAt:stamp,createdBy:'合成用户',ownerName:'合成用户',taskStatus:'ready',task_type:'partner_match',archivedAt:null,topPartner:'合成伙伴',partnerCount:0,completenessScore:null,lastErrorStage:null};
const development={...match,id:'names-development',task_type:'development_plan',planPresentation:{state:'available',current_available:true,current_version:1,latest_run_status:'ready',latest_run_type:'generate'}};
const plan={plan:{id:development.id,current_version_id:'names-v1',status:'active',active_run_id:null},presentation:development.planPresentation,partner_name:'合成伙伴',request:{raw_demand:raw},payload:{answer:raw,overview:{},stages:[],limitations:[],resource_gaps:[]},hidden:false,notice:null,versions:[{id:'names-v1',version_no:1}],conversation:[{submission_id:'names-conversation',message:'用户原话：'+raw,answer:'旧助手证据：'+raw}],runs:[{id:'names-run',run_type:'generate',status:'ready',created_at:stamp}]};
const transfer='伙伴能力发展安排\n'+raw+'\n正文仍有伙伴能力发展安排，不应替换。';
const copied='伙伴能力发展安排\n'+raw+'\n正文仍有伙伴能力发展安排，不应替换。';
const errorEntry={id:'names-error',time:stamp,request_id:'names-request',task_id:match.id,run_id:null,stage:'partner_match',exception_type:'SyntheticError',message:'原始错误：'+raw,model:'synthetic-model',http_status:422,response_excerpt:'原始模型片段：'+raw,traceback:'原始堆栈：'+raw};

async function setup(page:Page){
 const user={id:'names-user',username:'names-user',display_name:'合成用户',role:'user',status:'active',must_change_password:false},admin={...user,id:'names-admin',role:'admin'};
 await page.addInitScript(({user,admin})=>{for(const [scope,value] of [['user',user],['admin',admin]] as const){localStorage.setItem(`banfei:${scope}:token`,scope==='admin'?'names-admin-token':'names-user-token');localStorage.setItem(`banfei:${scope}:user`,JSON.stringify(value));}},{user,admin});
 const unexpected:string[]=[],errors:string[]=[],writes:{method:string;path:string;body:any}[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname.slice(4),method=request.method();
  if(method!=='GET'){
   writes.push({method,path,body:request.postData()?request.postDataJSON():null});
   if(path==='/development/plans/names-development/copy'&&method==='POST')return route.fulfill({json:{text:transfer,version_id:'names-v1'}});
   if(path==='/partners/names-partner'&&method==='DELETE')return route.fulfill({status:409,json:{detail:{code:'partner_delete_blocked',counts:{matching_tasks:2,unverifiable_matching_tasks:1,development_plans:3},message:'无法删除：存在伙伴推荐历史 2 条、无法核验关联的推荐历史 1 条、能力发展方案 3 条。请停用伙伴以保留历史。'}}});
   unexpected.push(method+' '+path);return route.fulfill({status:500,json:{detail:'Blocked synthetic write'}});
  }
  if(path==='/auth/me')return route.fulfill({json:request.headers().authorization?.includes('admin-token')?admin:user});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/agents')return route.fulfill({json:Object.entries(settings.agents).map(([id,a])=>({id,name:a.name,description:a.description,icon:a.icon,enabled:a.enabled}))});
  if(path==='/admin/agents')return route.fulfill({json:settings});
  if(path==='/admin/model-configs')return route.fulfill({json:[{id:'naming-model',name:'合成连接',modelName:'deepseek-flash',enabled:true,provider:'OpenAI Compatible',baseUrl:'https://example.invalid',apiKeyConfigured:true,maxTokens:384000,temperature:.3,isDefault:true}]});
  if(path==='/agent/tasks'||path==='/admin/tasks'){
   const type=url.searchParams.get('task_type'),items=[match,development].filter(x=>!type||x.task_type===type);
   return route.fulfill({json:{items,total:items.length,page:1,pageSize:20,totalPages:1}});
  }
  if(path.startsWith('/agent/tasks/')){const id=path.split('/').pop()!,dev=id===development.id||id==='scope-development';return route.fulfill({json:{...(dev?development:match),id,recommendations:[],answer:raw,demandProfile:null,opportunity:null,...(id==='scope-match'?{scopeMessage:'这里仅支持伙伴选择与推荐，请描述项目需求或询问相关推荐结果。'}:{})}});}
  if(path.startsWith('/development/plans/')&&path.endsWith('/transferable'))return route.fulfill({json:{text:transfer,version_id:'names-v1'}});
  if(path.startsWith('/development/plans/'))return route.fulfill({json:{...plan,...(path.endsWith('/scope-development')?{scopeMessage:'这里仅支持伙伴能力发展建议，请描述发展方向或询问相关方案。'}:{})}});
  if(path==='/admin/dashboard')return route.fulfill({json:{users:1,disabledUsers:0,partners:1,partnersWithoutProfile:0,tasks:7,monthTasks:4,opportunities:0,gapDemands:0,pendingSuggestions:0,partnerMatchTasks:5,developmentTasks:2,monthPartnerMatchTasks:3,monthDevelopmentTasks:1}});
  if(path==='/admin/demand-profiles')return route.fulfill({json:{profiles:[]}});
  if(path==='/admin/opportunities')return route.fulfill({json:[]});
  if(path==='/partners')return route.fulfill({json:[{id:'names-partner',name:'合成伙伴',intro:raw,capabilities:'',industries:'',service_areas:'',ai_profile:null,status:'active',profile_status:'ready',created_at:stamp}]});
  if(path==='/enablement/context')return route.fulfill({json:{partner:null,project:null,shared_case:null,evidence:[]}});
  if(path==='/admin/system/errors')return route.fulfill({json:{items:[errorEntry]}});
  if(path==='/admin/system/status')return route.fulfill({json:{overallStatus:'partial',checkedAt:stamp,summary:{normalCount:0,warningCount:1,errorCount:1,unknownCount:0,abnormalModules:[{module:'智能匹配',status:'error',message:'合成配置问题',impact:'可能影响 AI 画像生成、智能匹配和需求画像生成',suggestion:'检查配置'},{module:'能力发展',status:'warning',message:'能力发展模型配置不可用，请检查场景绑定、模型启用状态和凭据',impact:'能力发展任务可能无法执行',suggestion:'检查配置'}]},services:[],database:[],llm:[{name:'智能匹配',status:'normal',message:'自定义连接名称'}],businessCapabilities:[{name:'智能匹配',status:'error',message:'合成配置问题'},{name:'能力发展',status:'warning',message:'能力发展模型配置不可用，请检查场景绑定、模型启用状态和凭据'}],recentErrors:[]}});
  unexpected.push(method+' '+path);return route.fulfill({status:404,json:{detail:'Undefined synthetic route'}});
 });
  await mockDeviceSession(page);
 return {unexpected,errors,writes,check(){expect(unexpected).toEqual([]);expect(errors).toEqual([]);expect(JSON.stringify(settings)).toBe(snapshot);}};
}
async function paste(page:Page){
 await page.evaluate(()=>{const el=document.createElement('textarea');el.id='naming-paste';document.body.appendChild(el);el.focus();});
 await page.keyboard.press('Control+V');const target=page.locator('#naming-paste');
 return target;
}
for(const admin of [false,true])test(`recommendation labels: ${admin?'admin':'user'} history projects labels and preserves requirement`,async({page})=>{
 const f=await setup(page);await page.goto(admin?'/admin/tasks':'/tasks');
 await expect(page.getByLabel('任务类型').locator('option')).toHaveText(['全部类型','伙伴推荐','能力发展']);
 const rows=page.locator('tbody tr');await expect(rows).toHaveCount(2);
 await expect(rows.nth(0).locator('td').nth(0)).toHaveText(raw);await expect(rows.nth(0).locator('td').nth(1)).toHaveText('伙伴推荐');
 await expect(rows.nth(1).locator('td').nth(1)).toHaveText('能力发展');
 if(!admin){await expect(page.locator('.sidebar-task-list')).toContainText('伙伴推荐');await expect(page.locator('.sidebar-task-list')).toContainText('能力发展');}
 expect(f.writes).toHaveLength(0);f.check();
});
test('recommendation labels: settings normalize legacy labels while model options and custom roles survive',async({page})=>{
 const f=await setup(page);await page.goto('/admin/models');
 for(const [id,name] of [['partner_match','伙伴推荐'],['partner_development','伙伴发展']]){
  const panel=page.getByTestId('agent-'+id);await expect(panel.getByLabel('展示名称')).toHaveValue(name);await expect(panel.getByLabel('简介')).toHaveValue(raw);await expect(panel.getByLabel(/^模型/)).toHaveValue(options.modelConfigId);await expect(panel.getByLabel('请求超时（秒）')).toHaveValue('300');await expect(panel.getByLabel('开启思考（模型支持时）')).toBeChecked();
 }
 await page.goto('/tasks/names-match');await expect(page.locator('[data-agent-id="partner_match"]')).toHaveText('伙伴推荐');await expect(page.getByTestId('advisor-answer').locator('.advisor-answer-body')).toHaveText(raw);
 await page.route('**/api/agents',route=>route.fulfill({json:[{id:'partner_match',...settings.agents.partner_match,name:'伙伴发展经理'}]}));
 await page.reload();await expect(page.locator('[data-agent-id="partner_match"]')).toHaveText('伙伴发展经理');for(const name of ['行业匹配顾问','智能匹配','资源匹配']){await page.route('**/api/agents',route=>route.fulfill({json:[{id:'partner_match',...settings.agents.partner_match,name}]}));await page.reload();await expect(page.locator('[data-agent-id="partner_match"]')).toHaveText(name);}expect(f.writes).toHaveLength(0);f.check();
});
test('recommendation labels: legacy scene links select current categories and quick template label',async({page})=>{
 const f=await setup(page);
 for(const [old,name] of [['智能匹配','智能推荐'],['能力发展','能力发展']]){await page.goto('/scenes?category='+encodeURIComponent(old));await expect(page.getByRole('tab',{name,exact:true})).toHaveAttribute('aria-selected','true');}
 await expect(page.getByRole('heading',{name:'制定伙伴能力发展建议',exact:true})).toBeVisible();await page.goto('/scenes?category='+encodeURIComponent('智能匹配'));await expect(page.getByRole('tab',{name:'智能推荐',exact:true})).toHaveAttribute('aria-selected','true');await expect(page.getByText('根据项目需求推荐合作伙伴',{exact:true})).toBeVisible();await page.getByRole('tab',{name:'全部',exact:true}).click();await expect.poll(()=>new URL(page.url()).searchParams.get('category')).toBe(null);await page.getByRole('tab',{name:'智能推荐',exact:true}).click();await expect.poll(()=>new URL(page.url()).searchParams.get('category')).toBe('智能推荐');
 await page.goto('/');await expect(page.getByRole('tab',{name:'找伙伴',exact:true})).toBeVisible();await expect(page.getByRole('tab',{name:'促发展',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'伙伴发展建议',exact:true})).toBeVisible();expect(f.writes).toHaveLength(0);f.check();
});
test('recommendation labels: development, conversation and actual copied transfer keep original business text',async({page})=>{
 const f=await setup(page);await page.goto('/tasks/names-development');
 await expect(page.getByRole('heading',{name:'能力发展建议',exact:true})).toBeVisible();await expect(page.locator('[data-agent-id="partner_development"]')).toHaveText('伙伴发展');await expect(page.getByTestId('advisor-main-answer').locator('.advisor-answer-body')).toHaveText(raw);await expect(page.locator('.advisor-question')).toContainText('用户原话：'+raw);await expect(page.getByTestId('conversation')).toContainText('旧助手证据：'+raw);
 await page.locator('.advisor-more > summary').click();await page.getByRole('button',{name:'伙伴可传递视图预览',exact:true}).click();await expect(page.getByTestId('transfer-preview').locator('pre')).toHaveText(copied);await page.getByRole('button',{name:'复制内容',exact:true}).click();await expect(await paste(page)).toHaveValue(copied);
 expect(f.writes).toEqual([{method:'POST',path:'/development/plans/names-development/copy',body:{version_id:'names-v1'}}]);f.check();
});
test('recommendation labels: system status and error copy update fixed labels only',async({page})=>{
 const f=await setup(page);await page.goto('/admin/system');
 await expect(page.getByRole('heading',{name:'系统部分异常：伙伴推荐、能力发展',exact:true})).toBeVisible();await expect(page.getByText('智能匹配',{exact:true})).toHaveCount(1);await expect(page.locator('.ui-status-row').filter({has:page.getByText('能力发展',{exact:true})})).toContainText('能力发展模型配置不可用');await expect(page.locator('.ui-status-issue').first()).toContainText('可能影响 AI 画像生成、伙伴推荐和需求画像生成');
 const entry=page.locator('[data-error-id="names-error"]');await entry.locator('summary').click();const detail=entry.getByLabel('错误完整详情');await expect(detail).toContainText('失败环节：伙伴推荐');for(const value of [errorEntry.message,errorEntry.response_excerpt,errorEntry.traceback])await expect(detail).toContainText(value);
 await entry.getByRole('button',{name:'复制错误详情'}).click();await expect(await paste(page)).toHaveValue((await detail.textContent())!);expect(f.writes).toHaveLength(0);f.check();
});
test('recommendation labels: blocked deletion uses current fixed labels without altering partner text',async({page})=>{
 const f=await setup(page);await page.goto('/admin/partners');const row=page.locator('tbody tr').filter({hasText:'合成伙伴'});await expect(row).toBeVisible();page.once('dialog',dialog=>dialog.accept());await row.getByRole('button',{name:'删除',exact:true}).click();await expect(page.getByRole('alert').filter({hasText:'无法删除'})).toHaveText('无法删除：存在伙伴推荐历史 2 条、无法核验关联的推荐历史 1 条、能力发展方案 3 条。请停用伙伴以保留历史。');await expect(row).toBeVisible();expect(f.writes).toEqual([{method:'DELETE',path:'/partners/names-partner',body:null}]);f.check();
});
test('recommendation labels: existing scope responses map only known system templates',async({page})=>{
 const f=await setup(page);
 for(const [id,text] of [['scope-match','这里仅支持伙伴选择与推荐，请描述项目需求或询问相关推荐结果。'],['scope-development','这里仅支持伙伴能力发展建议，请描述发展方向或询问相关方案。']]){await page.goto('/tasks/'+id);await expect(page.getByTestId('scope-result')).toHaveText(text);}
 expect(f.writes).toHaveLength(0);f.check();
});

test.afterEach(async({page},info)=>{await page.locator("#naming-paste").evaluateAll(nodes=>nodes.forEach(node=>node.remove()));await page.screenshot({path:info.outputPath("recommendation-labels.png"),fullPage:true});});


test('recommendation labels: score, order and capabilities keep exact values while empty history stays literal',async({page})=>{
 const f=await setup(page);
 const recommendations=[{partnerId:'names-partner',partnerName:'合成伙伴',matchScore:'92.5',matchedCapabilities:'认证能力标签原名',matchedIndustries:'',matchedRegions:'',recommendationReason:raw,evidenceCases:'',evidenceDeliverables:'',riskNotes:''},{partnerId:'second-partner',partnerName:'第二伙伴',matchScore:'71',matchedCapabilities:'第二能力原名',matchedIndustries:'',matchedRegions:'',recommendationReason:raw,evidenceCases:'',evidenceDeliverables:'',riskNotes:''}];
 await page.route('**/api/agent/tasks/names-match',route=>route.fulfill({json:{...match,recommendations,answer:raw,demandProfile:null,opportunity:null}}));
 await page.goto('/tasks/names-match');await expect(page.getByText('推荐分 92.5',{exact:true})).toBeVisible();await expect(page.getByText('推荐分 71',{exact:true})).toBeVisible();await expect(page.locator('.recommendation-item').first().getByRole('heading',{name:'合成伙伴',exact:true})).toBeVisible();await expect(page.locator('.recommendation-item').first().getByText('相关能力',{exact:true})).toBeVisible();await expect(page.locator('.recommendation-item').first()).toContainText('认证能力标签原名');await expect(page.getByTestId('advisor-answer').locator('.advisor-answer-body')).toHaveText(raw);
 const history='历史原文：伙伴匹配；本次暂无正式推荐。';await page.route('**/api/agent/tasks/names-empty',route=>route.fulfill({json:{...match,id:'names-empty',recommendations:[],answer:history,demandProfile:null,opportunity:null}}));await page.goto('/tasks/names-empty');await expect(page.getByText('本次暂无推荐伙伴，请参考上方分析说明。',{exact:true})).toBeVisible();await expect(page.getByTestId('advisor-answer').locator('.advisor-answer-body')).toHaveText(history);expect(f.writes).toHaveLength(0);f.check();
});

test('recommendation labels: live analysis notices and task header describe generation',async({page})=>{
 const f=await setup(page);await page.route('**/api/agent/tasks?**',route=>route.fulfill({json:{items:[{...match,taskStatus:'matching'}],total:1,page:1,pageSize:20,totalPages:1}}));
 for(const [status,message] of [['matching','正在分析需求与伙伴资料，状态会自动更新。'],['enriching','伙伴推荐已生成，正在生成需求画像和项目机会。']]){await page.route('**/api/agent/tasks/names-match',route=>route.fulfill({json:{...match,taskStatus:status,recommendations:[],answer:'',demandProfile:null,opportunity:null}}));await page.goto('/tasks/names-match');await expect(page.getByText(message,{exact:true})).toBeVisible();}
 await page.goto('/tasks');await expect(page.locator('thead th').filter({hasText:/^首位推荐$/})).toBeVisible();await expect(page.locator('tbody')).toContainText('分析中');expect(f.writes).toHaveLength(0);f.check();
});

test('recommendation labels: admin totals and help retain development names and counts',async({page})=>{
 const f=await setup(page);await page.goto('/admin');const metric=page.locator('.admin-metric-card').filter({has:page.getByText('累计任务',{exact:true})});await expect(metric.locator('strong')).toHaveText('7');await expect(metric).toContainText('伙伴推荐 5 · 能力发展 2');await page.goto('/admin/demands');await expect(page.getByText('暂无需求画像，请先在 Agent 工作台生成一次伙伴推荐。',{exact:true})).toBeVisible();await page.goto('/admin/opportunities');await expect(page.getByRole('link',{name:'前往找伙伴',exact:true})).toBeVisible();expect(f.writes).toHaveLength(0);f.check();
});

test('recommendation labels: development source changes reference wording only',async({page})=>{
 const f=await setup(page);await page.route('**/api/enablement/context?**',route=>route.fulfill({json:{partner:{id:'names-partner',name:'合成伙伴'},project:{task_id:'names-source',requirement:raw,risk_status:'待能力发展流程复核',risk_notes:raw},shared_case:null,evidence:[]}}));await page.goto('/?mode=development&partner_id=names-partner&task_id=names-source');await expect(page.getByRole('tab',{name:'促发展',exact:true})).toHaveAttribute('aria-selected','true');const source=page.getByTestId('source-context');await source.locator('summary').click();await expect(source.getByRole('link',{name:'返回来源推荐任务',exact:true})).toHaveAttribute('href','/tasks/names-source');await expect(source.getByRole('heading',{name:'来源推荐的风险 / 缺口',exact:true})).toBeVisible();await expect(source).toContainText('待能力发展流程复核');await expect(source).toContainText(raw);expect(f.writes).toHaveLength(0);f.check();
});
