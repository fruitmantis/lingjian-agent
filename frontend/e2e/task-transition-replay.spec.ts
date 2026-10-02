import {test,expect} from '@playwright/test';
import {fixtureLogin} from './identity-fixture';

test.use({video:{mode:'on',size:{width:1366,height:768}},viewport:{width:1366,height:768}});

test.describe('record actual isolated PG task creation',()=>{

 for(const kind of ['match','development'] as const)test(`${kind}: real HTTP creation and persisted replay progress`,async({page,request},info)=>{
  test.setTimeout(90000);
  const session=await (await fixtureLogin(request,'user_a')).json();
  await page.addInitScript(s=>{localStorage.setItem('banfei:user:token',s.access_token);localStorage.setItem('banfei:user:user',JSON.stringify(s.user));},session);
  await page.goto(kind==='match'?'/':'/?mode=development&partner_id=partner-1');
  const input=page.locator(kind==='match'?'#requirement':'textarea[aria-label="发展方向"]');
  await input.fill(kind==='match'?'SIDEBAR_SLOW 希望寻找具备企业知识库实施经验的伙伴，并核实交付条件。':'C_SLOW 希望发展企业级 Agent 与知识库的实施交付能力。');
  await page.evaluate(()=>document.fonts.ready);
  // Suppress only development tooling in the recording, never application content.
  await page.addStyleTag({content:'nextjs-portal{display:none}'});
  const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith(kind==='match'?'/agent/tasks':'/development/plans'));
  await page.getByRole('button',{name:'开始',exact:true}).click();
  const response=await accepted;expect(response.status()).toBe(202);const body=await response.json(),id=body.recordId||body.plan_id;
  await expect(page).toHaveURL(`/tasks/${id}`);await expect(page.locator(`.sidebar-task-item[href="/tasks/${id}"]`)).toHaveAttribute('aria-current','page');
  await expect(page.getByTestId('task-progress')).toBeVisible();
  await expect(page.locator('.task-request-compact p')).toContainText(kind==='match'?'SIDEBAR_SLOW':'C_SLOW');
  await expect.poll(async()=>{const r=await request.get(`http://localhost/api/${kind==='match'?'agent/tasks':'development/plans'}/${id}`,{headers:{Authorization:`Bearer ${session.access_token}`}});const data=await r.json();return kind==='match'?data.taskStatus:data.runs[0]?.status;},{timeout:60000}).toBe('ready');
  await expect(page.locator('.task-answer')).toBeVisible();
  await page.screenshot({path:info.outputPath('persisted-result.png')});
  if(kind==='development'){
   await page.evaluate(()=>{(window as any).replayed=false;const observer=new MutationObserver(()=>{if(document.querySelector('[data-testid="task-transition"]'))(window as any).replayed=true;});observer.observe(document.body,{childList:true,subtree:true});});
   await page.getByLabel('消息',{exact:true}).fill('为什么推荐这个方向？');
   await page.getByRole('button',{name:'发送',exact:true}).click();
   await expect(page.locator('.advisor-exchange')).toBeVisible({timeout:30000});
   await expect(page.getByTestId('task-transition')).toHaveCount(0);
   expect(await page.locator('.task-request-compact').evaluate(el=>el.getAnimations().length)).toBe(0);
   expect(await page.evaluate(()=>(window as any).replayed)).toBe(false);
  }

  await info.attach('accepted-real-task',{body:JSON.stringify({id,status:response.status(),kind,database:'dedicated PostgreSQL temporary schema',model:'isolated replay; no real provider'}),contentType:'application/json'});
 });
});
