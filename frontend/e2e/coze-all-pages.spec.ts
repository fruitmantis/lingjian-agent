import {test, expect, type Page} from '@playwright/test';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fixture, partner, match} from './coze-fixtures';

const phase=process.env.COZE_ALL_PHASE || 'after';
const root=path.resolve(process.env.COZE_ALL_EVIDENCE_DIR || '../artifacts/coze-all-pages');
// Historical screenshots stay local; ordinary regression must work in a fresh checkout.
const baseline=process.env.COZE_ALL_BASELINE_DIR;
const stamp='2026-09-28T02:30:00Z';
const admin={id:'ui-admin',username:'ui-admin',display_name:'合成管理员',role:'admin',status:'active',must_change_password:false,department:'合成部门',auth_methods:['password'],created_at:stamp};
const member={...admin,id:'ui-member',display_name:'合成用户',role:'user',auth_methods:['identity_key'],identity_key_hint:'bf_DE…MO123'};
const material={kind:'case',id:'case-0',partner_id:partner.id,partner_name:partner.name,title:'金融数据库迁移交付案例（合成）',description:'用于验证方案设计、实施交付与风险说明的展示效果。',category_id:'technical-3',visible:true,file_count:1,processing_status:'ready',updated_at:stamp,profile_needs_update:false};
const feedback={id:'feedback-1',submitter:'合成用户',description:'窄屏下需要检查表格滚动和卡片边框。\n这是合成的视觉验收内容。',status:'pending',created_at:stamp,attachments:[],attachment_count:0,summary:'卡片与滚动检查（合成）',screenshot_count:0};
const opportunity={id:'opportunity-1',matchRecordId:match.id,projectName:'金融数据库迁移项目（合成）',customerName:'合成客户',industry:'金融',region:'广东',projectStage:'方案评估',supplyStatus:'partial',completenessScore:70,requirementText:match.requirement,businessNeeds:'业务连续性',technicalNeeds:'数据一致性与回退验证',deliveryNeeds:'实施与培训',caseRequirements:'同类项目经验',recommendedPartnerNames:partner.name,followUpQuestions:JSON.stringify(['是否需要驻场？'])};
const demand={id:'demand-1',matchRecordId:match.id,requirementText:match.requirement,industryTags:'金融',capabilityTags:'数据库',regionTags:'广东',matchedPartnerCount:1,topPartnerNames:partner.name,supplyStatus:'partial',gapAnalysis:'现场支持待核实',createdAt:stamp};
const resource={source_id:'resource-1',revision:1,status:'published',published_version:1,system_visible:true,model_allowed:true,partner_allowed:false,metadata:{resource_type:'course',title:'企业级 Agent 交付课程（合成）',summary:'学习方案设计与验证方法。',source_url:'https://example.com/resource',role_ids:['role-1'],zone_ids:['zone-1'],level:'basic',course_goals:'明确交付边界与验证方法。',audience:'解决方案架构师',outline:'需求分析\n方案验证'},versions:[{version:1,published_at:stamp}]};
async function allPagesFixture(page:Page){
  const base=await fixture(page);
  const writes:string[]=[],unhandled:string[]=[];
  await page.addInitScript(admin=>{localStorage.setItem('banfei:admin:token','synthetic-admin');localStorage.setItem('banfei:admin:user',JSON.stringify(admin));},admin);
  await page.route(/https?:\/\/(localhost|127\.0\.0\.1):8000\//,async route=>{
    const req=route.request(),u=new URL(req.url()),p=u.pathname;
    if(req.method()!=='GET'){writes.push(p);return route.abort();}
    let json:any;
    if(p==='/auth/me')json=req.headers().authorization==='Bearer synthetic-admin'?admin:member;
    else if(p==='/auth/identity/key')json={key:'SYNTHETIC-NOT-A-CREDENTIAL'};
    else if(p==='/partners/profiles'||p==='/partners')json=[{...partner,status:'active',created_at:stamp,case_count:1,deliverable_count:1}];
    else if(p===`/partners/${partner.id}`)json={...partner,status:'active',created_at:stamp};
    else if(p.endsWith('/documents'))json=[];
    else if(p==='/cases/case-0/deliverables')json=[{id:'file-1',filename:'验证材料.txt',processing_status:'ready',file_size:200,content_type:'text/plain',created_at:stamp}];
    else if(p==='/admin/partner-materials')json={items:[material,{...material,id:'case-1',title:'系统集成验证材料（合成）'},{...material,id:'case-2',title:'交付与回退清单（合成）'}],total:3,partners:[partner]};
    else if(p==='/admin/dashboard')json={users:8,partners:12,tasks:20,monthTasks:6,partnerMatchTasks:12,developmentTasks:8};
    else if(p==='/admin/demand-profiles')json={profiles:[demand],overview:{totalDemands:1,thisMonthDemands:1,gapDemandCount:1,avgPartnerCount:1,topCapabilityTags:'数据库'},industryDistribution:{金融:1},capabilityDistribution:{数据库:1},regionDistribution:{广东:1},deliveryTypeDistribution:{实施:1}};
    else if(p==='/admin/opportunities')json=[opportunity];
    else if(p==='/admin/reports')json={overview:{totalDemands:1,thisMonthDemands:1,totalPartners:12,partnersWithProfile:9,activePartners:8,noPartnerDemands:0,partialDemands:1,pendingSuggestions:0},capabilityDist:[{name:'数据库',count:1}],industryDist:[],regionDist:[],deliveryTypeDist:[],supplyGaps:[],activePartnerCount:8,activePartnerRatio:0.67,topRecommendedPartners:[],inactivePartners:[],topFormalTags:[],uncoveredClues:0,pendingSuggestions:0};
    else if(p==='/admin/model-configs')json=[{id:'model-1',name:'界面验收配置',provider:'合成供应商',modelName:'example-model',maxTokens:8192,baseUrl:'https://example.com/v1',apiKeyConfigured:true,enabled:true,isDefault:true}];
    else if(p==='/admin/model-configs/timeout-settings')json={timeoutSeconds:300,timeoutRetries:3};
    else if(p==='/admin/model-configs/usage')json=[{sceneKey:'partner_matching',sceneName:'伙伴匹配',modelConfigId:'model-1',modelConfigName:'界面验收配置'}];
    else if(p==='/admin/enablement/resources')json=[resource];
    else if(p==='/admin/enablement/resources/resource-1')json=resource;
    else if(p==='/admin/enablement/resource-categories')json=[{id:'role-1',kind:'role',name:'架构师',sort_order:0},{id:'zone-1',kind:'zone',name:'人工智能',sort_order:0}];
    else if(p==='/admin/capability-tags')json=[{id:'tag-1',name:'数据库',enabled:true,category:'技术能力',description:'数据库交付与迁移',sortOrder:1}];
    else if(p==='/admin/capability-tags/categories')json=[{id:'category-1',name:'技术能力',enabled:true,sortOrder:0}];
    else if(p==='/admin/capability-tags/suggestions')json={items:[],total:0};
    else if(p==='/admin/users')json={items:[member,{...admin,id:'admin-other'}],total:2,page:1};
    else if(p==='/admin/users/ui-member')json=member;
    else if(p==='/admin/user-audit-logs')json={items:[],total:0};
    else if(p==='/admin/feedback')json={items:[feedback],total:1};
    else if(p==='/admin/feedback/feedback-1')json=feedback;
    else if(p==='/admin/system/status')json={overallStatus:'normal',checkedAt:stamp,summary:{normalCount:4,warningCount:0,errorCount:0,unknownCount:0,abnormalModules:[]},services:[{name:'服务',status:'normal',message:'合成检查结果'}],database:[{name:'数据库',status:'normal',message:'合成只读结果'}],llm:[{name:'模型配置',status:'unknown',message:'未发送模型请求'}],businessCapabilities:[]};
    else if(p==='/admin/system/errors')json={items:[],total:0};
    else if(p==='/admin/tasks')json={items:[{...match,topPartner:partner.name,partnerCount:1}],total:1,page:1,pageSize:20,totalPages:1};
    else return route.fallback();
    return route.fulfill({json});
  });
  return {base,writes,unhandled};
}

