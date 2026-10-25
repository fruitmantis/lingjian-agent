import {test,expect,type Page} from '@playwright/test';
import {mockDeviceSession} from './device-session-fixture';

async function fixture(page:Page,{supported=true,empty=false,capacity=null,admin=true}:{supported?:boolean;empty?:boolean;capacity?:number|null;admin?:boolean}={}){
 const user={id:'capacity-synthetic-user',username:'capacity-qa',display_name:'容量合成测试',role:admin?'admin':'user',status:'active',must_change_password:false};
 await page.addInitScript(({user,admin})=>{localStorage.setItem(`banfei:${admin?'admin':'user'}:token`,'synthetic-capacity-token');localStorage.setItem(`banfei:${admin?'admin':'user'}:user`,JSON.stringify(user));},{user,admin});
 const stamp='2026-10-25T12:00:00Z';
 const provider={id:'provider-capacity',name:'合成提供商',baseUrl:'https://synthetic.invalid/v1',protocol:'openai_chat_completions',apiKeyConfigured:true,apiKeySource:'db',modelCount:empty?0:1,updatedAt:stamp};
 const models:any[]=empty?[]:[{id:'model-capacity',providerId:provider.id,providerName:provider.name,name:'合成容量模型',modelName:'synthetic-model',temperature:0.2,topP:0.8,maxTokens:131072,enabled:true,userSelectable:true,defaultBindings:['partner_match'],updatedAt:stamp,...(supported?{contextWindowTokens:capacity}:{})}];
 const options={modelConfigId:'model-capacity',thinking:true,timeoutSeconds:300,timeoutRetries:3};
 const settings={agents:{partner_match:{...options,name:'伙伴推荐',description:'找伙伴',icon:'users',enabled:true},partner_development:{...options,name:'伙伴发展',description:'促发展',icon:'trend',enabled:true}},processing:{...options}};
 const state={saves:[] as any[],tests:0,errors:[] as string[],posts:[] as string[]};
 page.on('pageerror',error=>state.errors.push(error.message));
 await page.route('**/api/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname.replace(/^\/api/,'');
  if(request.method()==='POST')state.posts.push(path);
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/auth/me')return route.fulfill({json:user});
  if(path==='/agents')return route.fulfill({json:Object.entries(settings.agents).map(([id,value])=>({id,...value}))});
  if(path==='/admin/agents')return route.fulfill({json:settings});
  if(path==='/admin/model-providers')return route.fulfill({json:[provider]});
  if(path==='/admin/model-configs'&&request.method()==='GET')return route.fulfill({headers:supported?{'X-Model-Context-Window':'tokens'}:{},json:models});
  if(path.startsWith('/admin/model-configs')&&(request.method()==='PUT'||path==='/admin/model-configs'&&request.method()==='POST')){
   const body=request.postDataJSON();state.saves.push(body);
   if(!supported&&'contextWindowTokens' in body)return route.fulfill({status:422,json:{detail:'extra field forbidden'}});
   if(supported&&(request.method()==='POST'||'contextWindowTokens' in body)&&(!Number.isInteger(body.contextWindowTokens)||body.contextWindowTokens<=0||body.contextWindowTokens>2147483647))return route.fulfill({status:422,json:{detail:'capacity required'}});
   let model=models.find(m=>m.id===path.split('/')[3]);
   if(!model){model={id:'new-model',defaultBindings:[],updatedAt:stamp};models.push(model);}
   Object.assign(model,body);return route.fulfill({status:request.method()==='POST'?201:200,json:model});
  }
  if(path.endsWith('/test')){state.tests++;return route.fulfill({json:{success:true,message:'合成 JSON 校验通过',latencyMs:12}});}
  if(path==='/model-timeout-settings')return route.fulfill({json:{timeoutSeconds:300,timeoutRetries:3}});
  if(path==='/agent/tasks')return route.fulfill({json:{items:[],total:0,page:1,pageSize:10,totalPages:1}});
  if(path==='/agent/tasks/capacity-failed')return route.fulfill({json:{id:'capacity-failed',task_type:'partner_match',requirement:'  合成容量需求，保留原文。  ',createdAt:stamp,taskStatus:'failed',archivedAt:null,recommendations:[],answer:'',understanding:null,progress:null,opportunity:null,demandProfile:null,lastErrorStage:'understanding',modelSelection:{id:'model-capacity',name:'合成容量模型'},failureDetails:[{stage:'understanding',stageLabel:'需求理解',code:'context_capacity',message:'untrusted exception must not be displayed',action:'返回并切换模型',modelRelated:true}]}});
  state.errors.push(request.method()+' '+path);return route.fulfill({status:404,json:{detail:'undefined synthetic endpoint'}});
 });
 await mockDeviceSession(page);
 await page.route('**/api/agents/*/models',route=>route.fulfill({json:{models:models.map(m=>({id:m.id,name:m.name,isDefault:true,providerId:m.providerId,providerName:provider.name})),defaultModelConfigId:'model-capacity',agentEnabled:true,unavailableReason:null}}));
 return state;
}

