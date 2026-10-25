import {mockDeviceSession} from './device-session-fixture';
import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {expect,test,type Page} from '@playwright/test';
import {fixtureLogin} from './identity-fixture';
const API='http://localhost/api';
function adminSession(){return JSON.parse(readFileSync(`${process.env.BANFEI_TEST_ROOT}/visual-session.json`,'utf8'));}
async function setSession(page:Page,session:ReturnType<typeof adminSession>){await page.addInitScript(s=>{localStorage.setItem(`banfei:${s.user.role}:token`,s.access_token);localStorage.setItem(`banfei:${s.user.role}:user`,JSON.stringify(s.user));},session);}

function organizeSyntheticProfile(partnerId:string){
  execFileSync('../.venv/bin/python',['-c',"import os,sys,json\nsys.path.insert(0,'..')\nfrom backend.tests.support.model_test_boundary import validation_url\nvalidation_url(os.environ['DATABASE_URL'],scoped=True)\nfrom backend.app.database import get_db\nfrom backend.app import profile_sources\nwith get_db() as conn:\n    assert conn.execute('SELECT current_database()').fetchone()[0] in ('banfei_agent_test','banfei_validation')\n    assert conn.execute('SELECT current_schema()').fetchone()[0].startswith('validation_')\ndef synthetic_merge(messages,contract):\n    assert contract is profile_sources.ChapterMerge\n    payload=json.loads(messages[-1]['content'])\n    sections=[]\n    for chapter in payload['chapters']:\n        rows=chapter['sources']\n        bodies=list(dict.fromkeys(row.get('summary',row.get('body','')) for row in rows))\n        sections.append({'chapter':chapter['chapter'],'body':'\\n\\n'.join(bodies) or profile_sources.profile_report.MISSING,'used_sources':[row['source'] for row in rows]})\n    return json.dumps({'sections':sections},ensure_ascii=False)\nprofile_sources._profile_completion=synthetic_merge\nprofile_sources.process_partner(sys.argv[1])\n",partnerId]);
}

