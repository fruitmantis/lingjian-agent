import {test,expect,type Page,type Locator} from '@playwright/test';

type Scope='match'|'development'|'followup';
function gate(){let release!:()=>void;const promise=new Promise<void>(resolve=>{release=resolve;});return {promise,release};}
async function setup(page:Page,scope:Scope,{disabled=false,historical=false}={}){
 const user={id:'shortcut-user',username:'shortcut-user',display_name:'合成用户',role:'user',status:'active',must_change_password:false};
 await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-shortcut-token');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
 const acknowledgement=gate();const posts:any[]=[],unexpected:string[]=[],errors:string[]=[];let accepted=false,matchId='shortcut-match';
 page.on('pageerror',e=>errors.push(e.message));
 const detail=()=>({plan:{id:'shortcut-plan',current_version_id:'version-2',active_run_id:null,status:'active'},presentation:{state:'available',current_available:true,current_version:2},partner_name:'合成伙伴',request:{raw_demand:'合成发展需求'},payload:{format_version:2,answer:'已有建议保持。',overview:{},stages:[],resource_gaps:[]},hidden:false,notice:null,versions:[{id:'version-2',version_no:2},{id:'version-1',version_no:1}],runs:[],conversation:[]});
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname.replace(/^\/api/,'');
  if(req.method()==='POST'&&(path==='/agent/tasks'||path==='/development/plans'||path==='/development/plans/shortcut-plan/conversation')){
   const body=req.postDataJSON();posts.push({path,body});if(path==='/agent/tasks')matchId=body.requestId;
   await acknowledgement.promise;accepted=true;
   return route.fulfill({status:202,json:path==='/agent/tasks'?{recordId:matchId,runId:'synthetic-run',taskStatus:'matching'}:{plan_id:'shortcut-plan',run_id:'synthetic-run'}});
  }
  if(path==='/auth/me')return route.fulfill({json:user});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/agents')return route.fulfill({json:disabled?[{id:'partner_match',name:'伙伴匹配',description:'',icon:'users',enabled:false},{id:'partner_development',name:'伙伴发展',description:'',icon:'trend',enabled:false}]:[]});
  if(path==='/partners')return route.fulfill({json:[{id:'partner-1',name:'合成伙伴'}]});
  if(path==='/enablement/context')return route.fulfill({json:{partner:{id:'partner-1',name:'合成伙伴'},project:null,shared_case:null,evidence:[]}});
  if(path==='/agent/tasks')return route.fulfill({json:{items:[],total:0,page:1,pageSize:10,totalPages:1}});
  if(path==='/agent/tasks/shortcut-plan')return route.fulfill({json:{task_type:'development_plan',id:'shortcut-plan'}});
  if(path==='/development/plans/shortcut-plan')return route.fulfill({json:detail()});
  if(path===`/agent/tasks/${matchId}`)return route.fulfill({json:{id:matchId,task_type:'partner_match',taskStatus:'ready',requirement:'合成需求',recommendations:[],answer:'合成答复',opportunity:null,demandProfile:null}});
  unexpected.push(req.method()+' '+path);return route.fulfill({status:404,json:{detail:'未定义的合成接口'}});
 });
 await page.goto(scope==='match'?'/':scope==='development'?'/?mode=development&partner_id=partner-1':'/tasks/shortcut-plan');
 const input=page.getByRole('textbox',{name:scope==='match'?'输入项目需求':scope==='development'?'发展方向':'消息',exact:true});
 await expect(input).toBeVisible();
 if(historical){await page.locator('.advisor-more summary').click();await page.getByText('历史版本',{exact:true}).click();await page.getByRole('combobox',{name:'查看版本'}).selectOption('version-1');}
 return {input,posts,unexpected,errors,acknowledgement,body:()=>posts[0]?.body,accepted:()=>accepted};
}

async function cursor(input:Locator,start:number,end=start){await input.evaluate((node,args)=>{const field=node as HTMLTextAreaElement;field.focus();field.setSelectionRange(args.start,args.end);},{start,end});}
async function expectNoPost(posts:any[]){await new Promise(resolve=>setTimeout(resolve,80));expect(posts).toHaveLength(0);}

