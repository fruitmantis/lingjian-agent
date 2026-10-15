import {test,expect,type Page} from '@playwright/test';

async function setup(page:Page,status:(reads:number,fileReads:number)=>string){
 const user={id:'catalogue-admin',username:'catalogue-admin',display_name:'合成管理员',role:'admin',status:'active',must_change_password:false};
 await page.addInitScript(user=>{localStorage.setItem('banfei:admin:token','synthetic-admin-token');localStorage.setItem('banfei:admin:user',JSON.stringify(user));},user);
 let reads=0,fileReads=0;const writes:string[]=[],unexpected:string[]=[],errors:string[]=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname.replace(/^\/api/,'');
  if(req.method()!=='GET'){writes.push(req.method()+' '+path);return route.fulfill({status:500,json:{detail:'Unexpected write'}});}
  if(path==='/auth/me')return route.fulfill({json:user});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/agents')return route.fulfill({json:[]});
  if(path==='/agent/tasks'||path==='/admin/tasks')return route.fulfill({json:{items:[],total:0}});
  if(path==='/partners')return route.fulfill({json:[{id:'partner-1',name:'合成伙伴'}]});
  if(path==='/admin/partner-materials'){
   reads++;return route.fulfill({json:{items:[{kind:'case',id:'case-1',partner_id:'partner-1',partner_name:'合成伙伴',title:'上传资料',description:'原资料',category_id:'delivery-1',visible:false,file_count:1,processing_status:status(reads,fileReads),updated_at:'2026-10-15',profile_needs_update:true}],total:1,partners:[{id:'partner-1',name:'合成伙伴'}]}});
  }
  if(path==='/cases/case-1/deliverables'){
   fileReads++;return route.fulfill({json:[{id:'B',filename:'B.txt',file_type:'txt',processing_status:'ready',source_state:'failed',source_error:'当前版本提炼失败'}]});
  }
  unexpected.push(path);return route.fulfill({status:404,json:{detail:'Undefined fixture'}});
 });
 await page.goto('/admin/partner-materials?partner_id=partner-1');
 const card=page.locator('[data-material-id="case-1"]');await expect(card).toBeVisible();
 return {card,reads:()=>reads,fileReads:()=>fileReads,writes,unexpected,errors};
}

test('failed catalogue card stays visible after file details close',async({page})=>{
 const f=await setup(page,()=> 'failed');await expect(f.card).toContainText('处理异常');await expect(f.card.getByRole('alert')).toContainText('重试');
 await f.card.getByRole('button',{name:'查看与管理',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'上传资料',exact:true});await expect(dialog.getByRole('alert')).toContainText('当前版本提炼失败');await expect(dialog.getByRole('button',{name:'重试',exact:true})).toBeEnabled();
 await dialog.getByRole('button',{name:'关闭',exact:true}).click();await expect(dialog).toHaveCount(0);await expect(f.card.getByRole('alert')).toBeVisible();await expect(f.card).not.toContainText('已处理');
 if(process.env.BANFEI_UF_EVIDENCE_DIR)await page.screenshot({path:process.env.BANFEI_UF_EVIDENCE_DIR+'/QA-CATALOGUE-AFTER-CLOSE-fixed.jpg',type:'jpeg'});
 expect(f.writes).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
});

test('closing stale ready catalogue details refreshes the now failed card',async({page})=>{
 const f=await setup(page,(_reads,fileReads)=>fileReads?'failed':'ready');await expect(f.card).toContainText('已处理');
 await f.card.getByRole('button',{name:'查看与管理',exact:true}).click();const dialog=page.getByRole('dialog',{name:'上传资料',exact:true});await expect(dialog.getByRole('alert')).toContainText('当前版本提炼失败');
 await dialog.getByRole('button',{name:'关闭',exact:true}).click();await expect(f.card.getByRole('alert')).toBeVisible();await expect(f.card).toContainText('处理异常');expect(f.reads()).toBeGreaterThanOrEqual(2);expect(f.fileReads()).toBe(1);expect(f.writes).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
});

for(const terminal of ['failed','ready']){
 test(`catalogue polls delayed contribution without opening details, ending ${terminal}`,async({page})=>{
  const f=await setup(page,reads=>reads<3?'processing':terminal);await expect(f.card).toContainText('处理中');
  await expect(f.card).toContainText(terminal==='failed'?'处理异常':'已处理',{timeout:10000});
  if(terminal==='failed')await expect(f.card.getByRole('alert')).toBeVisible();else await expect(f.card.getByRole('alert')).toHaveCount(0);
  expect(f.reads()).toBeGreaterThanOrEqual(3);expect(f.fileReads()).toBe(0);expect(f.writes).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
 });
}
