import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';

// Browser-only fixtures: no authentication, resource mutation or model request reaches the API.
for (const width of [1366,1920]) test(`shared UI surfaces and controls ${width}`,async({page})=>{
  await page.setViewportSize({width,height:width===1366?768:1080});
  await page.addInitScript(()=>localStorage.setItem('token','synthetic-browser-only'));
  let writes=0;
  await page.route(/https?:\/\/(127\.0\.0\.1|localhost):(8100|8000)\//,route=>{
    const u=new URL(route.request().url()),p=u.pathname;
    if(route.request().method()!=='GET'){writes++;return route.abort();}
    let json:unknown={items:[],total:0,page:1,pageSize:20,totalPages:0};
    const partner={id:'ui-preview',name:'合成视觉伙伴',capabilities:'数据库 · 系统集成',industries:'金融',service_areas:'广东',intro:'用于界面验证的合成数据。',ai_profile:'数据库交付及应用集成基础。',created_at:'2026-09-01',case_count:1,deliverable_count:1};
    if(p==='/auth/me')json={id:'ui-admin',username:'ui-admin',role:'admin',status:'active',must_change_password:false};
    else if(p==='/partners'||p==='/partners/profiles')json=[partner];
    else if(p==='/enablement/context')json={partner,evidence:[],project:null,shared_case:null};
    else if(p==='/enablement/resource-filters')json={capabilities:[]};
    else if(p==='/enablement/resources')json={items:[{source_type:u.searchParams.get('source_type')||'course',source_id:'ui-resource',source_version:1,title:'用于布局验证的合成资源',summary:'此记录仅存在于浏览器请求拦截中。',source_platform:'synthetic',capabilities:[],status:'published',availability:'available',difficulty:'advanced',language:'中文',review:null}],total:1};
    else if(p.startsWith('/enablement/resources/'))json={source_type:p.split('/')[3],source_id:'ui-resource',source_version:1,title:'用于布局验证的合成资源',summary:'仅用于界面测试。',capabilities:[],status:'published',availability:'available',source_platform:'synthetic',review:null};
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
    ['/resources?resource_type=course','.enablement-resource-card','course'],
    ['/resources?resource_type=lab','.enablement-resource-card','lab'],
    ['/resources?resource_type=case','.enablement-resource-card','case'],
  ]){
    await page.goto(url);const card=page.locator(selector).first();await expect(card).toBeVisible();
    await page.mouse.move(0,0);await page.waitForTimeout(220);
    await expect(card).toHaveCSS('border-top-width','0px');await expect(card).toHaveCSS('border-radius','8px');
    shadows.push(await card.evaluate(e=>getComputedStyle(e).boxShadow));
    await card.hover();await expect(card).toHaveCSS('transform','matrix(1, 0, 0, 1, 0, -2)');await page.waitForTimeout(220);
    hoverShadows.push(await card.evaluate(e=>getComputedStyle(e).boxShadow));
    await card.locator('a').last().focus();await expect(card).toHaveCSS('outline-style','solid');
    await page.emulateMedia({reducedMotion:'reduce'});await expect(card).toHaveCSS('transform','none');await page.emulateMedia({reducedMotion:'no-preference'});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    if(name==='partners'||name==='course'){await page.mouse.move(0,0);await page.screenshot({path:path.join(directory,`${name}-${width}.png`),fullPage:true});}
    if(['course','lab','case'].includes(name)){
      await card.locator('h2 a').click();await expect(page).toHaveURL(new RegExp(`/resources/${name}/ui-resource`));
      await expect(page.getByRole('heading',{name:'用于布局验证的合成资源',exact:true})).toBeVisible();
      await page.goto(url);await page.locator(selector).first().click({position:{x:12,y:12}});
      await expect(page).toHaveURL(new RegExp(`/resources/${name}/ui-resource`));
    }
  }
  expect(new Set(shadows).size).toBe(1);expect(shadows[0]).not.toBe('none');expect(new Set(hoverShadows).size).toBe(1);expect(hoverShadows[0]).not.toBe(shadows[0]);
  await page.goto('/?mode=development&partner_id=ui-preview');
  for(const selector of ['.development-context-row','.development-composer>.development-form']){
    const surface=page.locator(selector);await expect(surface).toBeVisible();await surface.hover();await expect(surface).toHaveCSS('transform','none');await expect(surface).toHaveCSS('border-top-width','0px');
  }
  await expect(page.getByLabel('发展方向',{exact:true})).toHaveCSS('height','176px');
  await expect(page.getByLabel('选择目标伙伴')).toHaveCSS('height','40px');
  await expect(page.getByRole('tab',{name:'能力发展',exact:true})).toHaveCSS('border-bottom-color','rgb(199, 0, 11)');
  await page.getByLabel('发展方向',{exact:true}).fill('希望具备 Agent 项目交付能力');
  await expect(page.getByRole('button',{name:'生成能力发展建议',exact:true})).toHaveCSS('background-color','rgb(199, 0, 11)');
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
