import {test,expect,type Page} from '@playwright/test';
import {readFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';

const evidence=process.env.BANFEI_RECOMMENDATION_EVIDENCE||'';
test.skip(!evidence,'Requires private saved-result evidence; no generated-task fallback.');
const variant=process.env.BANFEI_RECOMMENDATION_VARIANT||'after';
const screenshotTask=evidence?JSON.parse(readFileSync(join(evidence,'private/screenshot-task.json'),'utf8')):{};
const positiveTask=evidence?JSON.parse(readFileSync(join(evidence,'private/positive-task.json'),'utf8')):{};
const compact=(value:string)=>value.replace(/\*\*/g,'').replace(/^#{1,6}\s+/gm,'').replace(/^(?:[-*+] |\d+[.)] )/gm,'').replace(/\s+/g,'');
async function setup(page:Page,task:any){
 const user={id:'layout-user',username:'layout-user',display_name:'伴飞用户',role:'user',status:'active',must_change_password:false};
 const writes:string[]=[],unexpected:string[]=[],errors:string[]=[];
 await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-layout-token');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname.replace(/^\/api/,'');
  if(req.method()!=='GET'){writes.push(req.method()+' '+path);return route.fulfill({status:500,json:{detail:'No mutations in saved-result preview'}});}
  if(path==='/auth/me')return route.fulfill({json:user});
  if(path==='/agents')return route.fulfill({json:[]});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/agent/tasks')return route.fulfill({json:{items:[],total:0,page:1,pageSize:10,totalPages:1}});
  if(path===`/agent/tasks/${task.id}`)return route.fulfill({json:task});
  unexpected.push(path);return route.fulfill({status:404,json:{detail:'Undefined preview fixture'}});
 });
 await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/tasks/'+task.id);
 await expect(page.getByRole('heading',{name:'任务详情',exact:true})).toBeVisible();
 await expect(page.locator('.task-answer')).toContainText(task.answer.split('\n')[0].replace(/^#+\s+/,''));
 await page.evaluate(()=>document.fonts.ready);
 return {writes,unexpected,errors};
}
async function noOverflow(page:Page){expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);}
async function screenshot(page:Page,selector:string,name:string){mkdirSync(join(evidence,'screenshots'),{recursive:true});await page.locator(selector).first().screenshot({path:join(evidence,'screenshots',`${variant}-${name}.jpg`),type:'jpeg',quality:88});}

for(const screen of [{name:'desktop',width:1440,height:1000},{name:'narrow',width:390,height:844}]){
 test(`saved screenshot answer stays complete on ${screen.name}`,async({page})=>{
  await page.setViewportSize(screen);const f=await setup(page,screenshotTask);
  const answer=page.getByTestId('advisor-answer').locator('.advisor-answer-body');
  expect(compact(await answer.innerText())).toBe(compact(screenshotTask.answer));
  await expect(page.locator('.recommendation-item')).toHaveCount(0);await expect(answer.locator('p')).toHaveCount(2);
  if(variant==='after'){
   await expect(page.getByRole('heading',{name:'推荐说明',exact:true})).toBeVisible();
   const metrics=await answer.evaluate(node=>({max:getComputedStyle(node).maxWidth,line:parseFloat(getComputedStyle(node.querySelector('p')!).lineHeight)}));
   expect(metrics.max).not.toBe('none');expect(metrics.line).toBeGreaterThanOrEqual(30);
   await noOverflow(page);
  }
  await screenshot(page,'.task-answer',`saved-answer-${screen.name}`);
  expect(f.writes).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
 });
 test(`saved formal recommendation fields stay complete on ${screen.name}`,async({page})=>{
  await page.setViewportSize(screen);const f=await setup(page,positiveTask);
  const cards=page.locator('.recommendation-item');await expect(cards).toHaveCount(positiveTask.recommendations.length);
  for(let i=0;i<positiveTask.recommendations.length;i++){
   const item=positiveTask.recommendations[i],card=cards.nth(i),content=compact(await card.innerText());
   await expect(card.getByRole('heading',{name:item.partnerName,exact:true})).toBeVisible();
   await expect(card.getByRole('link',{name:'查看伙伴',exact:true})).toHaveAttribute('href','/partners/'+item.partnerId+(variant==='after'?'?returnTo='+encodeURIComponent('/tasks/'+positiveTask.id+'#recommendation-'+item.partnerId):''));
   expect(content).toContain(compact('匹配分 '+item.matchScore));
   for(const key of ['matchedCapabilities','matchedIndustries','matchedRegions','recommendationReason','evidenceCases','evidenceDeliverables','riskNotes']){
    const value=item[key];if(value&&!['未核实','未提供可核实的支撑案例','未提供可核实的支撑交付物'].includes(value))expect(content).toContain(compact(value));
   }
   if(variant==='after'){
    const reason=card.locator('section').filter({has:page.getByRole('heading',{name:'推荐理由',exact:true})});
    if(item.recommendationReason){await expect(reason).toBeVisible();const width=(await reason.boundingBox())!.width;expect(width).toBeGreaterThan((await card.boundingBox())!.width*.8);}
    const selection=await card.evaluate(node=>{const selection=getSelection()!;selection.selectAllChildren(node);const text=selection.toString();selection.removeAllRanges();return text;});
    expect(selection).toContain(item.partnerName);expect(selection).toContain('\n');
   }
  }
  if(variant==='after')await noOverflow(page);
  await screenshot(page,'.recommendation-item',`saved-card-${screen.name}`);
  expect(f.writes).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
 });
}

test('existing paragraphs and lists stay structured without guessing role fields',async({page})=>{
 test.skip(variant==='before');const task=structuredClone(positiveTask),item=task.recommendations[0];
 task.recommendations=[{...item,recommendationReason:'**交付分工**\n\n合成团队甲负责现有环节；合成团队乙负责另一环节。\n\n- 保留事实甲。\n- 保留事实乙。',evidenceCases:'合成案例第一段。\n\n合成案例第二段。',evidenceDeliverables:'<script>window.unexpectedLayoutExecution=true</script>\n\n[外部文字](javascript:alert(1))'}];
 const f=await setup(page,task),card=page.locator('.recommendation-item');await expect(card.getByRole('listitem')).toHaveCount(2);
 await expect(card).toContainText('合成团队甲负责现有环节；合成团队乙负责另一环节。');await expect(card.getByRole('heading',{name:'角色分工',exact:true})).toHaveCount(0);
 await expect(card.locator('script')).toHaveCount(0);await expect(card.locator('a[href^="javascript:"]')).toHaveCount(0);expect(await page.evaluate(()=>(window as any).unexpectedLayoutExecution)).toBeUndefined();
 expect(f.writes).toEqual([]);expect(f.unexpected).toEqual([]);expect(f.errors).toEqual([]);
});
