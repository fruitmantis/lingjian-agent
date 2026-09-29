import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {expect,test,type Page} from '@playwright/test';
import {fixtureLogin} from './identity-fixture';
const API='http://localhost:8000';
function adminSession(){return JSON.parse(readFileSync('/tmp/lingjian-enablement-e2e/visual-session.json','utf8'));}
async function setSession(page:Page,session:ReturnType<typeof adminSession>){await page.addInitScript(s=>{localStorage.setItem(`banfei:${s.user.role}:token`,s.access_token);localStorage.setItem(`banfei:${s.user.role}:user`,JSON.stringify(s.user));},session);}

test('one materials page: partner shortcut, private profile originals and legacy file classification',async({page,request})=>{
  const session=adminSession(),headers={Authorization:`Bearer ${session.access_token}`};await setSession(page,session);
  const partner=await (await request.post(API+'/partners',{headers,data:{name:'资料验证 '+randomUUID()}})).json();
  const legacy=await (await request.post(`${API}/partners/${partner.id}/documents`,{headers,multipart:{file:{name:'旧资料.txt',mimeType:'text/plain',buffer:Buffer.from('完整原生文字\n下一行保留')}}})).json();
  await page.goto('/admin/partners/'+partner.id);
  await expect(page.getByRole('heading',{name:'伙伴案例',exact:true})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'伙伴资料',exact:true})).toHaveCount(0);
  const pdfSource=execFileSync('../.venv/bin/python',['-c','import io,sys;from docx import Document;d=Document();d.add_paragraph("导入画像直接采用，不调用模型。");b=io.BytesIO();d.save(b);sys.stdout.buffer.write(b.getvalue())']);
  await page.getByText('导入 DOCX 画像',{exact:true}).locator('input').setInputFiles({name:'初始化画像.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:pdfSource});
  await expect(page.locator('.ai-profile-text')).toHaveText('导入画像直接采用，不调用模型。',{timeout:30000});
  await page.getByText('画像原件',{exact:true}).click();
  const office=page.locator('article').filter({hasText:'初始化画像.docx'});await expect(office).toContainText('已处理');
  await expect(page.locator('article').filter({hasText:'旧资料.txt'})).toHaveCount(0);
  await office.getByRole('button',{name:'在线查看'}).click();await expect(page.getByRole('dialog').locator('object[type="application/pdf"]')).toBeVisible();
  await page.getByRole('dialog').getByRole('button',{name:'关闭'}).click();
  const download=page.waitForEvent('download');await office.getByRole('button',{name:'下载原件'}).click();expect((await download).suggestedFilename()).toBe('初始化画像.docx');
  await page.getByRole('link',{name:'管理资料',exact:true}).click();await expect(page).toHaveURL(new RegExp('/admin/partner-materials\\?partner_id='+partner.id));
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
  await page.getByRole('button',{name:'查看全部伙伴资料'}).click();await expect(page.getByLabel('筛选伙伴')).toHaveAttribute('data-partner-id','');
  await page.getByRole('navigation',{name:'后台导航'}).getByRole('link',{name:'伙伴资料',exact:true}).click();await expect(page.getByRole('heading',{name:'伙伴资料',exact:true})).toBeVisible();
});

test('multiple files in one card, safe preview, same-ID replacement and live display permission',async({page,request,browser})=>{
  const session=adminSession(),headers={Authorization:`Bearer ${session.access_token}`};await setSession(page,session);
  const p=await (await request.post(API+'/partners',{headers,data:{name:'案例验证 '+randomUUID()}})).json();
  await page.goto('/admin/partner-materials?partner_id='+p.id);await page.getByRole('button',{name:'新增资料',exact:true}).click();
  const form=page.getByRole('dialog',{name:'新增资料'});await expect(form.getByLabel('关联伙伴')).toHaveAttribute('data-partner-id',p.id);
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
  await detail.getByLabel('替换 案例材料.md',{exact:true}).setInputFiles({name:'更新材料.txt',mimeType:'text/plain',buffer:Buffer.from('替换后的原生文字')});
  await expect(detail.getByText('更新材料.txt',{exact:true})).toBeVisible();await expect.poll(async()=>(await request.get(url,{headers})).text()).toBe('替换后的原生文字');
  const context=await browser.newContext();const ordinary=await context.newPage();await setSession(ordinary,user);await ordinary.goto(`/resources/case/${cid}`);await expect(ordinary.getByRole('heading',{name:'数据库原生文档案例',exact:true})).toBeVisible();
  await detail.getByLabel('展示',{exact:true}).uncheck();await expect.poll(async()=>(await request.get(url,{headers:uh})).status()).toBe(404);await ordinary.reload();await expect(ordinary.getByRole('alert').filter({hasText:'内容不存在'})).toContainText('内容不存在');await context.close();
  await detail.getByRole('button',{name:'关闭',exact:true}).click();await expect(page.locator('[data-material-id]')).toHaveCount(1);await expect(page.locator('[data-material-id]')).toContainText('2 个文件');
  expect((await request.get(`${API}/partners/${p.id}`,{headers})).ok()).toBeTruthy();expect((await (await request.get(`${API}/partners/${p.id}`,{headers})).json()).ai_profile).toBeNull();
});

test('global partner/category search, three-column groups and total-page jump',async({page,request})=>{
  const session=adminSession(),headers={Authorization:`Bearer ${session.access_token}`};await setSession(page,session);await page.setViewportSize({width:1440,height:1000});
  const name='卡片分组 '+randomUUID(),p=await (await request.post(API+'/partners',{headers,data:{name}})).json();
  for(let i=0;i<14;i++)expect((await request.post(API+'/cases',{headers,data:{partner_id:p.id,title:`目录验证 ${i}`,category_id:i<7?'marketing-1':'technical-3'}})).status()).toBe(201);
  await page.goto('/admin/partner-materials?partner_id='+p.id);await expect(page.locator('[data-material-id]')).toHaveCount(12);
  await expect(page.getByRole('heading',{name:'营销与宣传',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'技术案例',exact:true})).toBeVisible();
  const cards=page.locator('[data-material-id]');const boxes=await Promise.all([cards.nth(0).boundingBox(),cards.nth(1).boundingBox(),cards.nth(2).boundingBox()]);expect(Math.max(...boxes.map(b=>b!.y))-Math.min(...boxes.map(b=>b!.y))).toBeLessThan(2);
  await expect(page.getByRole('navigation',{name:'伙伴资料分页'})).toContainText('共 2 页');await page.getByLabel('跳转页码').fill('2');await page.getByRole('button',{name:'跳转',exact:true}).click();await expect(cards).toHaveCount(2);
  await page.getByLabel('筛选一级分类').selectOption('technical');await page.getByLabel('筛选二级分类').selectOption('technical-3');await expect(cards).toHaveCount(7);
  await page.getByLabel('资料名称').fill('目录验证 13');await page.getByRole('button',{name:'搜索',exact:true}).click();await expect(cards).toHaveCount(1);await expect(cards).toContainText('目录验证 13');
  await page.getByRole('button',{name:'查看全部伙伴资料'}).click();await expect(page.getByLabel('筛选伙伴')).toHaveAttribute('data-partner-id','');await expect(cards).toHaveCount(1);
  await page.goto('/admin/partner-materials?partner_id='+p.id);await expect(cards).toHaveCount(12);await page.screenshot({path:'/tmp/banfei-material-manager.png',fullPage:true});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