const routes=[
['home','/','.assistant-composer'],['development','/?mode=development','.development-composer'],['scenes','/scenes','.scene-gallery-card'],['partners','/partners','.partner-insight-card'],['partner-detail','/partners/coze-partner','.card'],['tasks','/tasks','.data-table'],['task-answer','/tasks/coze-plan','.advisor-answer'],['task-match','/tasks/coze-match','.recommendation-item'],['resources','/resources','.learning-card'],['resource-detail','/resources/course/course-0','.learning-content'],['account','/account','.card'],['feedback','/feedback','.feedback-form'],
['admin-home','/admin','.admin-metric-grid'],['admin-tasks','/admin/tasks','.data-table'],['admin-task-detail','/admin/tasks/coze-match','.recommendation-item'],['admin-partners','/admin/partners','.card'],['admin-partner-detail','/admin/partners/coze-partner','.card'],['admin-materials','/admin/partner-materials','.ui-catalog-card'],['admin-demands','/admin/demands','.card'],['admin-opportunities','/admin/opportunities','.data-table'],['admin-reports','/admin/reports','.ui-report-metrics'],['admin-resources','/admin/resources','.card'],['admin-tags','/admin/tags','.data-table'],['admin-users','/admin/users','.data-table'],['admin-user-detail','/admin/users/ui-member','.card'],['admin-models','/admin/models','.data-table'],['admin-system','/admin/system','.card'],['admin-feedback','/admin/feedback','.feedback-table-wrap'],['admin-feedback-detail','/admin/feedback/feedback-1','.feedback-form'],['admin-account','/admin/account','.card'],
];
for(const [width,height] of [[1366,768],[1920,1080],[390,844]])test(`all page visual coverage ${width}`,async({page,context})=>{
  await page.setViewportSize({width,height});await page.clock.setFixedTime(new Date(stamp));
  const {base,writes}=await allPagesFixture(page);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setPageScaleFactor',{pageScaleFactor:1});
  const dir=path.join(root,phase);await mkdir(dir,{recursive:true});const measurements:any[]=[];
  async function capture(name:string,crop:string){
    await page.waitForLoadState('networkidle');await page.evaluate(()=>document.fonts.ready);await page.addStyleTag({content:'nextjs-portal{display:none}'});await page.evaluate(()=>scrollTo(0,0));
    await expect(page.locator(crop).first(),name).toBeVisible();
    const data=await page.evaluate(()=>({text:document.querySelector('main')?.textContent,width:innerWidth,height:innerHeight,zoom:visualViewport?.scale,scrollWidth:document.documentElement.scrollWidth,sidebar:document.querySelector('.sidebar')?.getBoundingClientRect().width,overflow:[...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&!e.closest('.table-wrap,[class*=tableWrap],.feedback-table-wrap')).slice(0,10).map(e=>e.tagName+'.'+e.className)}));
    expect(data.zoom).toBe(1);
    if(phase==='after'){
      expect(data.scrollWidth,`${name}: document overflow ${JSON.stringify(data.overflow)}`).toBeLessThanOrEqual(width);
      if(baseline){const before=JSON.parse(await readFile(path.join(baseline,`${name}-${width}.json`),'utf8'));expect(data.text,`${name}: same content`).toBe(before.text);}
      if(data.sidebar && width>820)expect(data.sidebar).toBe(230);
    }
    const mask=[page.locator('.identity-key-value'),page.locator('input[type=password]')];
    await page.screenshot({path:path.join(dir,`${name}-${width}.png`),mask});
    await page.locator(crop).first().screenshot({path:path.join(dir,`${name}-${width}-detail.png`),mask});
    await writeFile(path.join(dir,`${name}-${width}.json`),JSON.stringify(data,null,2));measurements.push({name,...data,text:undefined});
  }
  for(const [name,url,crop] of routes){
    if(process.env.COZE_ROUTE_FILTER && name!==process.env.COZE_ROUTE_FILTER)continue;
    await page.goto(url);await capture(name,crop);
    if(name==='admin-materials'){
      await page.getByRole('button',{name:'查看与管理',exact:true}).first().click();await capture('material-dialog','[role=dialog]');if(phase==='after'){const close=await page.getByRole('button',{name:'关闭',exact:true}).boundingBox();expect(close!.height).toBeLessThanOrEqual(44);}await page.getByRole('button',{name:'关闭',exact:true}).click();
      await page.getByRole('button',{name:'新增资料',exact:true}).click();await capture('material-editor','[role=dialog]');await page.getByRole('button',{name:'关闭',exact:true}).click();
    }
    if(name==='admin-opportunities'){await page.getByRole('button',{name:'详情',exact:true}).click();await capture('opportunity-expanded','section[aria-label="项目详情"]');await page.getByRole('button',{name:'收起',exact:true}).click();}
    if(name==='admin-users'){await page.getByRole('button',{name:'编辑',exact:true}).first().click();await capture('user-dialog','.modal-card');await page.getByRole('button',{name:'取消',exact:true}).click();}
    if(name==='admin-resources'){await page.getByRole('button',{name:'管理资源',exact:true}).click();await capture('resource-editor','.card');}
    if(phase==='after'&&width===390 && name==='admin-home'){
      await page.getByRole('button',{name:'展开导航'}).click();await page.getByRole('navigation',{name:'后台导航'}).getByRole('link',{name:'系统状态',exact:true}).click();await expect(page).toHaveURL(/\/admin\/system$/);await expect(page.getByRole('button',{name:'展开导航'})).toBeVisible();
    }
    if(phase==='after'&&name==='admin-models')await expect(page.getByRole('link',{name:'后台概览',exact:true,includeHidden:true})).not.toHaveAttribute('aria-current','page');
  }
  // Standalone pages use a signed-out synthetic browser state. No identity creation.
  await page.addInitScript(()=>{localStorage.clear();localStorage.setItem('banfei:user:signed-out','1');if(location.pathname==='/403'){localStorage.removeItem('banfei:user:signed-out');localStorage.setItem('banfei:user:token','synthetic-ui-only');}});
  await page.route('**/auth/identity/session',r=>r.fulfill({status:401,json:{detail:'合成未登录状态'}}));
  for(const [name,url,crop] of [['login','/login?method=key','.login-card'],['admin-login','/admin/login','.login-card'],['forbidden','/403','.public-state-card']]){await page.goto(url);await capture(name,crop);}
  expect(errors).toEqual([]);expect(writes).toEqual([]);expect(base.requests.filter(r=>r.method!=='GET')).toEqual([]);expect(base.unexpected).toEqual([]);
  await writeFile(path.join(dir,`summary-${process.env.COZE_ROUTE_FILTER ? "targeted-" : ""}${width}.json`),JSON.stringify(measurements,null,2));
});
