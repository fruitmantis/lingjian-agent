import {test,expect,type Page} from '@playwright/test';
import {mockDeviceSession} from './device-session-fixture';

async function setup(page:Page){
 const user={id:'cert-ui-owner',username:'cert-ui-owner',display_name:'合成用户',role:'user',status:'active',must_change_password:false};
 const unexpected:string[]=[],errors:string[]=[];
 await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-cert-token');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
 page.on('pageerror',error=>errors.push(error.message));
 const base={matchScore:'90',matchedCapabilities:'数据库',matchedIndustries:'',matchedRegions:'',recommendationReason:'正式能力认证支持接洽；具体项目交付范围需结合现有资料。',evidenceCases:'',evidenceDeliverables:'',riskNotes:''};
 const task={id:'cert-task',task_type:'partner_match',requirement:'合成数据库工作需求',createdAt:'2026-11-04T00:00:00Z',createdBy:'合成用户',archivedAt:null,taskStatus:'ready',demandProfile:null,opportunity:null,lastErrorStage:null,answer:'按本次项目适配度推荐。',recommendations:[
  {...base,partnerId:'service',partnerName:'合成项目适配伙伴',matchScore:'95',recommendationReason:'相似项目资料支持该团队承担迁移工作。',evidenceCases:'合成迁移项目',certification:{capabilityTags:[],relatedCapabilityTags:[],servicePartnerBasis:'identity',identities:['服务合作伙伴','云经销商']}},
  {...base,partnerId:'cert',partnerName:'合成专项认证伙伴',matchScore:'85',certification:{capabilityTags:['数据库','容器'],relatedCapabilityTags:['数据库'],servicePartnerBasis:'capability_tag',identities:[]}},
  {...base,partnerId:'plain',partnerName:'合成资料伙伴',certification:{capabilityTags:[],relatedCapabilityTags:[],servicePartnerBasis:null,identities:[]}},
  {...base,partnerId:'legacy',partnerName:'历史推荐伙伴'}]};
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname.replace(/^\/api/,'');
  if(path==='/auth/me')return route.fulfill({json:user});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/agents')return route.fulfill({json:[]});
  if(path==='/agent/tasks')return route.fulfill({json:{items:[],total:0,page:1,pageSize:10,totalPages:1}});
  if(path==='/agent/tasks/cert-task')return route.fulfill({json:task});
  unexpected.push(route.request().method()+' '+path);return route.fulfill({status:404,json:{detail:'Undefined synthetic fixture'}});
 });
 await mockDeviceSession(page);await page.goto('/tasks/cert-task');
 await expect(page.getByRole('heading',{name:'任务详情',exact:true})).toBeVisible();
 return {unexpected,errors};
}

for(const width of [1440,390])test(`certification snapshot and legacy cards stay distinct at ${width}`,async({page},info)=>{
 await page.setViewportSize({width,height:1000});const state=await setup(page);
 const cards=page.locator('.recommendation-item');await expect(cards).toHaveCount(4);
 await expect(cards.nth(0)).toContainText('合成项目适配伙伴');
 await expect(cards.nth(0)).toContainText('未记录本次相关能力认证');
 await expect(cards.nth(0)).toContainText('已维护服务合作伙伴身份');
 await expect(cards.nth(0)).toContainText('服务合作伙伴、云经销商');
 await expect(cards.nth(0)).toContainText('合成迁移项目');
 const formal=cards.nth(1).getByTestId('recommendation-certification');
 await expect(formal).toContainText('相关能力认证数据库');
 await expect(formal).toContainText('正式能力认证：数据库、容器');
 await expect(formal).not.toContainText('暂未维护');
 await expect(formal).not.toContainText('伙伴身份');
 await expect(cards.nth(1).getByRole('heading',{name:'支撑案例'})).toHaveCount(0);
 await expect(cards.nth(2).getByTestId('recommendation-certification')).toContainText('未记录本次相关能力认证');
 await expect(cards.nth(2).getByTestId('recommendation-certification')).not.toContainText('服务伙伴依据');
 await expect(cards.nth(3).getByTestId('recommendation-certification')).toHaveCount(0);
 await expect(cards.nth(3)).toContainText('相关能力数据库');
 await expect(page.getByText('没有能力',{exact:true})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.evaluate(()=>document.fonts.ready);
 await cards.nth(0).screenshot({path:info.outputPath('service-'+width+'.png')});
 await cards.nth(1).screenshot({path:info.outputPath('certified-'+width+'.png')});
 expect(state.unexpected).toEqual([]);expect(state.errors).toEqual([]);
});
