import {test,expect,type Page} from '@playwright/test';
type FileInfo={id:string;filename:string;file_type:string;processing_status:string;processing_error?:string|null;source_state?:string|null;source_error?:string|null;preview_error?:string|null;doc_category?:string|null};
const base=(id:string):FileInfo=>({id,filename:id+'.txt',file_type:'txt',processing_status:'ready',source_state:'ready'});
async function setup(page:Page,rows:(reads:number,partnerReads:number)=>FileInfo[],{partnerPage=false,onRetry=(_id:string)=>{}}={}){
 const user={id:'failure-admin',username:'failure-admin',display_name:'合成管理员',role:'admin',status:'active',must_change_password:false};
 await page.addInitScript(user=>{localStorage.setItem('banfei:admin:token','synthetic-admin-token');localStorage.setItem('banfei:admin:user',JSON.stringify(user));},user);
 let reads=0,partnerReads=0;const posts:string[]=[],unexpected:string[]=[],errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname.replace(/^\/api/,'');
  if(req.method()==='POST'&&path.endsWith('/retry')){const id=path.split('/').at(-2)!;posts.push(id);onRetry(id);return route.fulfill({json:{processing_status:'processing'}});}
  if(req.method()!=='GET'){unexpected.push(req.method()+' '+path);return route.fulfill({status:500,json:{detail:'Unexpected write'}});}
  if(path==='/auth/me')return route.fulfill({json:user});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/agents'||path==='/admin/capability-tags')return route.fulfill({json:[]});
  if(path==='/agent/tasks'||path==='/admin/tasks')return route.fulfill({json:{items:[],total:0}});
  if(path==='/partners')return route.fulfill({json:[{id:'partner-1',name:'合成伙伴'}]});
  if(path==='/admin/partner-materials')return route.fulfill({json:{items:[{kind:'case',id:'case-1',partner_id:'partner-1',partner_name:'合成伙伴',title:'上传资料',description:'原资料',category_id:'delivery-1',visible:false,file_count:2,processing_status:'ready',updated_at:'2026-10-14',profile_needs_update:true}],total:1,partners:[{id:'partner-1',name:'合成伙伴'}]}});
  if(path==='/partners/partner-1'){
   partnerReads++;return route.fulfill({json:{id:'partner-1',name:'合成伙伴',intro:'',capabilities:'',industries:'',service_areas:'',profile_needs_update:false,profile_status:'ready',ai_profile:'# 一、公司概况\n\n旧有效画像保留。',profile_sources:[{source_kind:'word',source_id:'word-1',label:'新画像.docx',state:partnerReads<2?'pending':'failed',error:partnerReads<2?null:'画像结构识别失败'}]}});
  }
  if(path==='/cases/case-1/deliverables'||path==='/partners/partner-1/documents'){reads++;return route.fulfill({json:rows(reads,partnerReads)});}
  unexpected.push(path);return route.fulfill({status:404,json:{detail:'Undefined fixture'}});
 });
 await page.goto(partnerPage?'/admin/partners/partner-1':'/admin/partner-materials?partner_id=partner-1');
 if(!partnerPage){await page.getByRole('button',{name:'查看与管理',exact:true}).click();await expect(page.getByRole('dialog',{name:'上传资料',exact:true})).toBeVisible();}
 return {posts,unexpected,errors,reads:()=>reads,partnerReads:()=>partnerReads};
}

test('native failure shows reason and retry without automatic requests',async({page})=>{
 const f=await setup(page,()=>[{...base('native'),processing_status:'failed',processing_error:'文字解析失败'}]);
 const row=page.locator('article').filter({hasText:'native.txt'});await expect(row.getByRole('alert')).toContainText('文字解析失败');await expect(row.getByRole('alert')).toContainText('请点击“重试”');await expect(row.getByRole('button',{name:'重试',exact:true})).toBeEnabled();
 expect(f.posts).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
});

test('native ready continues polling through delayed contribution claim and failure',async({page})=>{
 const f=await setup(page,reads=>[{...base('delayed'),source_state:reads===1?'pending':reads===2?'processing':'failed',source_error:reads>=3?'资料服务暂不可用':null}]);
 const row=page.locator('article').filter({hasText:'delayed.txt'});await expect(row).toContainText('等待处理');await expect(row.getByRole('alert')).toContainText('资料服务暂不可用',{timeout:10000});
 await expect(row.getByRole('button',{name:'重试',exact:true})).toBeEnabled();await expect(row).not.toContainText('已处理');expect(f.reads()).toBeGreaterThanOrEqual(3);expect(f.posts).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
});

test('retry B keeps failed A and follows only the selected file to completion',async({page})=>{
 let retried=false,afterReads=0;
 const f=await setup(page,()=>[{...base('A'),source_state:'failed',source_error:'A原失败原因'},{...base('B'),source_state:retried?(++afterReads===1?'pending':afterReads===2?'processing':'ready'):'failed',source_error:retried?null:'B本次失败原因'}],{onRetry:id=>{expect(id).toBe('B');retried=true;}});
 const a=page.locator('article').filter({hasText:'A.txt'}),b=page.locator('article').filter({hasText:'B.txt'});
 await b.getByRole('button',{name:'重试',exact:true}).click();await expect(b).toContainText('等待处理');await expect(b).toContainText('已处理',{timeout:10000});await expect(a.getByRole('alert')).toContainText('A原失败原因');expect(f.posts).toEqual(['B']);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
});

test('old ready profile still polls new Word failure and opens its file retry',async({page})=>{
 const f=await setup(page,(_reads,partnerReads)=>[{...base('word-1'),filename:'新画像.docx',file_type:'docx',doc_category:'profile_import',processing_status:partnerReads>=2?'failed':'ready',source_state:partnerReads>=2?null:'pending',processing_error:partnerReads>=2?'画像结构识别失败':null}],{partnerPage:true});
 await expect(page.getByTestId('partner-profile-report')).toContainText('旧有效画像保留。');
 const file=page.locator('article').filter({hasText:'新画像.docx'});await expect(file.getByRole('alert')).toBeVisible({timeout:10000});await expect(file.getByRole('alert')).toContainText('画像结构识别失败');await expect(file.getByRole('button',{name:'重试',exact:true})).toBeEnabled();await expect(page.getByTestId('partner-profile-report')).toContainText('旧有效画像保留。');expect(f.partnerReads()).toBeGreaterThanOrEqual(2);expect(f.posts).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
});

test('preview failure retains file access and has explicit retry hint',async({page})=>{
 const f=await setup(page,()=>[{...base('preview'),preview_error:'预览转换失败'}]);const row=page.locator('article').filter({hasText:'preview.txt'});
 await expect(row.getByRole('status')).toContainText('文字提取结果已保留');await expect(row.getByRole('status')).toContainText('请点击“重试”');await expect(row.getByRole('button',{name:'在线查看',exact:true})).toBeEnabled();await expect(row.getByRole('button',{name:'重试',exact:true})).toBeEnabled();expect(f.posts).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
});
