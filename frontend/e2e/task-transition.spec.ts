import {test,expect,type Page} from '@playwright/test';

type Kind='match'|'development';
const draft='  寻找能够支撑企业知识库项目的伙伴，具备实施交付经验。\n请保留完整原文与必要限制。  ';
function gate(){let release!:()=>void;const promise=new Promise<void>(resolve=>{release=resolve;});return {promise,release};}
async function setup(page:Page,kind:Kind,{reject=false,slowDetail=false}={}){
 const user={id:'transition-user',username:'transition-user',display_name:'合成验证用户',role:'user',status:'active',must_change_password:false};
 await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-transition-token');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
 const acknowledgement=gate(),detail=gate();let id='transition-development',accepted=false,phase=0,posts=0;
 const stamp=new Date().toISOString(),errors:string[]=[];
 page.on('pageerror',error=>errors.push(error.message));
 const labels=kind==='match'?['理解项目需求','寻找合适伙伴','形成伙伴推荐','完善项目分析']:['分析发展方向','查找学习资源','形成发展建议'];
 const progress=()=>({run_id:'synthetic-run',started_at:stamp,finished_at:null,stages:labels.map((label,i)=>({key:['understanding','retrieval','generation','enrichment'][i],label,status:i<phase?'completed':i===phase?'running':'pending',started_at:i<=phase?stamp:null,finished_at:i<phase?stamp:null}))});
 const summary=(history=false)=>({id:history?'history-task':id,requirement:history?'已有历史任务的原文':draft,createdAt:stamp,taskStatus:history?'ready':'matching',task_type:kind==='match'?'partner_match':'development_plan',archivedAt:null});
 const payload={answer:'本轮已校验保存的发展建议。',overview:{},stages:[],limitations:[],resource_gaps:[]};
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname.replace(/^\/api/,'');
  if(req.method()==='POST'&&(path==='/agent/tasks'||path==='/development/plans')){
   posts++;if(kind==='match')id=req.postDataJSON().requestId;
   await acknowledgement.promise;
   if(reject)return route.fulfill({status:422,json:{detail:'合成创建失败，请重试。'}});
   accepted=true;return route.fulfill({status:202,json:kind==='match'?{recordId:id,runId:'synthetic-run',taskStatus:'matching'}:{plan_id:id,run_id:'synthetic-run'}});
  }
  const history=path.endsWith('/history-task');
  if(path===`/agent/tasks/${id}`||history&&path.startsWith('/agent/tasks/')){
   if(!accepted&&!history)return route.fulfill({status:404,json:{detail:'尚未创建'}});
   if(slowDetail&&!history)await detail.promise;
   return route.fulfill({json:{...summary(history),recommendations:[],progress:history?null:progress(),understanding:phase&&!history?{technicalNeeds:'已保存的需求理解'}:null,answer:phase===2?'已保存的匹配答复。':'',opportunity:null,demandProfile:null}});
  }
  if(path===`/development/plans/${id}`||history&&path.startsWith('/development/plans/')){
   if(slowDetail&&!history)await detail.promise;
   const ready=history||phase===2;
   return route.fulfill({json:{plan:{id:history?'history-task':id,current_version_id:ready?'version-1':null,status:'active',active_run_id:ready?null:'synthetic-run'},presentation:{state:ready?'available':'generating',current_available:ready,latest_run_status:ready?'ready':'running',latest_run_type:'generate'},partner_name:'合成伙伴',request:{raw_demand:history?'已有历史任务的原文':draft},progress:history?null:progress(),analysis:phase&&!history?{interpretation:'已保存的发展方向分析',priorities:[],basis_limitations:[]}:null,payload:ready?payload:null,hidden:false,notice:null,versions:ready?[{id:'version-1',version_no:1}]:[],conversation:[],runs:[{id:'synthetic-run',submission_id:'synthetic-submission',run_type:'generate',status:ready?'ready':'running',created_at:stamp}]}});
  }
  if(path==='/agents')return route.fulfill({json:[]});
  const json=path==='/auth/me'?user:path==='/health'?{status:'ok'}:path==='/partners'?[{id:'partner-1',name:'合成伙伴'}]:path==='/enablement/context'?{partner:{id:'partner-1',name:'合成伙伴'},project:null,shared_case:null,evidence:[]}:path==='/agent/tasks'?{items:[...(accepted?[summary()]:[]),summary(true)],total:accepted?2:1,page:1,pageSize:10,totalPages:1}:null;
  if(json===null){errors.push(req.method()+' '+path);return route.fulfill({status:404,json:{detail:'未定义的合成接口'}});}
  return route.fulfill({json});
 });
 await page.goto(kind==='match'?'/':'/?mode=development&partner_id=partner-1');
 const input=page.locator(kind==='match'?'#requirement':'textarea[aria-label="发展方向"]');
 await input.fill(draft);await page.evaluate(()=>document.fonts.ready);
 const submit=page.getByRole('button',{name:'开始',exact:true});
 return {input,submit,acknowledgement,detail,errors,id:()=>id,posts:()=>posts,phase:(value:number)=>{phase=value;}};
}

