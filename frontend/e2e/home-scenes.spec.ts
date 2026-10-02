import {test,expect,type Page} from '@playwright/test';
import {selectPartner} from './partner-select-helper';

const scenes=[
 {name:'AI项目找伙伴',mode:'match',text:'为【行业与业务场景】寻找AI合作伙伴，希望解决【问题或目标】。需要伙伴负责【工作范围】，最终交付【成果】。关键技术要求：【选填】。'},
 {name:'按行业找伙伴',mode:'match',text:'帮我找在【行业】有相关经验的伙伴，用于【具体业务场景】。希望伙伴承担【哪些工作及交付成果】，优先考虑有【描述项目经验需求】的伙伴。'},
 {name:'按能力找伙伴',mode:'match',text:'帮我找具备【某几类核心技术能力】的伙伴，用于【业务场景】。需要完成【具体工作内容】，交付【预期成果内容】。'},
 {name:'伙伴发展建议',mode:'development',text:'希望向【能力或业务方向】发展，主要面向【行业或场景】，下一步能承担【工作内容或项目类型】。目前的能力或经验：【选填】。请结合已提供的信息给出优先提升建议和适合的学习资源。'},
 {name:'能力短板分析',mode:'development',text:'为了做好【目标业务或项目】，需要具备【哪些关键能力】，完成【哪些工作或交付哪些成果】。目前的能力或经验：【选填】。请结合已提供的信息，区分实际短板和资料不足、尚待核实的部分。'},
 {name:'为项目补能力',mode:'development',text:'准备参与【项目及目标】，计划负责【工作范围】，关键要求是【技术要求或交付标准】。目前的能力或经验：【选填】。请分析需要补齐哪些能力，并推荐适合的现有课程或实验。'},
] as const;
const direction=(page:Page)=>page.getByRole('textbox',{name:'发展方向',exact:true});
const starter=(page:Page,name:string)=>page.getByRole('region',{name:'需求场景'}).getByRole('button',{name,exact:true});
async function setup(page:Page,{url='/',rejectFirst=false,hold=false}={}){
 const user={id:'home-scenes-user',username:'home-scenes-user',display_name:'合成验证用户',role:'user',status:'active',must_change_password:false};
 await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-home-scenes-token');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
 const posts:{path:string;body:any}[]=[],errors:string[]=[];
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
 let accepted:{id:string;type:string;text:string}|null=null;
 page.on('pageerror',error=>errors.push(error.message));
 const stamp=new Date().toISOString();
 const summary=(id='history-task')=>({id,requirement:id==='history-task'?'已有任务原文':accepted?.text||'',createdAt:stamp,taskStatus:'ready',task_type:id==='history-task'?'partner_match':accepted?.type||'partner_match',archivedAt:null});
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname.replace(/^\/api/,'');
  if(req.method()==='POST'&&(path==='/agent/tasks'||path==='/development/plans')){
   const body=req.postDataJSON();posts.push({path,body});if(hold)await gate;
   if(rejectFirst&&posts.length===1)return route.fulfill({status:422,json:{detail:'本次处理失败，请重试。'}});
   accepted={id:path==='/agent/tasks'?body.requestId:'home-development-task',type:path==='/agent/tasks'?'partner_match':'development_plan',text:body.requirement||body.request.development_direction};
   return route.fulfill({status:202,json:path==='/agent/tasks'?{recordId:accepted.id,taskStatus:'ready'}:{plan_id:accepted.id}});
  }
  if(path.startsWith('/agent/tasks/')){
   const id=path.split('/').pop();
   if(id!=='history-task'&&id!==accepted?.id)return route.fulfill({status:404,json:{detail:'尚未创建'}});
   return route.fulfill({json:{...summary(id),recommendations:[],answer:'隔离验证结果',demandProfile:null,opportunity:null}});
  }
  if(path.startsWith('/development/plans/'))return route.fulfill({json:{plan:{id:accepted?.id,current_version_id:'version-1',status:'active',active_run_id:null},presentation:{state:'available',current_available:true,latest_run_status:'ready',latest_run_type:'generate'},partner_name:'验证伙伴',request:{raw_demand:accepted?.text},payload:{answer:'隔离验证建议',overview:{},stages:[],limitations:[],resource_gaps:[]},hidden:false,versions:[{id:'version-1',version_no:1}],conversation:[],runs:[{id:'run-1',run_type:'generate',status:'ready',created_at:stamp}]}});
  const partner=url.searchParams.get('partner_id');
  const json=path==='/auth/me'?user:path==='/health'?{status:'ok'}:path==='/partners'?[{id:'partner-1',name:'验证伙伴'},{id:'partner-2',name:'第二验证伙伴'}]:path==='/enablement/context'?{partner:partner?{id:partner,name:partner==='partner-1'?'验证伙伴':'第二验证伙伴'}:null,project:url.searchParams.get('task_id')?{task_id:url.searchParams.get('task_id'),requirement:'已有项目来源',risk_status:'参考信息',risk_notes:'需要核实'}:null,shared_case:null,evidence:[]}:path==='/agent/tasks'?{items:[...(accepted?[summary(accepted.id)]:[]),summary()],total:accepted?2:1,page:1,pageSize:10,totalPages:1}:null;
  if(json===null){errors.push(req.method()+' '+path);return route.fulfill({status:404,json:{detail:'未定义的合成接口'}});}
  return route.fulfill({json});
 });
 await page.goto(url);await expect(page.locator('.home-scene-buttons button')).toHaveCount(6);
 return {posts,errors,release};
}

