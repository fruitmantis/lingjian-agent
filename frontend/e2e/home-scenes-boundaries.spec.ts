import {test, expect, type Page} from '@playwright/test';

type Kind='match'|'development';
const input=(page:Page,kind:Kind)=>kind==='match'?page.locator('#requirement'):page.getByRole('textbox',{name:'发展方向',exact:true});
const submit=(page:Page,kind:Kind)=>page.getByRole('button',{name:'开始',exact:true});
const starter=(page:Page,name:string)=>page.getByRole('region',{name:'需求场景'}).getByRole('button',{name,exact:true});
const deferred=()=>{let release!:()=>void;const promise=new Promise<void>(resolve=>release=resolve);return {promise,release};};
async function fixture(page:Page,kind:Kind,options:{reject?:boolean,slow?:boolean,detail?:boolean,url?:string}={}) {
 const ack=deferred(),detail=deferred(),posts:any[]=[],errors:string[]=[];
 const records=new Map<string,any>();const stamp=new Date().toISOString();
 const user={id:'independent-audit-user',username:'synthetic-audit',display_name:'独立合成验收',role:'user',status:'active',must_change_password:false};
 await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-audit-token');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
 page.on('pageerror',error=>errors.push(error.message));
 const summary=(id:string,body:any,isDev:boolean)=>({id,requirement:isDev?body.request.development_direction:body.requirement,createdAt:stamp,taskStatus:'ready',task_type:isDev?'development_plan':'partner_match',archivedAt:null});
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname.replace(/^\/api/,'');
  if(path==='/agents')return route.fulfill({json:[]});
  if(req.method()==='POST'&&(path==='/agent/tasks'||path==='/development/plans')) {
   const body=req.postDataJSON(),dev=path==='/development/plans',id=dev?'audit-development-'+posts.length:body.requestId;
   posts.push({path,body,id});if(options.slow)await ack.promise;
   if(options.reject)return route.fulfill({status:422,json:{detail:'本次处理失败，请重试。'}});
   records.set(id,summary(id,body,dev));
   return route.fulfill({status:202,json:dev?{plan_id:id}:{recordId:id,taskStatus:'ready'}});
  }
  if(path.startsWith('/development/submissions/')) {
   const post=posts.find(p=>p.body.submission_id===path.split('/').pop()&&records.has(p.id));
   return route.fulfill(post?{json:{plan_id:post.id}}:{status:404,json:{detail:'尚未创建'}});
  }
  if(path.startsWith('/agent/tasks/')) {
   const id=path.split('/').pop()!,record=id==='audit-history'?{id,requirement:'独立历史任务原文',createdAt:stamp,taskStatus:'ready',task_type:'partner_match'}:records.get(id);
   if(!record)return route.fulfill({status:404,json:{detail:'尚未创建'}});
   if(options.detail&&id!=='audit-history')await detail.promise;
   return route.fulfill({json:{...record,recommendations:[],answer:'隔离合成结果',opportunity:null,demandProfile:null}});
  }
  if(path.startsWith('/development/plans/')) {
   const id=path.split('/').pop()!,record=records.get(id);
   if(!record)return route.fulfill({status:404,json:{detail:'尚未创建'}});
   if(options.detail)await detail.promise;
   return route.fulfill({json:{plan:{id,status:'active',current_version_id:'v1',active_run_id:null},request:{raw_demand:record.requirement},presentation:{state:'available',current_available:true,latest_run_status:'ready',latest_run_type:'generate'},partner_name:'合成伙伴一',payload:{answer:'隔离合成建议',overview:{},stages:[],limitations:[],resource_gaps:[]},hidden:false,versions:[{id:'v1',version_no:1}],conversation:[],runs:[{id:'run1',run_type:'generate',status:'ready',created_at:stamp}]}});
  }
  const json=path==='/auth/me'?user:path==='/health'?{status:'ok'}:path==='/partners'?[{id:'partner-1',name:'合成伙伴一'},{id:'partner-2',name:'合成伙伴二'}]:path==='/enablement/context'?{partner:url.searchParams.get('partner_id')?{id:url.searchParams.get('partner_id'),name:'合成伙伴一'}:null,project:url.searchParams.get('task_id')?{task_id:url.searchParams.get('task_id'),requirement:'合成来源项目',risk_status:'参考信息',risk_notes:'需要核实'}:null,shared_case:null,evidence:[]}:path==='/agent/tasks'?{items:[...records.values(),{id:'audit-history',requirement:'独立历史任务原文',createdAt:stamp,taskStatus:'ready',task_type:'partner_match'}],total:records.size+1,page:1,pageSize:10,totalPages:1}:null;
  if(json===null){errors.push(req.method()+' '+path);return route.fulfill({status:404,json:{detail:'未定义合成接口'}});}
  return route.fulfill({json});
 });
 await page.goto(options.url||(kind==='match'?'/':'/?mode=development&partner_id=partner-1'));
 await expect(page.locator('.home-scene-buttons button')).toHaveCount(6);
 return {ack,detail,posts,errors};
}

