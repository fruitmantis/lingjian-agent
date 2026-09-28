import type {Page} from '@playwright/test';

const stamp = '2026-09-28T02:30:00Z';
export const partner = {id:'coze-partner',name:'远航数智（合成演示）',capabilities:'数据库迁移、系统集成',industries:'金融',service_areas:'广东',intro:'面向企业数字化项目提供系统集成与交付服务。',ai_profile:'已有数据库迁移与系统集成项目基础。建议先验证应用集成、数据质量和回退能力，再逐步扩展 Agent 交付场景。'};
const user = {id:'coze-user',username:'ui-review',display_name:'界面验收',role:'user',status:'active',must_change_password:false};
const roles = [{id:'role-1',name:'解决方案架构师'},{id:'role-2',name:'开发工程师'},{id:'role-3',name:'运维工程师'}];
const zones = [{id:'zone-1',name:'人工智能'},{id:'zone-2',name:'数据库'}];
const titles = ['企业级 Agent 应用设计与交付','数据库迁移与一致性验证','面向业务场景的系统集成','RAG 知识库工程实践','云上应用的可靠性设计','从验证到上线：项目交付方法'];
function resource(type:string, n=0) {return {source_type:type,source_id:`${type}-${n}`,source_version:1,title:titles[n],summary:'从真实业务问题出发，学习方案设计、验证方法与交付要点，建立可复用的项目实践。',roles:[roles[n%3]],zones:[zones[n%2]],level:n%2?'basic':'advanced',duration_minutes:90,source_url:'https://example.com/coze-ui',availability:'available',capabilities:[],category:'技术案例',subcategory:'架构设计',contributor_id:partner.id,contributor_name:partner.name,course_goals:'理解方案边界，掌握验证方法，形成完整的交付清单。',audience:'具备基础系统集成经验的工程师。',outline:'1. 需求与范围\n2. 方案设计与验证\n3. 交付与回退',lab_goals:'完成测试环境搭建与端到端验证。',lab_requirements:'准备独立实验环境与测试账号。'};}
const item = (n:number) => ({...resource('lab',n),item_id:`item-${n}`,reason:n?'验证数据一致性、异常处理与回退流程，为实际交付积累依据。':'先用小范围场景完成系统集成验证，再评估扩展范围。',conditions:{level:'advanced',duration_minutes:90,roles:[roles[0]],zones:[zones[0]]}});
export const plan = {plan:{id:'coze-plan',current_version_id:'v1',status:'active',active_run_id:null},partner_name:partner.name,request:{development_direction:'希望基于现有系统集成经验，逐步形成企业级 Agent 项目交付能力。优先安排可验证的实践。'},presentation:{state:'available',current_available:true,current_version:1},payload:{answer:'## 从系统集成基础出发，先完成小范围验证\n\n建议优先围绕已有交付经验，选择一个边界清晰的业务场景。先建立可验证的集成链路，再决定是否扩大技术范围。\n\n### 建议先做这两件事\n\n1. 明确接口、数据与交付边界，列出需要验证的关键假设。\n2. 用独立环境验证异常处理和回退流程，记录结果与待补充证据。\n\n现有资料能够支持发展方向的初步判断，但不能替代真实项目中的交付验证。',overview:{},stages:[{title:'实践',items:[item(0),item(1)]}],limitations:['资料不足不代表缺乏能力；以上建议仍需结合真实项目验证。'],resource_gaps:[]},hidden:false,notice:null,versions:[{id:'v1',version_no:1}],runs:[{id:'run-1',submission_id:'initial',run_type:'generate',status:'ready',created_at:stamp}],conversation:[] as {submission_id:string;message:string;answer:string}[]};
export const match = {id:'coze-match',task_type:'partner_match',requirement:'寻找有金融行业数据库迁移经验、能够在广东完成实施交付的伙伴。需要有可核对的案例与回退方案。',answer:'## 建议优先沟通远航数智\n\n当前资料显示，该伙伴在数据库迁移和系统集成方向与需求较为接近。建议先确认项目规模、现场支持和回退方案，再决定合作范围。\n\n以下推荐依据来自当前可访问的伙伴资料；缺失证据已单独标注。',taskStatus:'ready',createdAt:stamp,createdBy:'界面验收',archivedAt:null,demandProfile:{industryTags:'金融',capabilityTags:'数据库迁移、系统集成',regionTags:'广东',supplyStatus:'partial',gapAnalysis:'需要进一步确认现场资源与交付周期'},opportunity:null,recommendations:[{partnerId:partner.id,partnerName:partner.name,matchScore:'86',matchedCapabilities:'数据库迁移、系统集成',matchedIndustries:'金融',matchedRegions:'广东',recommendationReason:'已有相关交付经验，区域和技术方向较为匹配。',evidenceCases:'金融行业数据库迁移案例（合成）',evidenceDeliverables:'迁移验证报告、回退方案（合成）',riskNotes:'尚未确认现场可投入人员与项目规模；需进一步核对。'}]};