for(const kind of ['match','development'] as const){
 test(`${kind}: slow acknowledgement and detail keep continuous input; only new results animate`,async({page},info)=>{
  await page.setViewportSize({width:1366,height:768});
  const f=await setup(page,kind,{slowDetail:true});
  await page.evaluate(original=>{
   const sidebar=document.querySelector('aside'),workspace=document.querySelector('.main-area');
   const samples:any[]=[];(window as any).transitionSamples=samples;
   function sample(){
    const input=Array.from(document.querySelectorAll<HTMLTextAreaElement>('textarea')).find(el=>el.value===original&&el.getBoundingClientRect().height>0)||null;
    const overlay=document.querySelector<HTMLElement>('.task-transition-frame p');
    const final=document.querySelector<HTMLElement>('.task-request-compact p');
    const progress=document.querySelector<HTMLElement>('[data-testid="task-progress"]');
    const visible=(e:HTMLElement|null)=>!!e&&getComputedStyle(e).visibility!=='hidden'&&e.getBoundingClientRect().height>0;
    samples.push({frameDuration:overlay?.parentElement?.getAnimations()[0]?.effect?.getTiming().duration,progressDuration:progress?.getAnimations()[0]?.effect?.getTiming().duration,progressOpacity:progress?Number(getComputedStyle(progress).opacity):null,visible:!!(visible(input)&&input?.value===original||visible(overlay)&&overlay?.textContent===original||visible(final)&&final?.textContent===original),sidebar:sidebar===document.querySelector('aside'),workspace:workspace===document.querySelector('.main-area'),font:overlay?getComputedStyle(overlay).fontSize:null,transform:overlay?getComputedStyle(overlay).transform:null,phase:document.querySelector('[data-testid="task-transition"]')?.getAttribute('data-phase'),top:overlay?.getBoundingClientRect().top});
    (window as any).transitionRaf=requestAnimationFrame(sample);
   }sample();
  },draft);
  await f.submit.click();await expect(page.getByRole('button',{name:'提交中',exact:true})).toBeDisabled();
  await expect(f.input).toHaveValue(draft);await expect(page.getByTestId('task-transition')).toHaveCount(0);
  await expect.poll(()=>page.evaluate(()=>(window as any).transitionSamples.length)).toBeGreaterThan(30);
  f.acknowledgement.release();await expect(page).toHaveURL(new RegExp(`/tasks/${f.id()}$`));
  await expect(page.locator('.task-transition-frame p')).toHaveText(draft);
  await expect(page.getByTestId('task-transition')).toHaveAttribute('data-phase','waiting');
  await expect(page.getByTestId('task-progress')).toHaveCount(0);
  await page.screenshot({path:info.outputPath('awaiting-real-detail.png')});
  f.detail.release();await expect(page.getByTestId('task-transition')).toHaveCount(0);
  await expect(page.getByTestId('task-progress')).toBeVisible();
  await expect(page.getByTestId('task-progress')).toHaveCSS('opacity','1');
  await expect(page.locator('.task-request-compact p')).toHaveText(draft);
  await expect(page.locator(`.sidebar-task-item[href="/tasks/${f.id()}"]`)).toHaveAttribute('aria-current','page');
  const samples=await page.evaluate(()=>{cancelAnimationFrame((window as any).transitionRaf);return (window as any).transitionSamples;});
  await info.attach('frame-continuity',{body:JSON.stringify(samples),contentType:'application/json'});
  expect(samples.filter((s:any)=>!s.visible||!s.sidebar||!s.workspace)).toEqual([]);
  expect(samples.filter((s:any)=>s.font&&(s.font!=='16px'||s.transform!=='none'))).toEqual([]);
  expect(samples.filter((s:any)=>s.phase==='moving').length).toBeGreaterThan(2);
  expect(samples.some((s:any)=>s.frameDuration===280)).toBe(true);
  expect(samples.some((s:any)=>s.progressDuration===180)).toBe(true);
  expect(samples.filter((s:any)=>s.phase==='moving'&&s.progressOpacity>0)).toEqual([]);
  const requestBox=await page.locator('.task-request-compact').boundingBox(),progressBox=await page.getByTestId('task-progress').boundingBox();
  expect(progressBox!.y).toBeGreaterThanOrEqual(requestBox!.y+requestBox!.height);
  f.phase(1);const result=page.getByTestId(kind==='match'?'task-understanding':'development-analysis');
  await expect(result).toBeVisible({timeout:8000});
  // A repeated poll keeps the same node and does not scroll or replay its animation.
  await result.evaluate(el=>{(window as any).savedResult=el;window.scrollTo(0,80);});
  const scroll=await page.evaluate(()=>scrollY);
  await page.waitForTimeout(3300);
  expect(await result.evaluate(el=>el===(window as any).savedResult&&el.getAnimations().length===0)).toBe(true);
  expect(await page.evaluate(()=>scrollY)).toBe(scroll);
  await page.reload();await expect(result).toBeVisible();
  await expect(page.getByTestId('task-transition')).toHaveCount(0);
  expect(await page.locator('.task-request-compact').evaluate(el=>el.getAnimations().length)).toBe(0);
  await page.locator('.sidebar-task-item[href="/tasks/history-task"]').click();
  await expect(page.locator('.task-request-compact p')).toHaveText('已有历史任务的原文');
  await expect(page.getByTestId('task-transition')).toHaveCount(0);
  expect(f.errors).toEqual([]);expect(f.posts()).toBe(1);
 });

 for(const width of [1920,390])test(`${kind}: normal motion and full text at ${width}px`,async({page},info)=>{
  await page.setViewportSize({width,height:width===1920?1080:844});
  const f=await setup(page,kind);await f.submit.click();f.acknowledgement.release();
  await expect(page.getByTestId('task-transition')).toHaveCount(0);
  await expect(page.locator('.task-request-compact p')).toHaveText(draft);
  await expect(page.getByTestId('task-progress')).toHaveCSS('opacity','1');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath(`${kind}-${width}-settled.png`),fullPage:true});expect(f.errors).toEqual([]);
 });
 test(`${kind}: rejected create restores controls and preserves draft`,async({page})=>{
  const f=await setup(page,kind,{reject:true});await f.submit.click();
  await expect(page.getByRole('button',{name:'提交中',exact:true})).toBeDisabled();f.acknowledgement.release();
  await expect(page.getByRole('button',{name:'提交中',exact:true})).toHaveCount(0);
  await expect(f.input).toHaveValue(draft);await expect(f.input).toBeEditable();
  await expect(page.getByTestId('task-transition')).toHaveCount(0);expect(new URL(page.url()).pathname).toBe('/');expect(f.posts()).toBe(1);
 });
 test(`${kind}: leaving before acknowledgement never steals another task`,async({page})=>{
  const f=await setup(page,kind);await f.submit.click();
  await page.locator('.sidebar-task-item[href="/tasks/history-task"]').click();
  await expect(page.locator('.task-request-compact p')).toHaveText('已有历史任务的原文');
  const response=page.waitForResponse(r=>r.request().method()==='POST');f.acknowledgement.release();await response;
  await expect(page).toHaveURL('/tasks/history-task');await expect(page.getByTestId('task-transition')).toHaveCount(0);
  await expect(page.locator('.task-request-compact p')).toHaveText('已有历史任务的原文');expect(f.errors).toEqual([]);
 });
 test(`${kind}: switching while detail is pending discards the old handoff`,async({page})=>{
  const f=await setup(page,kind,{slowDetail:true});await f.submit.click();f.acknowledgement.release();
  await expect(page.getByTestId('task-transition')).toBeVisible();
  await page.locator('.sidebar-task-item[href="/tasks/history-task"]').click();f.detail.release();
  await expect(page.locator('.task-request-compact p')).toHaveText('已有历史任务的原文');
  await expect(page.getByTestId('task-transition')).toHaveCount(0);expect(f.errors).toEqual([]);
 });
 test(`${kind}: reduced motion and narrow viewport retain unscaled text`,async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:390,height:844});
  const f=await setup(page,kind);await f.submit.click();f.acknowledgement.release();
  await expect(page.getByTestId('task-progress')).toBeVisible();await expect(page.getByTestId('task-transition')).toHaveCount(0);
  await expect(page.locator('.task-request-compact p')).toHaveText(draft);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(await page.getByTestId('task-progress').evaluate(el=>el.getAnimations().length)).toBe(0);expect(f.errors).toEqual([]);
 });
}