test('one materials page: partner shortcut, private profile originals and legacy file classification',async({page,request})=>{
  const session=adminSession(),headers={Authorization:`Bearer ${session.access_token}`};await setSession(page,session);
  const partner=await (await request.post(API+'/partners',{headers,data:{name:'资料验证 '+randomUUID()}})).json();
  const legacy=await (await request.post(`${API}/partners/${partner.id}/documents`,{headers,multipart:{file:{name:'旧资料.txt',mimeType:'text/plain',buffer:Buffer.from('完整原生文字\n下一行保留')}}})).json();
  await page.goto('/admin/partners/'+partner.id);
  await expect(page.getByRole('heading',{name:'伙伴案例',exact:true})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'伙伴资料',exact:true})).toHaveCount(0);
  const pdfSource=execFileSync('../.venv/bin/python',['-c','import sys;sys.path.insert(0,"..");from backend.tests.support.profile_report_fixture import document;sys.stdout.buffer.write(document())']);
  await page.getByText('导入 DOCX 画像',{exact:true}).locator('input').setInputFiles({name:'初始化画像.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:pdfSource});
  await expect(page.getByTestId('partner-profile-report').getByRole('heading',{level:3})).toHaveCount(10,{timeout:30000});
  await expect(page.getByTestId('partner-profile-report').getByRole('table')).toHaveCount(3);
  await page.getByText('画像原件',{exact:true}).click();
  const originals=page.locator('details').filter({has:page.getByText('画像原件',{exact:true})});await expect(originals).toHaveCount(1);
  const office=originals.locator('article').filter({hasText:'初始化画像.docx'});await expect(office).toHaveCount(1);await expect(office).toContainText('已处理');
  await expect(originals.locator('article').filter({hasText:'旧资料.txt'})).toHaveCount(0);
  await office.getByRole('button',{name:'在线查看'}).click();await expect(page.getByRole('dialog').locator('object[type="application/pdf"]')).toBeVisible();
  await page.getByRole('dialog').getByRole('button',{name:'关闭'}).click();
  const download=page.waitForEvent('download');await office.getByRole('button',{name:'下载原件'}).click();expect((await download).suggestedFilename()).toBe('初始化画像.docx');
  await page.locator('section').filter({has:page.getByRole('heading',{name:'案例与资料',exact:true})}).getByRole('link',{name:'管理资料',exact:true}).click();await expect(page).toHaveURL(new RegExp('/admin/partner-materials\\?partner_id='+partner.id));
  await expect(page.getByText('当前伙伴：'+partner.name,{exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'待分类资料',exact:true})).toBeVisible();
  await expect(page.locator('[data-material-id]')).toHaveCount(1);
  await page.getByRole('button',{name:'查看与管理'}).click();
  let detail=page.getByRole('dialog',{name:'旧资料.txt',exact:true});
  await detail.getByRole('button',{name:'在线查看'}).click();await expect(page.getByRole('dialog',{name:'旧资料.txt'}).last()).toContainText('下一行保留');
  await page.getByRole('dialog',{name:'旧资料.txt'}).last().getByRole('button',{name:'关闭'}).click();
  await detail.getByRole('button',{name:'编辑与归类'}).click();await detail.getByLabel('标题',{exact:true}).fill('已归类资料');await detail.getByLabel('一级分类',{exact:true}).selectOption('delivery');await detail.getByLabel('二级分类',{exact:true}).selectOption('delivery-2');await detail.getByRole('button',{name:'保存资料'}).click();
  detail=page.getByRole('dialog',{name:'已归类资料',exact:true});await expect(detail).toBeVisible();await detail.getByRole('button',{name:'关闭'}).click();
  await expect(page.locator(`[data-material-id="${legacy.id}"]`)).toContainText('已归类资料');
  expect((await request.get(`${API}/cases/${legacy.id}/deliverables`,{headers})).ok()).toBeTruthy();
  const after=await (await request.get(`${API}/cases/${legacy.id}/deliverables`,{headers})).json();expect(after[0].id).toBe(legacy.id);
  await page.getByRole('button',{name:'查看全部伙伴资料'}).click();await expect(page.getByLabel('筛选伙伴',{exact:true})).toHaveAttribute('data-partner-id','');
  await page.getByRole('navigation',{name:'后台导航'}).getByRole('link',{name:'伙伴资料',exact:true}).click();await expect(page.getByRole('heading',{name:'伙伴资料',exact:true})).toBeVisible();
});

