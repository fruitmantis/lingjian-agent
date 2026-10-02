import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import {match, plan} from './coze-fixtures';

// Browser-only fixtures: no authentication, resource mutation or model request reaches the API.
for (const width of [1366,1920]) test(`shared UI surfaces and controls ${width}`,async({page})=>{
  await page.setViewportSize({width,height:width===1366?768:1080});
  await page.addInitScript(()=>{localStorage.setItem('banfei:user:token','synthetic-user');localStorage.setItem('banfei:admin:token','synthetic-admin');});
  let writes=0;
  await page.route('**/*',route=>{
    const u=new URL(route.request().url());
    if(u.port!=='8000'&&!u.pathname.startsWith('/api/'))return ['localhost','127.0.0.1'].includes(u.hostname)?route.continue():route.abort();
    const p=u.pathname.replace(/^\/api/,'');
    if(route.request().method()!=='GET'){writes++;return route.abort();}
    let json:unknown={items:[],total:0,page:1,pageSize:20,totalPages:0};
    const partner={id:'ui-preview',name:'合成视觉伙伴',capabilities:'数据库 · 系统集成',industries:'金融',service_areas:'广东',intro:'用于界面验证的合成数据。',ai_profile:'数据库交付及应用集成基础。',created_at:'2026-09-01',case_count:1,deliverable_count:1};
    if(p==='/auth/me')json={id:'ui-admin',username:'ui-admin',role:route.request().headers().authorization==='Bearer synthetic-admin'?'admin':'user',status:'active',must_change_password:false};
    else if(p==='/partners'||p==='/partners/profiles')json=[partner];
    else if(p.startsWith('/partners/'))json=partner;
    else if(p==='/agent/tasks/coze-match')json=match;
    else if(p==='/agent/tasks/coze-plan')json={id:'coze-plan',task_type:'development_plan',taskStatus:'ready'};
    else if(p==='/development/plans/coze-plan')json=plan;
    else if(p==='/admin/partner-materials')json={items:[{kind:'case',id:'ui-material',partner_id:partner.id,partner_name:partner.name,title:'合成伙伴资料',description:'仅用于隔离界面检查。',category_id:'technical-3',visible:false,file_count:0,processing_status:'ready',updated_at:'2026-09-28'}],total:1,partners:[partner]};
    else if(p==='/enablement/context')json={partner,evidence:[],project:null,shared_case:null};
    else if(p==='/enablement/resource-filters')json={roles:[],zones:[],case_categories:[]};
    else if(p.endsWith('/deliverables'))json=[];
    else if(p==='/enablement/resources')json={items:[{source_type:u.searchParams.get('source_type')||'course',source_id:'ui-resource',source_version:1,title:'用于布局验证的合成资源',summary:'此记录仅存在于浏览器请求拦截中。',source_url:'https://example.com/resource',capabilities:[],roles:[],zones:[],level:'advanced',category:'技术案例',subcategory:'架构设计',contributor_id:partner.id,contributor_name:partner.name}],total:1};
    else if(p.startsWith('/enablement/resources/'))json={source_type:p.split('/')[3],source_id:'ui-resource',source_version:1,title:'用于布局验证的合成资源',summary:'仅用于界面测试。',capabilities:[],roles:[],zones:[],level:'advanced',source_url:'https://example.com/resource',category:'技术案例',subcategory:'架构设计',contributor_id:partner.id,contributor_name:partner.name};
    else if(p==='/admin/reports')json={overview:{totalDemands:1,thisMonthDemands:1,totalPartners:1,partnersWithProfile:1,activePartners:1,noPartnerDemands:0,partialDemands:0,pendingSuggestions:0},capabilityDist:[],industryDist:[],regionDist:[],deliveryTypeDist:[],supplyGaps:[],activePartnerCount:0,activePartnerRatio:0,topRecommendedPartners:[],inactivePartners:[],topFormalTags:[],uncoveredClues:0,pendingSuggestions:0};
    else if(p==='/admin/dashboard')json={users:8,tasks:20};
    else if(p==='/admin/model-configs'||p==='/admin/model-configs/usage')json=[];
    return route.fulfill({json});
  });
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const directory=path.resolve(process.env.UI_SYSTEM_EVIDENCE_DIR||'/tmp/lingjian-ui-system');await mkdir(directory,{recursive:true});
  const shadows:string[]=[],hoverShadows:string[]=[];
  for(const [url,selector,name] of [
    ['/scenes','.scene-gallery-card.is-interactive','scenes'],
    ['/partners','.partner-insight-card','partners'],
    ['/resources?resource_type=course','.learning-card','course'],
    ['/resources?resource_type=lab','.learning-card','lab'],
    ['/resources?resource_type=case','.enablement-resource-card','case'],
  ]){
    await page.goto(url);const card=page.locator(selector).first();await expect(card).toBeVisible();
    await page.mouse.move(0,0);await page.waitForTimeout(220);
    // At DPR 1 Chromium snaps the shared 0.5 CSS px border to one device pixel.
    await expect(card).toHaveCSS('border-top-width','1px');await expect(card).toHaveCSS('border-top-color','rgb(228, 228, 231)');await expect(card).toHaveCSS('border-radius','16px');
    const entry=card.locator('.card-entry-label');
    await expect(entry).toHaveCSS('font-size','12px');await expect(entry).toHaveCSS('color','rgb(96, 96, 92)');
    await expect(entry.locator('svg')).toHaveAttribute('width','14');
    shadows.push(await card.evaluate(e=>getComputedStyle(e).boxShadow));
    await card.hover();await expect(card).toHaveCSS('transform','none');await page.waitForTimeout(220);
    await expect(card).toHaveCSS('background-color','rgb(244, 244, 243)');
    await expect(entry).toHaveCSS('color','rgb(38, 38, 38)');
    hoverShadows.push(await card.evaluate(e=>getComputedStyle(e).boxShadow));
    // Cancel this one navigation to inspect pointer focus and the native full-card link.
    const href=await card.locator('a').last().getAttribute('href');
    await card.evaluate(el=>el.addEventListener('click',event=>{
      event.preventDefault();el.setAttribute('data-clicked-href',(event.target as HTMLElement).closest('a')?.getAttribute('href')||'');
    },{capture:true,once:true}));
    await card.click({position:{x:20,y:20}});await expect(card).toHaveAttribute('data-clicked-href',href!);
    await expect(card).toHaveCSS('outline-style','none');
    await page.keyboard.press('Tab');await card.locator('a').last().focus();await expect(card).toHaveCSS('outline-style','solid');
    await page.emulateMedia({reducedMotion:'reduce'});await expect(card).toHaveCSS('transform','none');await page.emulateMedia({reducedMotion:'no-preference'});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    if(name==='partners'||name==='course'){await page.mouse.move(0,0);await page.screenshot({path:path.join(directory,`${name}-${width}.png`),fullPage:true});}
    if(['course','lab','case'].includes(name)){
      // The footer label must reach the same native link, including stretched course/lab links.
      await entry.scrollIntoViewIfNeeded();const box=(await entry.boundingBox())!;
      await page.mouse.click(box.x+box.width/2,box.y+box.height/2);await expect(page).toHaveURL(new RegExp(`/resources/${name}/ui-resource`));
      await expect(page.getByRole('heading',{name:'用于布局验证的合成资源',exact:true})).toBeVisible();
    }
  }
  expect(new Set(shadows).size).toBe(1);expect(shadows[0]).not.toBe('none');expect(hoverShadows).toEqual(shadows);
  for(const [url,selector,href] of [
    ['/tasks/coze-match','.recommendation-item','/partners/coze-partner'],
    ['/tasks/coze-plan','.advisor-resource','/resources/lab/lab-0?source_version=1'],
    ['/partners/ui-preview','.case-item','/resources/case/ui-resource'],
  ]){
    await page.goto(url);const card=page.locator(selector).first(),link=card.locator('.card-entry-link');
    await expect(link).toBeVisible();await page.mouse.move(0,0);
    await expect(link).toHaveCSS('border-top-width','0px');await expect(link).toHaveCSS('background-color','rgba(0, 0, 0, 0)');
    await expect(link.locator('.card-entry-label')).toHaveCSS('color','rgb(96, 96, 92)');
    await page.screenshot({path:path.join(directory,`${selector.slice(1)}-${width}.png`),fullPage:true});
    await expect(link).toHaveAttribute('href',href);await link.focus();await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(href.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$'));
  }
  await page.goto('/admin/partner-materials');
  const material=page.locator('.ui-catalog-card').first(),open=material.getByRole('button',{name:'查看与管理',exact:true});
  await expect(open).toBeVisible();await page.mouse.move(0,0);
  await expect(open).toHaveCSS('border-top-width','0px');await expect(open).toHaveCSS('background-color','rgba(0, 0, 0, 0)');
  await expect(open.locator('.card-entry-label')).toHaveCSS('font-size','12px');
  await page.screenshot({path:path.join(directory,`material-entry-${width}.png`),fullPage:true});
  await page.keyboard.press('Tab');await open.focus();await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog',{name:'合成伙伴资料'})).toBeVisible();
  await page.getByRole('button',{name:'关闭',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.goto('/?mode=development&partner_id=ui-preview');
  for(const selector of ['.development-context-row','.development-composer>.development-form']){
    const surface=page.locator(selector);await expect(surface).toBeVisible();await surface.hover();await expect(surface).toHaveCSS('transform','none');await expect(surface).toHaveCSS('border-top-width','0px');
  }
  await expect(page.getByLabel('发展方向',{exact:true})).toHaveCSS('height','140px');
  await expect(page.getByLabel('关联已有伙伴资料（可选）',{exact:true})).toHaveCSS('height','40px');
  await expect(page.getByRole('tab',{name:'伙伴发展',exact:true})).toHaveAttribute('aria-selected','true');
  await page.getByLabel('发展方向',{exact:true}).fill('希望具备 Agent 项目交付能力');
  await expect(page.getByRole('button',{name:'开始',exact:true})).toHaveCSS('background-color','rgb(199, 0, 11)');
  await page.screenshot({path:path.join(directory,`development-${width}.png`),fullPage:true});
  await page.goto('/admin/partners');await expect(page.getByPlaceholder('伙伴名称',{exact:true})).toHaveCSS('height','40px');
  const groups=page.getByRole('group');await expect(groups.getByRole('checkbox')).toHaveCount(52);
  await page.getByLabel('金融',{exact:true}).check();await page.getByLabel('广东',{exact:true}).check();await page.getByLabel('欧洲',{exact:true}).check();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const overseas=page.locator('[data-region-type=overseas] .classification-options label');
  for(const item of await overseas.all())await expect(item).toHaveCSS('height','20px');
  await page.screenshot({path:path.join(directory,`admin-partners-${width}.png`),fullPage:true});
  await page.goto('/admin/models');await page.getByRole('button',{name:'新增配置',exact:true}).click();
  await expect(page.getByPlaceholder('配置名称',{exact:true})).toHaveCSS('height','32px');
  await expect(page.getByRole('button',{name:'保存',exact:true})).toHaveCSS('height','32px');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.getByRole('button',{name:'取消',exact:true}).click();await expect(page.getByPlaceholder('配置名称',{exact:true})).toHaveCount(0);
  await page.goto('/admin/reports');await expect(page.locator('.ui-report-metrics .ui-metric')).toHaveCount(8);
  const rows=await page.locator('.ui-report-metrics .ui-metric').evaluateAll(elements=>elements.map(e=>Math.round(e.getBoundingClientRect().y)));
  expect(new Set(rows.slice(0,4)).size).toBe(1);expect(new Set(rows.slice(4)).size).toBe(1);expect(rows[4]).toBeGreaterThan(rows[0]);
  await page.screenshot({path:path.join(directory,`admin-reports-${width}.png`),fullPage:true});
  expect(writes).toBe(0);expect(errors).toEqual([]);
});
