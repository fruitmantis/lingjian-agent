import {expect,test} from '@playwright/test';

for (const kind of ['match','development'] as const) {
 test(`${kind}: accepted task selects itself and restores input, stages, results and elapsed time`,async({page},testInfo)=>{
  await page.setViewportSize({width:1366,height:768});
  const user={id:'progress-user',username:'progress-user',display_name:'合成验收用户',role:'user',status:'active',must_change_password:false};
  await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-progress-token');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
  const original='  数据库迁移与回退验证\n完整保留第二行需求。  ';let id=`progress-${kind}`;
  const started=Date.now()-20_000;
  const time=(seconds:number)=>new Date(started+seconds*1000).toISOString();
  let accepted=false,phase=0;
  const errors:string[]=[],writes:any[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  const keys=kind==='match'?['understanding','initial_selection','detailed_review','enrichment']:['understanding','retrieval','generation'];
  const labels=kind==='match'?['理解项目需求','寻找合适伙伴','形成伙伴推荐','完善项目分析']:['分析发展方向','查找学习资源','形成发展建议'];
  function progress(){return {run_id:'progress-run',started_at:time(0),finished_at:phase===2?time(60):null,stages:keys.map((key,i)=>({key,label:labels[i],status:phase===0?(i===0?'running':'pending'):phase===1?(i===0?'completed':i===1?'running':'pending'):kind==='match'&&i===3?'failed':'completed',started_at:i===0?time(1):phase>0&&i===1?time(10):phase===2?time(i*10):null,finished_at:phase>0&&i===0?time(10):phase===2?time(i===keys.length-1?60:(i+1)*10):null}))};}
  function summary(){return {id,requirement:original,createdAt:time(0),taskStatus:phase===2?(kind==='match'?'partial':'ready'):'matching',task_type:kind==='match'?'partner_match':'development_plan',archivedAt:null};}
  function matchDetail(){return {...summary(),progress:progress(),understanding:phase?{technicalNeeds:'数据库迁移与回退验证'}:null,answer:phase===2?'已保存的伙伴推荐依据。':'',recommendations:phase===2?[{partnerId:'partner-1',partnerName:'合成伙伴',matchScore:'80',matchedCapabilities:'数据库',matchedIndustries:'金融',matchedRegions:'北京市',recommendationReason:'已核验的合成证据',evidenceCases:'',evidenceDeliverables:'',riskNotes:'交付排期需核实'}]:[],opportunity:null,demandProfile:null,failureDetails:phase===2?[{stage:'persistence',code:'unknown',message:'本次处理失败，请重试。'}]:[]};}
  function developmentDetail(){return {progress:progress(),executionInput:original,analysis:phase?{interpretation:'从已有交付基础分析发展方向。',partner_assessment:'现有资料提供数据库经验。',priorities:[],basis_limitations:[]}:null,plan:{id,current_version_id:phase===2?'version-1':null,status:'active',active_run_id:phase===2?null:'progress-run'},presentation:{state:phase===2?'available':'generating',current_available:phase===2,latest_run_status:phase===2?'ready':'running',latest_run_type:'generate'},partner_name:'合成伙伴',request:{raw_demand:original,development_direction:original},conversation:[],payload:phase===2?{answer:'已校验并保存的发展建议。',overview:{development_direction:original},stages:[],limitations:[],resource_gaps:[]}:null,hidden:false,notice:null,versions:phase===2?[{id:'version-1',version_no:1}]:[],runs:[{id:'progress-run',submission_id:'progress-submission',run_type:'generate',status:phase===2?'ready':'running',created_at:time(0),safe_error_message:null}],failureDetails:[]};}
  await page.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url()),path=url.pathname.replace(/^\/api/,'');
   if(req.method()==='POST'&&(path==='/agent/tasks'||path==='/development/plans')){
    writes.push(req.postDataJSON());accepted=true;if(kind==='match')id=req.postDataJSON().requestId;
    return route.fulfill({status:202,json:kind==='match'?{recordId:id,runId:'progress-run',taskStatus:'matching'}:{plan_id:id,run_id:'progress-run',task_type:'development_plan'}});
   }
   const json=path==='/auth/me'?user:path==='/health'?{status:'ok'}:path==='/partners'?[{id:'partner-1',name:'合成伙伴'}]:path==='/enablement/context'?{partner:{id:'partner-1',name:'合成伙伴',intro:'合成资料'},project:null,shared_case:null,evidence:[]}:path==='/agent/tasks'?{items:accepted?[summary()]:[],total:accepted?1:0,page:1,pageSize:20,totalPages:1}:path===`/agent/tasks/${id}`?kind==='match'?matchDetail():summary():path===`/development/plans/${id}`?developmentDetail():null;
   if(json===null){errors.push(req.method()+' '+path);return route.fulfill({status:404,json:{detail:'Unlisted synthetic endpoint'}});}
   return route.fulfill({json});
  });
  await page.goto(kind==='match'?'/':'/?mode=development&partner_id=partner-1');
  await page.locator(kind==='match'?'#requirement':'textarea[aria-label="发展方向"]').fill(original);
  await page.getByRole('button',{name:kind==='match'?'开始匹配':'生成能力发展建议',exact:true}).click();
  await expect(page).toHaveURL(new RegExp(`/tasks/${id}$`));
  await expect(page.locator(`.sidebar-task-item[href="/tasks/${id}"]`)).toHaveAttribute('aria-current','page');
  await expect(page.locator('aside').getByRole('link',{name:'全部任务',exact:true})).toHaveAttribute('aria-current','page');
  const input=page.locator('.task-request-compact p');
  await expect(input).toHaveText(original);
  expect(await input.textContent()).toBe(original);
  await expect(input).toHaveCSS("white-space","pre-wrap");
  expect(kind==='match'?writes[0].requirement:writes[0].request.development_direction).toBe(original);
  await expect(page.getByTestId('task-progress').locator('[data-stage="understanding"]')).toHaveAttribute('data-status','running');
  await expect(page.getByTestId('task-elapsed')).toContainText('本次已用时间');
  await page.reload();
  await expect(input).toHaveText(original);
  phase=1;
  await expect(page.getByTestId(kind==='match'?'task-understanding':'development-analysis')).toBeVisible({timeout:12_000});
  await expect(page.getByTestId('task-progress').locator('[data-stage="understanding"]')).toContainText('已完成 · 9 秒');
  if(kind==='development')await expect(page.getByTestId('advisor-main-answer')).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId(kind==='match'?'task-understanding':'development-analysis')).toBeVisible();
  phase=2;
  await expect(page.getByTestId('task-elapsed')).toHaveText('本次已用时间：1 分 0 秒',{timeout:12_000});
  await expect(page.getByText(kind==='match'?'已保存的伙伴推荐依据。':'已校验并保存的发展建议。',{exact:true})).toBeVisible();
  await page.waitForTimeout(1200);
  await expect(page.getByTestId('task-elapsed')).toHaveText('本次已用时间：1 分 0 秒');
  await page.reload();
  await expect(page.getByTestId('task-elapsed')).toHaveText('本次已用时间：1 分 0 秒');
  for(const width of [1366,1920,390]){
   await page.setViewportSize({width,height:width===1920?1080:768});
   await page.evaluate(()=>document.fonts.ready);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
   await page.screenshot({path:testInfo.outputPath(`${kind}-${width}.png`),fullPage:true});
  }
  expect(errors).toEqual([]);expect(writes).toHaveLength(1);
 });
}