test('multiple files in one card, safe preview, same-ID replacement and live display permission',async({page,request,browser})=>{
  const session=adminSession(),headers={Authorization:`Bearer ${session.access_token}`};await setSession(page,session);
  const p=await (await request.post(API+'/partners',{headers,data:{name:'案例验证 '+randomUUID()}})).json();
  await page.goto('/admin/partner-materials?partner_id='+p.id);await page.getByRole('button',{name:'新增资料',exact:true}).click();
  const form=page.getByRole('dialog',{name:'新增资料'});await expect(form.getByLabel('关联伙伴',{exact:true})).toHaveAttribute('data-partner-id',p.id);
  await form.getByLabel('标题',{exact:true}).fill('数据库原生文档案例');await form.getByLabel('一级分类',{exact:true}).selectOption('technical');await form.getByLabel('二级分类',{exact:true}).selectOption('technical-3');await form.getByLabel('简介（选填）').fill('案例简介');
  await form.locator('input[type=file]').setInputFiles({name:'image.png',mimeType:'image/png',buffer:Buffer.from('not allowed')});await expect(form.getByRole('alert')).toContainText('不支持此格式');
  await form.locator('input[type=file]').setInputFiles([{name:'案例材料.md',mimeType:'text/markdown',buffer:Buffer.from('# 案例文档\n\n正文内容')},{name:'静态.html',mimeType:'text/html',buffer:Buffer.from('<h1>安全正文</h1><script>window.injected=1</script><img src="https://example.invalid/leak">')}]);
  await form.getByRole('button',{name:'保存资料'}).click();
  const detail=page.getByRole('dialog',{name:'数据库原生文档案例',exact:true});await expect(detail).toBeVisible();await expect(detail.getByText('已处理',{exact:true})).toHaveCount(2,{timeout:20000});
  const html=detail.locator('article').filter({hasText:'静态.html'});await html.getByRole('button',{name:'在线查看'}).click();
  await expect(page.frameLocator('iframe[title="文档预览"]').getByRole('heading',{name:'安全正文'})).toBeVisible();expect(await page.frameLocator('iframe[title="文档预览"]').locator('script,img').count()).toBe(0);await page.getByRole('dialog',{name:'静态.html'}).getByRole('button',{name:'关闭'}).click();
  const cases=await (await request.get(`${API}/cases/by-partner/${p.id}`,{headers})).json();expect(cases).toHaveLength(1);const cid=cases[0].id;
  const files=await (await request.get(`${API}/cases/${cid}/deliverables`,{headers})).json();const md=files.find((f:{filename:string})=>f.filename==='案例材料.md');const url=`${API}/cases/${cid}/deliverables/${md.id}/file`;
  const user=await (await fixtureLogin(request,'user_a')).json(),uh={Authorization:`Bearer ${user.access_token}`};expect((await request.get(url,{headers:uh})).status()).toBe(404);
  await detail.getByLabel('展示',{exact:true}).check();await expect.poll(async()=>(await request.get(url,{headers:uh})).status()).toBe(200);
  // Seed a literal, owned original contribution without a model, then verify its real withdrawal.
  await expect.poll(async()=>{const value=await (await request.get(API+'/partners/'+p.id,{headers})).json();return value.profile_sources?.find((s:{source_kind:string;source_id:string;state:string})=>s.source_kind==='attachment'&&s.source_id===md.id)?.state;}).not.toBe('processing');
  execFileSync('../.venv/bin/python',['-c',"import os,sys\nsys.path.insert(0,'..')\nfrom backend.tests.support.model_test_boundary import validation_url\nvalidation_url(os.environ['DATABASE_URL'],scoped=True)\nfrom backend.app.database import get_db\nfrom backend.app import profile_sources\npid,fid=sys.argv[1:]\nwith get_db() as conn:\n    assert conn.execute('SELECT current_database()').fetchone()[0] in ('banfei_agent_test','banfei_validation')\n    assert conn.execute('SELECT current_schema()').fetchone()[0].startswith('validation_')\n    source=next(s for s in profile_sources.sources(conn,pid) if s['kind']=='attachment' and s['id']==fid)\n    assert '正文内容' in source['text']\n    profile_sources.put(conn,source,'ready',[{'chapter':6,'summary':'正文内容','quotes':['正文内容']}])\n    profile_sources.rebuild(conn,pid)\n",p.id,md.id]);
  // Contributions only mark chapters pending; explicitly organize the synthetic profile.
  organizeSyntheticProfile(p.id);
  await expect.poll(async()=>(await (await request.get(API+'/partners/'+p.id,{headers})).json()).ai_profile).toContain('正文内容');
  await detail.getByLabel('替换 案例材料.md',{exact:true}).setInputFiles({name:'更新材料.txt',mimeType:'text/plain',buffer:Buffer.from('替换后的原生文字')});
  await expect(detail.getByText('更新材料.txt',{exact:true})).toBeVisible();await expect.poll(async()=>(await request.get(url,{headers})).text()).toBe('替换后的原生文字');
  const context=await browser.newContext();const ordinary=await context.newPage();await setSession(ordinary,user);await ordinary.goto(`/resources/case/${cid}`);await expect(ordinary.getByRole('heading',{name:'数据库原生文档案例',exact:true})).toBeVisible();
  await detail.getByLabel('展示',{exact:true}).uncheck();await expect.poll(async()=>(await request.get(url,{headers:uh})).status()).toBe(404);await ordinary.reload();await expect(ordinary.getByRole('alert').filter({hasText:'内容不存在'})).toContainText('内容不存在');await context.close();
  await detail.getByRole('button',{name:'关闭',exact:true}).click();await expect(page.locator('[data-material-id]')).toHaveCount(1);await expect(page.locator('[data-material-id]')).toContainText('2 个文件');
  await expect.poll(async()=>{const rows=await (await request.get(`${API}/cases/${cid}/deliverables`,{headers})).json();return rows.find((row:{id:string})=>row.id===md.id)?.source_state;}).toBe('ready');
  organizeSyntheticProfile(p.id);
  const profileResponse=await request.get(API+'/partners/'+p.id,{headers});expect(profileResponse.ok()).toBeTruthy();
  const projected=await profileResponse.json();expect(typeof projected.ai_profile).toBe('string');
  expect(projected.ai_profile.match(/^##\s+\d+\./gm)).toHaveLength(10);
  expect(projected.ai_profile).toContain('现有资料未提供');expect(projected.ai_profile).toContain('案例简介');
  expect(projected.ai_profile).not.toContain('正文内容');expect(projected.ai_profile).not.toContain('案例材料.md');
});

test('global partner/category search, three-column groups and total-page jump',async({page,request})=>{
  const session=adminSession(),headers={Authorization:`Bearer ${session.access_token}`};await setSession(page,session);await page.setViewportSize({width:1440,height:1000});
  const name='卡片分组 '+randomUUID(),p=await (await request.post(API+'/partners',{headers,data:{name}})).json();
  for(let i=0;i<14;i++)expect((await request.post(API+'/cases',{headers,data:{partner_id:p.id,title:`目录验证 ${i}`,category_id:i<7?'marketing-1':'technical-3'}})).status()).toBe(201);
  await page.goto('/admin/partner-materials?partner_id='+p.id);await expect(page.locator('[data-material-id]')).toHaveCount(10);
  await expect(page.getByRole('heading',{name:'营销与宣传',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'技术案例',exact:true})).toBeVisible();
  const cards=page.locator('[data-material-id]');const boxes=await Promise.all([cards.nth(0).boundingBox(),cards.nth(1).boundingBox(),cards.nth(2).boundingBox()]);expect(Math.max(...boxes.map(b=>b!.y))-Math.min(...boxes.map(b=>b!.y))).toBeLessThan(2);
  await expect(page.getByRole('navigation',{name:'伙伴资料分页'})).toContainText('共 2 页');await page.getByLabel('跳转页码').fill('2');await page.getByRole('button',{name:'跳转',exact:true}).click();await expect(cards).toHaveCount(4);
  await page.getByLabel('筛选一级分类').selectOption('technical');await page.getByLabel('筛选二级分类').selectOption('technical-3');await expect(cards).toHaveCount(7);
  await page.getByLabel('资料名称').fill('目录验证 13');await page.getByRole('button',{name:'搜索',exact:true}).click();await expect(cards).toHaveCount(1);await expect(cards).toContainText('目录验证 13');
  await page.getByRole('button',{name:'查看全部伙伴资料'}).click();await expect(page.getByLabel('筛选伙伴',{exact:true})).toHaveAttribute('data-partner-id','');await expect(cards).toHaveCount(1);
  await page.goto('/admin/partner-materials?partner_id='+p.id);await expect(cards).toHaveCount(10);await page.screenshot({path:'/tmp/banfei-material-manager.png',fullPage:true});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});


for(const motion of ['no-preference','reduce'] as const)test('phase1 F01: material panel contains keyboard focus and restores its trigger, '+motion,async({page},info)=>{
  await page.emulateMedia({reducedMotion:motion});
  const session=adminSession();await setSession(page,session);
  await page.route('**/api/**',async route=>{
    expect(route.request().method()).toBe('GET');
    const path=new URL(route.request().url()).pathname.slice(4);
    const json=path==='/auth/me'?session.user:path==='/health'?{status:'ok'}:
      path==='/admin/partner-materials'?{items:[],total:0,partners:[{id:'focus-fixture',name:'合成焦点伙伴'}]}:{};
    await route.fulfill({json});
  });
  await mockDeviceSession(page);
  await page.goto('/admin/partner-materials');
  const trigger=page.getByRole('button',{name:'新增资料',exact:true});await trigger.click();
  const dialog=page.getByRole('dialog',{name:'新增资料',exact:true});
  if(motion==='reduce'){
    await expect(dialog).toHaveCSS('animation-name','none');
    await expect(dialog.locator('..')).toHaveCSS('animation-name','none');
  }else expect(await dialog.evaluate(el=>getComputedStyle(el).animationDuration)).toBe('0.12s');
  await page.screenshot({path:info.outputPath('phase3-material-panel-'+motion+'.png')});
  const close=dialog.getByRole('button',{name:'关闭',exact:true}),file=dialog.locator('input[type=file]');
  await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');await expect(file).toBeFocused();
  await page.keyboard.press('Tab');await expect(close).toBeFocused();
  const partner=dialog.getByRole('combobox',{name:'关联伙伴',exact:true});await partner.click();
  await expect(partner).toHaveAttribute('aria-expanded','true');
  await page.keyboard.press('Escape');await expect(partner).toHaveAttribute('aria-expanded','false');
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused();
  await trigger.click();await expect(close).toBeFocused();await close.click();await expect(trigger).toBeFocused();
});


async function seedMaterialControls(request:import('@playwright/test').APIRequestContext){
  const session=adminSession(),headers={Authorization:`Bearer ${session.access_token}`};
  const response=await request.post(API+'/partners',{headers,data:{name:'合成分页筛选 '+randomUUID()}});
  expect(response.status()).toBe(201);const partner=await response.json();
  execFileSync('../.venv/bin/python',['-c',`
import os,sys
sys.path.insert(0,'..')
from backend.tests.support.model_test_boundary import validation_url
validation_url(os.environ['DATABASE_URL'],scoped=True)
from backend.app.database import get_db
from backend.app import profile_sources
pid=sys.argv[1]
with get_db() as conn:
    assert conn.execute('SELECT current_database()').fetchone()[0] in ('banfei_agent_test','banfei_validation')
    assert conn.execute('SELECT current_schema()').fetchone()[0].startswith('validation_')
    for i in range(64):
        cid=pid+'-card-'+str(i)
        fid=cid+'-file'
        category=['marketing-1','delivery-1','technical-1'][i%3]
        title=('失败资料 ' if i<55 else '正常资料 ')+str(i).zfill(2)
        conn.execute('INSERT INTO cases (id,partner_id,title,description,category_id,visible,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',(cid,pid,title,'合成资料，仅用于隔离验证。',category,0,'2026-10-24','2026-10-24'))
        conn.execute('INSERT INTO deliverables (id,case_id,filename,file_path,file_type,created_at,extracted_text,processing_status) VALUES (?,?,?,?,?,?,?,?)',(fid,cid,'合成.txt','/tmp/'+fid+'.txt','txt','2026-10-24','合成正文','ready'))
        profile_sources.put(conn,profile_sources.source(conn,pid,'attachment',fid),'failed' if i<55 else 'ready')
        if i==0:
            for j in range(2):
                extra=fid+'-extra-'+str(j)
                conn.execute('INSERT INTO deliverables (id,case_id,filename,file_path,file_type,created_at,processing_status) VALUES (?,?,?,?,?,?,?)',(extra,cid,'合成额外附件.txt','/tmp/'+extra+'.txt','txt','2026-10-24','failed'))
`,partner.id]);
  return {session,partner};
}
async function materialChange(page:Page,action:()=>Promise<unknown>,matches:(url:URL)=>boolean){
  const response=page.waitForResponse(r=>{const url=new URL(r.url());return url.pathname==='/api/admin/partner-materials'&&r.request().method()==='GET'&&matches(url);});
  await action();expect((await response).ok()).toBe(true);
  await expect(page.getByRole('navigation',{name:'伙伴资料分页'})).toHaveAttribute('aria-busy','false');
}
const materialIds=(page:Page)=>page.locator('[data-material-id]').evaluateAll(cards=>cards.map(card=>card.getAttribute('data-material-id')!));

test('material controls: 10 20 50 count cards across groups and preserve failed filter across pages',async({page,request})=>{
  const {session,partner}=await seedMaterialControls(request);await setSession(page,session);
  await page.goto('/admin/partner-materials?partner_id='+partner.id);
  const cards=page.locator('[data-material-id]'),pager=page.getByRole('navigation',{name:'伙伴资料分页'}),size=page.getByLabel('每页条数',{exact:true}),status=page.getByLabel('状态',{exact:true});
  await expect(cards).toHaveCount(10);await expect(size).toHaveValue('10');await expect(pager).toContainText('共 64 条');
  expect(await size.locator('option').evaluateAll(options=>options.map(option=>(option as HTMLOptionElement).value))).toEqual(['10','20','50']);
  expect(await status.locator('option').allTextContents()).toEqual(['全部资料','处理失败']);
  await materialChange(page,()=>status.selectOption('failed'),u=>u.searchParams.get('status')==='failed');
  await expect(pager).toContainText('共 55 条');await expect(cards).toHaveCount(10);await expect(page.locator('[data-material-id]').filter({hasText:'3 个文件'})).toHaveCount(1);
  await materialChange(page,()=>pager.getByRole('button',{name:'下一页',exact:true}).click(),u=>u.searchParams.get('page')==='2');
  await expect(cards).toHaveCount(10);
  await materialChange(page,()=>size.selectOption('20'),u=>u.searchParams.get('page_size')==='20'&&!u.searchParams.has('page'));
  await expect(cards).toHaveCount(20);expect(new URL(page.url()).searchParams.get('partner_id')).toBe(partner.id);await expect(status).toHaveValue('failed');await expect(pager).toContainText('共 3 页');
  await page.getByLabel('跳转页码').fill('3');
  await materialChange(page,()=>pager.getByRole('button',{name:'跳转',exact:true}).click(),u=>u.searchParams.get('page')==='3');
  await expect(cards).toHaveCount(15);
  await materialChange(page,()=>size.selectOption('50'),u=>u.searchParams.get('page_size')==='50'&&!u.searchParams.has('page'));
  await expect(cards).toHaveCount(50);const first=await materialIds(page);await expect(pager).toContainText('共 2 页');
  await materialChange(page,()=>pager.getByRole('button',{name:'下一页',exact:true}).click(),u=>u.searchParams.get('page')==='2'&&u.searchParams.get('page_size')==='50');
  await expect(cards).toHaveCount(5);const all=[...first,...await materialIds(page)];expect(all).toHaveLength(55);expect(new Set(all).size).toBe(55);
  await materialChange(page,()=>size.selectOption('10'),u=>u.searchParams.get('page_size')==='10'&&!u.searchParams.has('page'));
  await expect(cards).toHaveCount(10);await expect(pager).toContainText('共 55 条');await expect(status).toHaveValue('failed');
});

test('material controls: status combines partner category and name and resets each filter to first page',async({page,request})=>{
  const {session,partner}=await seedMaterialControls(request);await setSession(page,session);
  await page.goto('/admin/partner-materials?partner_id='+partner.id+'&page=2');
  const cards=page.locator('[data-material-id]'),status=page.getByLabel('状态',{exact:true}),pager=page.getByRole('navigation',{name:'伙伴资料分页'});
  await expect(cards).toHaveCount(10);
  await materialChange(page,()=>status.selectOption('failed'),u=>u.searchParams.get('status')==='failed'&&!u.searchParams.has('page'));
  await expect(pager).toContainText('共 55 条');
  await materialChange(page,()=>pager.getByRole('button',{name:'下一页',exact:true}).click(),u=>u.searchParams.get('page')==='2');
  await materialChange(page,()=>page.getByLabel('筛选一级分类',{exact:true}).selectOption('technical'),u=>u.searchParams.get('category_group')==='technical'&&!u.searchParams.has('page'));
  await expect(pager).toContainText('共 18 条');
  await materialChange(page,()=>page.getByLabel('筛选二级分类',{exact:true}).selectOption('technical-1'),u=>u.searchParams.get('category_id')==='technical-1');
  await page.getByLabel('资料名称',{exact:true}).fill('失败资料 0');
  await materialChange(page,()=>page.getByRole('button',{name:'搜索',exact:true}).click(),u=>u.searchParams.get('q')==='失败资料 0');
  await expect(cards).toHaveCount(3);await expect(pager).toContainText('共 3 条');
  const selected=new URL(page.url()).searchParams;expect(selected.get('partner_id')).toBe(partner.id);expect(selected.get('category_group')).toBe('technical');expect(selected.get('category_id')).toBe('technical-1');expect(selected.get('status')).toBe('failed');
  await materialChange(page,()=>page.getByLabel('每页条数',{exact:true}).selectOption('20'),u=>u.searchParams.get('page_size')==='20');
  await expect(cards).toHaveCount(3);
  await materialChange(page,()=>status.selectOption(''),u=>!u.searchParams.has('status'));
  await expect(cards).toHaveCount(3);await expect(page.getByLabel('资料名称',{exact:true})).toHaveValue('失败资料 0');await expect(page.getByLabel('筛选二级分类',{exact:true})).toHaveValue('technical-1');
  await page.getByLabel('资料名称',{exact:true}).fill('不存在的合成资料');
  await materialChange(page,()=>page.getByRole('button',{name:'搜索',exact:true}).click(),u=>u.searchParams.get('q')==='不存在的合成资料');
  await expect(cards).toHaveCount(0);await expect(page.getByText('暂无符合条件的资料。',{exact:true})).toBeVisible();await expect(page.getByLabel('每页条数',{exact:true})).toHaveValue('20');
});

for(const width of [1440,390])test('material controls: aligned controls and pagination viewport '+width,async({page,request},info)=>{
  const {session,partner}=await seedMaterialControls(request);await setSession(page,session);await page.setViewportSize({width,height:width===390?844:1000});
  await page.goto('/admin/partner-materials?partner_id='+partner.id+'&status=failed&page_size=20');
  await expect(page.locator('[data-material-id]')).toHaveCount(20);await expect(page.getByLabel('状态',{exact:true})).toHaveValue('failed');await expect(page.getByLabel('每页条数',{exact:true})).toHaveValue('20');
  await expect(page.getByText('处理状态',{exact:true})).toHaveCount(0);
  const controls=[page.getByLabel('筛选伙伴',{exact:true}),page.getByLabel('筛选一级分类',{exact:true}),page.getByLabel('筛选二级分类',{exact:true}),page.getByLabel('状态',{exact:true}),page.getByLabel('资料名称',{exact:true})];
  const boxes=await Promise.all(controls.map(c=>c.boundingBox()));expect(boxes.every(Boolean)).toBe(true);
  if(width===1440)expect(Math.max(...boxes.map(b=>b!.y))-Math.min(...boxes.map(b=>b!.y))).toBeLessThan(2);
  for(const box of boxes){expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(width);}
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:info.outputPath('materials-controls-'+width+'.png')});
  await page.getByRole('navigation',{name:'伙伴资料分页'}).scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('materials-pagination-'+width+'.png')});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