for(const scene of scenes)test(`${scene.name}: fills only the editable target and selects its placeholder`,async({page})=>{
 const f=await setup(page);await page.evaluate(()=>{(window as any).entryNode=document.querySelector('.unified-task-page');});
 await starter(page,scene.name).click();
 const input=scene.mode==='match'?page.locator('#requirement'):direction(page);
 await expect(input).toHaveValue(scene.text);await expect(input).toBeFocused();
 expect(await input.evaluate(el=>(el as HTMLTextAreaElement).value.slice((el as HTMLTextAreaElement).selectionStart,(el as HTMLTextAreaElement).selectionEnd))).toBe(scene.text.match(/【[^】]+】/)![0]);
 expect(await page.evaluate(()=>(window as any).entryNode===document.querySelector('.unified-task-page'))).toBe(true);
 expect(new URL(page.url()).pathname).toBe('/');expect(f.posts).toHaveLength(0);
 if(scene.mode==='development')await expect(page.getByRole('combobox',{name:'关联已有伙伴资料（可选）'})).toHaveAttribute('data-partner-id','');
 await expect(page.getByText('请将【】中的提示替换为实际需求，也可以直接改写。',{exact:true})).toBeVisible();
 expect(f.errors).toEqual([]);
});

test('modified drafts require confirmation; cancel preserves both mode and text',async({page})=>{
 const f=await setup(page);
 await starter(page,'AI项目找伙伴').click();await page.locator('#requirement').fill('我的匹配草稿');
 await starter(page,'伙伴发展建议').click();await direction(page).fill('我的发展草稿');
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();await expect(page.locator('#requirement')).toHaveValue('我的匹配草稿');
 page.once('dialog',async dialog=>{expect(dialog.message()).toBe('已有未提交内容，要替换成这个场景模板吗？');await dialog.dismiss();});
 await starter(page,'能力短板分析').click();await expect(page.getByRole('tab',{name:'伙伴匹配',exact:true})).toHaveAttribute('aria-selected','true');await expect(page.locator('#requirement')).toHaveValue('我的匹配草稿');
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();await expect(direction(page)).toHaveValue('我的发展草稿');
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();
 page.once('dialog',dialog=>dialog.accept());await starter(page,'能力短板分析').click();await expect(direction(page)).toHaveValue(scenes[4].text);
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();await expect(page.locator('#requirement')).toHaveValue('我的匹配草稿');
 expect(f.posts).toHaveLength(0);expect(f.errors).toEqual([]);
});

