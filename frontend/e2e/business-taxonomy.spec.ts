import {test,expect} from '@playwright/test';
import standard from '../../shared/business-taxonomy.json';
const API='http://127.0.0.1:8100';
for(const width of [1366,1920])test(`standard industry and grouped regions ${width}`,async({page,request})=>{
 const login=await request.post(API+'/auth/login',{data:{username:'admin1',password:'ValidationPass123'}});expect(login.ok()).toBeTruthy();const session=await login.json();const headers={Authorization:`Bearer ${session.access_token}`};await page.addInitScript(s=>localStorage.setItem('token',s.access_token),session);await page.setViewportSize({width,height:width===1366?768:1080});
 await page.goto('/admin/partners');const section=page.locator('section').filter({has:page.getByRole('heading',{name:'新增伙伴',exact:true})});
 const name=`合成分类测试-${width}-${Date.now()}`;await section.getByPlaceholder('伙伴名称').fill(name);
 const industry=section.getByRole('group',{name:'行业经验（多选）',exact:true});await expect(industry.getByRole('checkbox')).toHaveCount(12);expect(await industry.locator('label').allTextContents()).toEqual(standard.industries);
 const domestic=section.getByRole('group',{name:'国内省级区域（多选）',exact:true}),overseas=section.getByRole('group',{name:'海外区域（多选）',exact:true});await expect(domestic.getByRole('checkbox')).toHaveCount(34);expect(await overseas.locator('label').allTextContents()).toEqual(standard.region_types.overseas);
 await industry.getByLabel('金融',{exact:true}).check();await industry.getByLabel('互联网',{exact:true}).check();await domestic.getByLabel('广东',{exact:true}).check();await domestic.getByLabel('陕西',{exact:true}).check();await overseas.getByLabel('亚太',{exact:true}).check();await overseas.getByLabel('欧洲',{exact:true}).check();
 const saved=page.waitForResponse(r=>r.url()===API+'/partners'&&r.request().method()==='POST');await section.getByRole('button',{name:'新增伙伴',exact:true}).click();const res=await saved;expect(res.status()).toBe(201);const row=await res.json();expect(row.industries).toBe('金融,互联网');expect(row.region_groups).toEqual([{region_type:'domestic',regions:['广东','陕西']},{region_type:'overseas',regions:['亚太','欧洲']}]);
 await page.goto('/admin/partners/'+row.id);await expect(page.getByLabel('金融',{exact:true})).toBeChecked();await expect(page.getByLabel('亚太',{exact:true})).toBeChecked();await page.getByLabel('欧洲',{exact:true}).uncheck();const updated=page.waitForResponse(r=>r.url()===API+'/partners/'+row.id&&r.request().method()==='PUT');await page.getByRole('button',{name:'保存伙伴信息'}).click();expect((await updated).ok()).toBeTruthy();
 await page.goto('/partners');await expect(page.getByLabel('行业筛选',{exact:true})).toHaveCount(0);await expect(page.getByLabel('区域筛选',{exact:true})).toHaveCount(0);await page.getByPlaceholder('搜索伙伴名称、能力、行业或区域').fill(name);await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 for(const data of [{industries:'银行'},{service_areas:'深圳'},{service_areas:'海外地区'}])expect((await request.put(API+'/partners/'+row.id,{headers,data})).status()).toBe(422);
 await page.screenshot({path:`/tmp/business-taxonomy-${width}.png`,fullPage:true});
});