export async function fixture(page:Page) {
  const data=structuredClone(plan), requests:{path:string;method:string;body:any}[]=[],unexpected:string[]=[];
  await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-ui-only');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
  await page.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.port!=='8000'&&!url.pathname.startsWith('/api/')) {
      if(['localhost','127.0.0.1'].includes(url.hostname))return route.continue();
      if(url.hostname==='example.com')return route.fulfill({contentType:'text/html',body:'<h1>合成跳转目标</h1>'});
      unexpected.push(url.origin);return route.abort();
    }
    const p=url.pathname.replace(/^\/api/,'');requests.push({path:p+url.search,method:req.method(),body:req.postDataJSON()});
    let json:unknown;
    if(p==='/health')json={status:'ok'};
    else if(p==='/auth/me')json=user;
    else if(p==='/agent/tasks'&&req.method()==='POST')json={...match,id:req.postDataJSON().requestId};
    else if(p==='/agent/tasks')json={items:[{...match,topPartner:partner.name,partnerCount:1},{id:'coze-plan',task_type:'development_plan',requirement:'企业级 Agent 项目交付能力发展',taskStatus:'ready',createdAt:stamp,planPresentation:data.presentation}],total:2,page:1,pageSize:20,totalPages:1};
    else if(p==='/agent/tasks/coze-plan')json={id:'coze-plan',task_type:'development_plan',requirement:'企业级 Agent 项目交付能力发展',taskStatus:'ready',createdAt:stamp,planPresentation:data.presentation};
    else if(p.startsWith('/agent/tasks/'))json={...match,id:p.split('/').pop()};
    else if(p==='/development/plans'&&req.method()==='POST')json={plan_id:'coze-plan'};
    else if(p==='/development/plans/coze-plan/conversation') {data.conversation.push({...req.postDataJSON(),answer:'建议先对照接口清单，验证异常处理与回退。当前建议仍可使用。'});json={};}
    else if(p==='/development/plans/coze-plan')json=data;
    else if(p==='/partners')json=[partner];
    else if(p==='/enablement/context')json={partner:url.searchParams.get('partner_id')?partner:null,evidence:[{source_type:'case',source_id:'case-0',title:'系统集成交付案例（合成）'}],project:null,shared_case:null};
    else if(p==='/enablement/resource-filters')json={roles,zones};
    else if(p==='/enablement/resources')json={items:Array.from({length:6},(_,i)=>resource(url.searchParams.get('source_type')||'course',i)),total:6};
    else if(p.endsWith('/redirect'))json={url:'https://example.com/coze-ui'};
    else if(p.startsWith('/enablement/resources/'))json=resource(p.split('/')[3],Number(p.split('/')[4].split('-').pop()));
    else if(p.endsWith('/deliverables'))json=[];
    else {unexpected.push(p);return route.abort();}
    return route.fulfill({json});
  });
  return {requests,unexpected};
}