async function openModel(page:Page){
 await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 await page.getByRole('article',{name:'合成容量模型',exact:true}).getByRole('button',{name:'编辑',exact:true}).click();
 await page.getByText('高级参数',{exact:false}).click();
}

for(const width of [1440,390])test('capacity and maximum output keep distinct fields and fit viewport '+width,async({page})=>{
 const state=await fixture(page);await page.setViewportSize({width,height:1000});await openModel(page);
 const capacity=page.getByLabel('总上下文容量（Token）',{exact:true}),output=page.getByLabel('最大输出（Token）',{exact:true});
 await expect(capacity).toHaveValue('');await expect(capacity).toHaveAttribute('placeholder','待填写');await expect(output).toHaveValue('131072');
 const left=await capacity.boundingBox(),right=await output.boundingBox();expect(left).not.toBeNull();expect(right).not.toBeNull();
 if(width>600){expect(left!.y).toBe(right!.y);expect(left!.x+left!.width).toBeLessThan(right!.x);}else expect(left!.y+left!.height).toBeLessThan(right!.y);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:test.info().outputPath('capacity-dual-fields-'+width+'.png'),fullPage:true});
 await page.getByLabel('显示名称',{exact:true}).fill('旧模型普通编辑');await page.getByRole('button',{name:'保存模型',exact:true}).click();
 await expect.poll(()=>state.saves.length).toBe(1);expect(state.saves[0].contextWindowTokens).toBeUndefined();expect(state.saves[0].maxTokens).toBe(131072);
 await capacity.fill('262144');await expect(output).toHaveValue('131072');await page.getByRole('button',{name:'保存模型',exact:true}).click();
 await expect.poll(()=>state.saves.length).toBe(2);expect(state.saves[1]).toMatchObject({contextWindowTokens:262144,maxTokens:131072});
 expect(state.tests).toBe(0);expect(state.errors).toEqual([]);
});

test('new model requires explicit positive capacity including an empty new API model list',async({page})=>{
 const state=await fixture(page,{empty:true});await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 await page.getByRole('button',{name:'＋ 添加模型',exact:true}).click();await page.getByLabel('显示名称',{exact:true}).fill('新增合成容量模型');await page.getByLabel('模型 ID',{exact:true}).fill('synthetic-new');
 await page.getByText('高级参数',{exact:false}).click();const capacity=page.getByLabel('总上下文容量（Token）',{exact:true});await expect(capacity).toBeEnabled();
 for(const value of ['', '0', '1.5']){await capacity.fill(value);await page.getByRole('button',{name:'保存模型',exact:true}).click();expect(state.saves).toHaveLength(0);}
 await capacity.fill('131072');await page.getByRole('button',{name:'保存模型',exact:true}).click();
 await expect.poll(()=>state.saves.length).toBe(1);expect(state.saves[0]).toMatchObject({contextWindowTokens:131072,maxTokens:131072});expect(state.tests).toBe(0);expect(state.errors).toEqual([]);
});

test('new model reveals required capacity when saving from collapsed advanced parameters',async({page})=>{
 const state=await fixture(page,{empty:true});await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();
 await page.getByRole('button',{name:'＋ 添加模型',exact:true}).click();await page.getByLabel('显示名称',{exact:true}).fill('需要填写容量');await page.getByLabel('模型 ID',{exact:true}).fill('synthetic-explicit-capacity');
 await page.getByRole('button',{name:'保存模型',exact:true}).click();
 await expect(page.getByLabel('总上下文容量（Token）',{exact:true})).toBeVisible();expect(state.saves).toHaveLength(0);expect(state.tests).toBe(0);expect(state.errors).toEqual([]);
});