test.describe('composer keyboard',()=>{
for(const scope of ['match','development','followup'] as const){
 test(`${scope}: Enter submits once; busy and repeat do not duplicate`,async({page})=>{
  const f=await setup(page,scope);
  try{
   await f.input.fill('合成需求');await f.input.press('Enter');await expect.poll(()=>f.posts.length).toBe(1);
   expect(scope==='match'?f.body().requirement:scope==='development'?f.body().request.development_direction:f.body().message).toBe('合成需求');
   if(scope==='followup')expect(f.body().based_on_version_id).toBe('version-2');
   await f.input.dispatchEvent('keydown',{key:'Enter',code:'Enter',repeat:true});
   await f.input.dispatchEvent('keydown',{key:'Enter',code:'Enter',repeat:false});
   expect(f.posts).toHaveLength(1);expect(f.errors).toEqual([]);
  }finally{f.acknowledgement.release();}
 });
 test(`${scope}: Alt/Ctrl Enter inserts at selection without submitting`,async({page})=>{
  const f=await setup(page,scope);
  try{
   await f.input.fill('甲乙丙');await cursor(f.input,1,2);await f.input.press('Alt+Enter');await expect(f.input).toHaveValue('甲\n丙');
   expect(await f.input.evaluate(node=>{const field=node as HTMLTextAreaElement;return [field.selectionStart,field.selectionEnd];})).toEqual([2,2]);
   await f.input.press('Control+Enter');await expect(f.input).toHaveValue('甲\n\n丙');
   await expectNoPost(f.posts);
   const hint=scope==='followup'?page.getByTestId('conversation'):scope==='match'?page.locator('#match-panel'):page.locator('#development-panel');
   await expect(hint.getByTestId('composer-shortcut-hint')).toContainText('Alt+Enter / Ctrl+Enter');
   await f.input.press('Enter');await expect.poll(()=>f.posts.length).toBe(1);
   expect(scope==='match'?f.body().requirement:scope==='development'?f.body().request.development_direction:f.body().message).toBe('甲\n\n丙');
  }finally{f.acknowledgement.release();}
 });
 test(`${scope}: composing Enter and keyCode229 never submit`,async({page})=>{
  const f=await setup(page,scope);
  try{
   await f.input.fill('中文选词');
   await f.input.dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:true});await expectNoPost(f.posts);
   await f.input.dispatchEvent('compositionstart',{data:'中文'});
   await f.input.dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:false});await expectNoPost(f.posts);
   await f.input.dispatchEvent('compositionend',{data:'中文选词'});
   await f.input.evaluate(node=>{const e=new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true});Object.defineProperty(e,'keyCode',{value:229});node.dispatchEvent(e);});
   await expectNoPost(f.posts);await f.input.press('Enter');await expect.poll(()=>f.posts.length).toBe(1);
  }finally{f.acknowledgement.release();}
 });
 test(`${scope}: blank input and maxLength retain existing guards`,async({page})=>{
  const f=await setup(page,scope);
  try{
   await f.input.fill('   ');await f.input.press('Enter');await expectNoPost(f.posts);
   const limit=await f.input.getAttribute('maxlength');const size=Number(limit);
   await f.input.fill('甲'.repeat(size));await cursor(f.input,size);await f.input.press('Control+Enter');await expect(f.input).toHaveValue('甲'.repeat(size));
   await cursor(f.input,size-1,size);await f.input.press('Alt+Enter');await expect(f.input).toHaveValue('甲'.repeat(size-1)+'\n');await expectNoPost(f.posts);
  }finally{f.acknowledgement.release();}
 });
 test(`${scope}: stopped agent cannot submit through Enter`,async({page})=>{
  const f=await setup(page,scope,{disabled:true});
  try{await f.input.fill('合成需求');await f.input.press('Enter');await expectNoPost(f.posts);expect(f.errors).toEqual([]);}finally{f.acknowledgement.release();}
 });
}

test('followup: historical view keeps submit disabled',async({page})=>{
 const f=await setup(page,'followup',{historical:true});
 try{await f.input.fill('查看旧版时不提交');await f.input.press('Enter');await expectNoPost(f.posts);}finally{f.acknowledgement.release();}
});
});