test('unchanged templates replace directly; partner and source context survive mode changes',async({page})=>{
 const f=await setup(page,{url:'/?mode=development&partner_id=partner-1&task_id=source-task&case_id=source-case&case_version=2'});
 let dialogs=0;page.on('dialog',async dialog=>{dialogs++;await dialog.dismiss();});
 await starter(page,'伙伴发展建议').click();await starter(page,'能力短板分析').click();await expect(direction(page)).toHaveValue(scenes[4].text);
 await starter(page,'按行业找伙伴').click();await expect(page.locator('#requirement')).toHaveValue(scenes[1].text);
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();await expect(direction(page)).toHaveValue(scenes[4].text);
 const params=new URL(page.url()).searchParams;for(const [key,value] of Object.entries({partner_id:'partner-1',task_id:'source-task',case_id:'source-case',case_version:'2'}))expect(params.get(key)).toBe(value);
 await expect(page.getByRole('combobox',{name:'关联已有伙伴资料（可选）'})).toHaveAttribute('data-partner-id','partner-1');await expect(page.getByTestId('source-context')).toContainText('已有项目来源');
 expect(dialogs).toBe(0);expect(f.posts).toHaveLength(0);expect(f.errors).toEqual([]);
});

for(const kind of ['match','development'] as const)test(`${kind}: free input, failed create, retry and repeated click keep one accepted task`,async({page})=>{
 const f=await setup(page,{rejectFirst:true,hold:true});
 await starter(page,kind==='match'?'AI项目找伙伴':'伙伴发展建议').click();
 const input=kind==='match'?page.locator('#requirement'):direction(page);
 await input.fill('  完全自由输入，不使用任何模板。\n保留我的原文。  ');
 if(kind==='development')await selectPartner(page,'partner-2');
 await expect(page.getByText('请将【】中的提示替换为实际需求，也可以直接改写。',{exact:true})).toHaveCount(0);
 const button=page.getByRole('button',{name:'开始',exact:true});
 await button.evaluate(el=>{(el as HTMLButtonElement).click();(el as HTMLButtonElement).click();});
 await expect.poll(()=>f.posts.length).toBe(1);await expect(page.getByRole('button',{name:'提交中',exact:true})).toBeDisabled();
 await expect(starter(page,'按能力找伙伴')).toBeDisabled();f.release();
 await expect(input).toBeEditable();await expect(input).toHaveValue('  完全自由输入，不使用任何模板。\n保留我的原文。  ');
 await page.getByRole('button',{name:kind==='match'?'开始':'重试',exact:true}).click();
 await expect(page).toHaveURL(/\/tasks\/[^/?]+$/);await expect(page.locator('.task-request-compact p')).toHaveText('  完全自由输入，不使用任何模板。\n保留我的原文。  ');
 await expect(page.getByRole('region',{name:'需求场景'})).toHaveCount(0);expect(f.posts).toHaveLength(2);
 const body=f.posts[1].body;if(kind==='development')expect(body.request.target_partner_id).toBe('partner-2');else expect(body).not.toHaveProperty('target_partner_id');
 await expect(page.locator('.sidebar-task-item[aria-current="page"]')).toHaveAttribute('href',new URL(page.url()).pathname);
 await page.locator('.sidebar-task-item[href="/tasks/history-task"]').click();await expect(page.locator('.task-request-compact p')).toHaveText('已有任务原文');
 expect(f.errors).toEqual([]);
});