for(const kind of ['match','development'] as const)test(`${kind}: untouched placeholder remains optional and explicit submit creates one task`,async({page})=>{
 const f=await fixture(page,kind);
 await starter(page,kind==='match'?'按行业找伙伴':'能力短板分析').click();
 const text=await input(page,kind).inputValue();expect(text).toContain('【');expect(f.posts).toHaveLength(0);
 await expect(input(page,kind)).toBeEditable();await submit(page,kind).click();
 await expect(page).toHaveURL(/\/tasks\//);expect(f.posts).toHaveLength(1);
 expect(kind==='match'?f.posts[0].body.requirement:f.posts[0].body.request.development_direction).toBe(text);
 expect(f.errors).toEqual([]);
});

test('source IDs survive template and mode changes into the submitted development request',async({page})=>{
 const f=await fixture(page,'development',{url:'/?mode=development&partner_id=partner-1&task_id=source-task&case_id=source-case&case_version=2'});
 await starter(page,'为项目补能力').click();await input(page,'development').fill('保留来源的自由方向');
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();await input(page,'match').fill('保留匹配草稿');
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();await expect(input(page,'development')).toHaveValue('保留来源的自由方向');
 await submit(page,'development').click();await expect(page).toHaveURL(/\/tasks\//);
 expect(f.posts[0].body.request).toMatchObject({target_partner_id:'partner-1',development_direction:'保留来源的自由方向',source_task_id:'source-task',source_case_id:'source-case',source_case_version:2});
 expect(f.errors).toEqual([]);
});

test('320px keyboard traversal can select a scene and select partner without pointer input',async({page},info)=>{
 await page.setViewportSize({width:320,height:568});const f=await fixture(page,'match');
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).focus();
 let reached=false;for(let i=0;i<18;i++){await page.keyboard.press('Tab');if(await starter(page,'伙伴发展建议').evaluate(el=>document.activeElement===el)){reached=true;break;}}
 expect(reached).toBe(true);await page.keyboard.press('Enter');await expect(input(page,'development')).toBeFocused();
 const combo=page.getByRole('combobox',{name:'关联已有伙伴资料（可选）'});await combo.focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
 await expect(combo).toHaveAttribute('data-partner-id',/partner-/);
 await input(page,'development').fill('窄屏键盘自由输入');
 await page.setViewportSize({width:320,height:340});await expect(input(page,'development')).toBeEditable();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:info.outputPath('keyboard-short-viewport.png'),fullPage:true});expect(f.posts).toHaveLength(0);expect(f.errors).toEqual([]);
});

test('development rejected acknowledgement while away must restore the preserved draft on return',async({page},info)=>{
 const f=await fixture(page,'development',{reject:true,slow:true});await input(page,'development').fill('不能丢失的可重试草稿');
 await submit(page,'development').click();await expect.poll(()=>f.posts.length).toBe(1);
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();
 const response=page.waitForResponse(r=>r.request().method()==='POST');f.ack.release();await response;
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();await expect(input(page,'development')).toHaveValue('不能丢失的可重试草稿');
 const refresh=page.getByRole('button',{name:'刷新查看',exact:true});
 if(await refresh.isVisible()){const checked=page.waitForResponse(r=>r.url().includes('/development/submissions/'));await refresh.click();expect((await checked).status()).toBe(404);}
 await page.screenshot({path:info.outputPath('returned-after-rejected-create.png'),fullPage:true});
 await expect(input(page,'development')).toBeEditable({timeout:2000});
});

test('match mode round trip while acknowledgement is pending must not create the same draft twice',async({page},info)=>{
 const f=await fixture(page,'match',{slow:true});await input(page,'match').fill('同一轮匹配提交，不能重复创建');
 await submit(page,'match').click();await expect.poll(()=>f.posts.length).toBe(1);
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();
 if(await submit(page,'match').isEnabled()){await submit(page,'match').click();await page.waitForTimeout(200);}
 await info.attach('creation-count',{body:JSON.stringify({count:f.posts.length,distinctIds:new Set(f.posts.map(p=>p.body.requestId)).size}),contentType:'application/json'});
 await page.screenshot({path:info.outputPath('duplicate-after-mode-roundtrip.png'),fullPage:true});f.ack.release();
 expect(f.posts).toHaveLength(1);
});

for(const kind of ['match','development'] as const)test(`${kind}: long scrolled textarea preserves visible text origin while waiting for detail`,async({page},info)=>{
 await page.setViewportSize({width:1366,height:900});const f=await fixture(page,kind,{slow:true,detail:true});
 const value=Array.from({length:24},(_,i)=>`第${String(i+1).padStart(2,'0')}行：合成项目需求，保留当前阅读位置。`).join('\n');await input(page,kind).fill(value);
 const before=await input(page,kind).evaluate(el=>{const e=el as HTMLTextAreaElement;e.scrollTop=e.scrollHeight;const b=e.getBoundingClientRect();return {scrollTop:e.scrollTop,textTop:b.top+parseFloat(getComputedStyle(e).paddingTop)-e.scrollTop};});
 expect(before.scrollTop).toBeGreaterThan(50);await submit(page,kind).click();await page.screenshot({path:info.outputPath('scrolled-input-before.png')});f.ack.release();
 await expect(page.getByTestId('task-transition')).toHaveAttribute('data-phase','waiting');
 const after=await page.locator('.task-transition-frame p').evaluate(e=>e.getBoundingClientRect().top+parseFloat(getComputedStyle(e).paddingTop));
 await page.screenshot({path:info.outputPath('scrolled-input-after.png')});await info.attach('text-origin',{body:JSON.stringify({before,after,jump:after-before.textTop}),contentType:'application/json'});f.detail.release();
 expect(Math.abs(after-before.textTop)).toBeLessThanOrEqual(2);
});