test('changing capacity invalidates saved test and does not clamp maximum output in configuration',async({page})=>{
 const state=await fixture(page,{capacity:262144});await openModel(page);
 await page.getByRole('button',{name:'测试连接',exact:true}).click();await expect(page.getByText('本次测试通过',{exact:true})).toBeVisible();expect(state.tests).toBe(1);
 const capacity=page.getByLabel('总上下文容量（Token）',{exact:true});await capacity.fill('1048576');await expect(page.getByText('配置已变更',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'测试连接',exact:true})).toBeDisabled();
 await page.getByLabel('最大输出（Token）',{exact:true}).fill('131072');await page.getByRole('button',{name:'保存模型',exact:true}).click();await expect.poll(()=>state.saves.length).toBe(1);
 expect(state.saves[0]).toMatchObject({contextWindowTokens:1048576,maxTokens:131072});expect(state.tests).toBe(1);
 await capacity.fill('');await page.getByRole('button',{name:'保存模型',exact:true}).click();expect(state.saves).toHaveLength(1);expect(state.errors).toEqual([]);
});

test('old API remains editable without sending unsupported capacity or claiming activation',async({page})=>{
 const state=await fixture(page,{supported:false});await openModel(page);const capacity=page.getByLabel('总上下文容量（Token）',{exact:true});
 await expect(capacity).toBeDisabled();await expect(capacity).toHaveValue('');await expect(page.getByText('当前后端尚不支持容量配置，其他模型设置仍可编辑。',{exact:true})).toBeVisible();
 await page.getByLabel('显示名称',{exact:true}).fill('旧接口仍可编辑');await page.getByRole('button',{name:'保存模型',exact:true}).click();
 await expect.poll(()=>state.saves.length).toBe(1);expect(state.saves[0].contextWindowTokens).toBeUndefined();expect(state.saves[0].maxTokens).toBe(131072);expect(state.tests).toBe(0);expect(state.errors).toEqual([]);
});

test('missing capacity uses safe fixed message and existing return with raw demand and provider menu',async({page})=>{
 const state=await fixture(page,{admin:false});await page.goto('/tasks/capacity-failed');
 await expect(page.getByText('该模型尚未配置总上下文容量，请管理员填写后重试，或返回切换模型。',{exact:true})).toBeVisible();await expect(page.getByText('untrusted exception must not be displayed',{exact:false})).toHaveCount(0);
 await page.getByRole('button',{name:'返回并切换模型',exact:true}).click();await expect(page.locator('#requirement')).toHaveValue('  合成容量需求，保留原文。  ');
 await expect(page.getByRole('menuitem',{name:/^合成提供商/})).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'选择模型：合成容量模型'})).toBeVisible();
 expect(state.posts.filter(path=>path!=='/auth/identity/session')).toEqual([]);expect(state.tests).toBe(0);expect(state.errors).toEqual([]);
});


for(const width of [1440,390])for(const method of ['post','put'])test('capacity INTEGER boundary '+method+' '+width,async({page})=>{
 const state=await fixture(page,{empty:method==='post',capacity:262144});await page.setViewportSize({width,height:1000});
 if(method==='post'){
  await page.goto('/admin/models');await page.getByRole('tab',{name:'模型提供商',exact:true}).click();await page.getByRole('button',{name:'＋ 添加模型',exact:true}).click();
  await page.getByLabel('显示名称',{exact:true}).fill('合成整数边界模型');await page.getByLabel('模型 ID',{exact:true}).fill('synthetic-integer-boundary');await page.getByText('高级参数',{exact:false}).click();
 }else await openModel(page);
 const capacity=page.getByLabel('总上下文容量（Token）',{exact:true}),output=page.getByLabel('最大输出（Token）',{exact:true});
 await expect(capacity).toHaveAttribute('min','1');await expect(capacity).toHaveAttribute('max','2147483647');await expect(capacity).toHaveAttribute('step','1');
 await expect(page.getByText('总上下文容量包含输入与输出，请按当前接入服务的实际容量填写（1～2147483647 的整数）。',{exact:true})).toBeVisible();
 await capacity.fill('2147483648');expect(await capacity.evaluate(element=>(element as HTMLInputElement).validity.rangeOverflow)).toBe(true);
 await page.getByRole('button',{name:'保存模型',exact:true}).click();await expect(capacity).toBeFocused();expect(state.saves).toHaveLength(0);
 await capacity.fill('2147483647');expect(await capacity.evaluate(element=>(element as HTMLInputElement).checkValidity())).toBe(true);
 await expect(output).toHaveValue('131072');await page.getByRole('button',{name:'保存模型',exact:true}).click();
 await expect.poll(()=>state.saves.length).toBe(1);expect(state.saves[0]).toMatchObject({contextWindowTokens:2147483647,maxTokens:131072});
 await expect(capacity).toHaveValue('2147483647');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:test.info().outputPath('capacity-integer-boundary-'+method+'-'+width+'.png'),fullPage:true});
 expect(state.tests).toBe(0);expect(state.errors).toEqual([]);
});