for(const width of [1366,390])test(`six compact starters use keyboard and fit ${width}px`,async({page},info)=>{
 await page.setViewportSize({width,height:width===1366?900:844});const f=await setup(page);
 const first=starter(page,'AI项目找伙伴');await first.focus();await page.keyboard.press('Enter');await expect(page.locator('#requirement')).toBeFocused();
 const boxes=await page.locator('.home-scene-buttons button').evaluateAll(nodes=>nodes.map(n=>{const b=n.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height};}));
 const rows=[...new Set(boxes.map(b=>Math.round(b.y)))];expect(rows).toHaveLength(width===1366?2:3);
 for(const scene of scenes){
  const button=starter(page,scene.name),icon=button.locator('svg');
  await expect(button).toHaveAccessibleName(scene.name);await expect(icon).toHaveCount(1);await expect(icon).toHaveAttribute('aria-hidden','true');
  const alignment=await button.evaluate(el=>{
   const b=el.getBoundingClientRect(),i=el.querySelector('svg')!.getBoundingClientRect(),t=el.querySelector('span')!.getBoundingClientRect();
   return {iconWidth:i.width,iconHeight:i.height,gap:t.left-i.right,centerOffset:Math.abs((i.top+i.bottom-t.top-t.bottom)/2),textFits:t.right<=b.right&&t.bottom<=b.bottom,height:b.height};
  });
  expect(alignment.iconWidth).toBe(18);expect(alignment.iconHeight).toBe(18);expect(alignment.gap).toBe(8);expect(alignment.centerOffset).toBeLessThanOrEqual(1);expect(alignment.textFits).toBe(true);expect(alignment.height).toBeLessThanOrEqual(46);
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:info.outputPath(`home-scenes-${width}.png`),fullPage:true});
 await starter(page,'伙伴发展建议').focus();await page.keyboard.press('Space');await expect(direction(page)).toBeFocused();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const actions=page.locator('.development-form-actions'),start=actions.getByRole('button',{name:'开始',exact:true});
 await expect(start).toHaveText('开始');await expect(actions.locator('p')).toHaveCount(0);
 const footer=await actions.evaluate(el=>{
  const box=el.getBoundingClientRect(),button=el.querySelector('button')!.getBoundingClientRect();
  return {rightGap:Math.abs(box.right-button.right),height:box.height,buttonHeight:button.height};
 });
 expect(footer.rightGap).toBeLessThanOrEqual(1);expect(footer.height-footer.buttonHeight).toBeLessThanOrEqual(18);
 expect(await page.locator('.development-form').evaluate(el=>Array.from(el.querySelectorAll('[aria-describedby]')).flatMap(node=>(node.getAttribute('aria-describedby')||'').split(/\s+/).filter(id=>id&&!document.getElementById(id))))).toEqual([]);
 await page.screenshot({path:info.outputPath(`development-scenes-${width}.png`),fullPage:true});expect(f.posts).toHaveLength(0);expect(f.errors).toEqual([]);
});

for(const kind of ['clear','replace'] as const)test(`changing linked partner ${kind} removes all sources and keeps both drafts`,async({page})=>{
 const f=await setup(page,{url:'/?mode=development&partner_id=partner-1&task_id=source-task&case_id=source-case&case_version=2'});
 await direction(page).fill('自述基础和目标，必须保留');
 const combo=page.getByRole('combobox',{name:'关联已有伙伴资料（可选）',exact:true});await combo.click();
 await page.getByRole('option',{name:kind==='clear'?'不关联已有伙伴资料':'第二验证伙伴',exact:true}).click();
 await expect(direction(page)).toHaveValue('自述基础和目标，必须保留');
 for(const key of ['task_id','case_id','case_version'])expect(new URL(page.url()).searchParams.has(key)).toBe(false);
 await expect(page.getByTestId('source-context')).toHaveCount(0);
 await page.getByRole('tab',{name:'伙伴匹配',exact:true}).click();await page.locator('#requirement').fill('独立匹配草稿');
 await page.getByRole('tab',{name:'伙伴发展',exact:true}).click();await expect(direction(page)).toHaveValue('自述基础和目标，必须保留');
 await page.getByRole('button',{name:'开始',exact:true}).click();await expect(page).toHaveURL(/\/tasks\//);
 expect(f.posts[0].body.request).toMatchObject({target_partner_id:kind==='clear'?null:'partner-2',source_task_id:null,source_case_id:null,source_case_version:null});
 expect(f.errors).toEqual([]);
});