test('same-mode cancel preserves selection content; new task clears both independent drafts',async({page})=>{
 const f=await fixture(page,'match');await input(page,'match').fill('匹配保留文本');
 page.once('dialog',d=>d.dismiss());await starter(page,'按能力找伙伴').click();await expect(input(page,'match')).toHaveValue('匹配保留文本');
 await starter(page,'伙伴发展建议').click();await input(page,'development').fill('发展保留文本');
 await page.getByRole('link',{name:'开启新任务',exact:true}).click();
 await expect(input(page,'match')).toHaveValue('');await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();await expect(input(page,'development')).toHaveValue('');
 expect(f.posts).toHaveLength(0);expect(f.errors).toEqual([]);
});

// Additional regressions: original independent assertions above remain unchanged.
test('development rejection arriving after return releases only the original submission lock',async({page})=>{
 const f=await fixture(page,'development',{reject:true,slow:true});
 await input(page,'development').fill('回到页面后仍可恢复的原草稿');await submit(page,'development').click();
 await expect.poll(()=>f.posts.length).toBe(1);
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();await input(page,'match').fill('另一模式的独立草稿');
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();await expect(input(page,'development')).toBeDisabled();
 f.ack.release();await expect(input(page,'development')).toBeEditable();
 await expect(input(page,'development')).toHaveValue('回到页面后仍可恢复的原草稿');
 expect(await page.evaluate(()=>Object.keys(sessionStorage).filter(k=>k.startsWith('development:pending-create:')))).toEqual([]);
 await page.getByRole('button',{name:'重试',exact:true}).click();await expect.poll(()=>f.posts.length).toBe(2);
 expect(f.posts[1].body.submission_id).not.toBe(f.posts[0].body.submission_id);
 await expect(input(page,'development')).toBeEditable();
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();await expect(input(page,'match')).toHaveValue('另一模式的独立草稿');expect(f.errors).toEqual([]);
});

test('a pending match blocks its own draft while allowing a different draft and the other mode',async({page})=>{
 const f=await fixture(page,'match',{slow:true});await input(page,'match').fill('第一个在途匹配草稿');await submit(page,'match').click();
 await expect.poll(()=>f.posts.length).toBe(1);
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();
 const combo=page.getByRole('combobox',{name:'关联已有伙伴资料（可选）'});await combo.click();await page.getByRole('option',{name:'合成伙伴一',exact:true}).click();await expect(combo).toHaveAttribute('data-partner-id','partner-1');
 await input(page,'development').fill('独立的发展方向');await submit(page,'development').click();await expect.poll(()=>f.posts.length).toBe(2);
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();await expect(submit(page,'match')).toBeDisabled();
 await expect(input(page,'match')).toBeEditable();await input(page,'match').fill('不同的第二个匹配草稿');await expect(submit(page,'match')).toBeEnabled();
 await submit(page,'match').click();await expect.poll(()=>f.posts.length).toBe(3);
 expect(new Set(f.posts.filter(p=>p.path==='/agent/tasks').map(p=>p.body.requestId)).size).toBe(2);
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();f.ack.release();
 await expect(input(page,'development')).toBeEditable();await expect(input(page,'development')).toHaveValue('独立的发展方向');
 await expect.poll(()=>page.locator('.sidebar-task-item[href^="/tasks/"]').count()).toBe(4);
 await expect.poll(()=>{const url=new URL(page.url());return {path:url.pathname,mode:url.searchParams.get('mode')};}).toEqual({path:'/',mode:'development'});expect(f.errors).toEqual([]);
});

for(const kind of ['match','development'] as const)test(`${kind}: scrolled handoff settles into the complete original requirement`,async({page})=>{
 const f=await fixture(page,kind,{slow:true,detail:true});
 const value=Array.from({length:24},(_,i)=>`第${i+1}行：最终需求保留全部合成文字。`).join('\n');
 await input(page,kind).fill(value);await input(page,kind).evaluate(el=>{el.scrollTop=el.scrollHeight;});
 await submit(page,kind).click();f.ack.release();await expect(page.getByTestId('task-transition')).toHaveAttribute('data-phase','waiting');
 f.detail.release();await expect(page.getByTestId('task-transition')).toHaveCount(0);
 await expect(page.locator('.task-request-compact p')).toHaveText(value);expect(f.posts).toHaveLength(1);expect(f.errors).toEqual([]);
});
