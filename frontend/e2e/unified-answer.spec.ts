import {test,expect} from '@playwright/test';

test('unified answer and resource order match follow-up context',async({page})=>{
 const item=(n:number)=>({item_id:`item-${n}`,source_type:'lab',source_id:`lab-${n}`,source_version:1,title:`数据库实验${n}`,reason:`第${n}项用途`,availability:'available',conditions:{level:'advanced'}});
 const payload={answer:'## 建议\n\n1. 先校验一致性。\n\n2. 再验证回退。',analysis:{intent:'resources',interpretation:'不应作为主答复',reusable_basis:[],priorities:[],basis_limitations:[]},stages:[{title:'实践',items:[item(1),item(2)]}],limitations:[],resource_gaps:[]};
 const data={plan:{id:'synthetic-plan',current_version_id:'v1',active_run_id:null,status:'active'},partner_name:'合成伙伴',request:{development_direction:'只要两个进阶实验'},presentation:{state:'available',current_available:true,current_version:1},payload,hidden:false,notice:null,versions:[{id:'v1',version_no:1}],runs:[],conversation:[{submission_id:'q1',message:'按第二点继续',answer:'第二点是回退验证。',resources:[item(2)]}]};
 const unexpected:string[]=[];
 await page.addInitScript(()=>localStorage.setItem('banfei:admin:token','synthetic-ui-only'));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());if(url.port!=='8000'&&!url.pathname.startsWith('/api/'))return route.continue();
  const path=url.pathname.replace(/^\/api/,'');
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/auth/me')return route.fulfill({json:{id:'admin',role:'admin',status:'active',must_change_password:false}});
  if(path==='/agent/tasks/synthetic-plan')return route.fulfill({json:{task_type:'development_plan'}});
  if(path==='/development/plans/synthetic-plan')return route.fulfill({json:data});
  unexpected.push(path);return route.abort();
 });
 await page.goto('/admin/tasks/synthetic-plan');
 await expect(page.getByTestId('advisor-main-answer')).toContainText('先校验一致性');
 await expect(page.getByTestId('advisor-main-answer')).not.toContainText('不应作为主答复');
 const cards=page.getByTestId('stages').getByTestId('resource-advice');
 await expect(cards).toHaveCount(2);
 await expect(cards.nth(0).getByRole('heading')).toHaveText('1. 数据库实验1');
 await expect(cards.nth(1).getByRole('heading')).toHaveText('2. 数据库实验2');
 await expect(cards.nth(1).getByRole('link')).toHaveAttribute('href','/resources/lab/lab-2?source_version=1');
 await expect(page.getByTestId('conversation')).toContainText('第二点是回退验证');
 await expect(page.getByTestId('conversation').getByTestId('resource-advice')).toHaveCount(1);
 await page.screenshot({path:'/tmp/banfei-unified-answer.png',fullPage:true});
 expect(unexpected).toEqual([]);
});
