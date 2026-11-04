import {test,expect,type Page} from '@playwright/test';
import {mockDeviceSession} from './device-session-fixture';
import {readFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import identities from '../../shared/partner-identities.json';

for(const width of [1440,390])test(`partner identities maintain multiple values and display all without model calls ${width}`,async({page,request},info)=>{
 const origin=String(info.project.use.baseURL).replace(/\/$/,''),api=origin+'/api';
 const admin=JSON.parse(readFileSync(`${process.env.BANFEI_TEST_ROOT}/visual-session.json`,'utf8'));
 const headers={Authorization:`Bearer ${admin.access_token}`};
 const writes:string[]=[];page.on('request',r=>{if(r.method()==='POST'&&/\/(profile|batch-profile|agent\/tasks|development\/plans)(?:[?]|$)/.test(new URL(r.url()).pathname))writes.push(r.url());});
 await page.setViewportSize({width,height:900});
 await page.addInitScript(s=>{localStorage.setItem('banfei:admin:token',s.access_token);localStorage.setItem('banfei:admin:user',JSON.stringify(s.user));},admin);
 await page.goto('/admin/partners');
 const editor=page.locator('details').filter({has:page.locator('summary').filter({hasText:'新增伙伴'})}).first();
 await editor.locator('summary').click();
 const name='身份验证伙伴-'+randomUUID().slice(0,8);
 await editor.getByLabel('伙伴名称',{exact:true}).fill(name);
 const selection=editor.getByRole('group',{name:'伙伴身份（多选）',exact:true});
 await expect(selection.getByRole('checkbox')).toHaveCount(6);
 for(const label of identities.slice(0,2))await selection.getByRole('checkbox',{name:label,exact:true}).check();
 const created=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===api+'/partners');
 await editor.getByRole('button',{name:'新增伙伴',exact:true}).click();
 const response=await created;expect(response.status()).toBe(201);const partner=await response.json();
 expect(partner.identities).toEqual(identities.slice(0,2));
 await page.goto('/admin/partners/'+partner.id);
 const fields=page.getByRole('group',{name:'伙伴身份（多选）',exact:true});
 for(const label of identities.slice(0,2))await expect(fields.getByRole('checkbox',{name:label,exact:true})).toBeChecked();
 for(const label of identities)await fields.getByRole('checkbox',{name:label,exact:true}).check();
 await page.getByRole('button',{name:'保存伙伴信息',exact:true}).click();
 await expect(page.getByText('伙伴信息已保存。',{exact:true})).toBeVisible();await page.reload();
 for(const label of identities)await expect(page.getByRole('checkbox',{name:label,exact:true})).toBeChecked();
 await page.screenshot({path:info.outputPath(`admin-identities-${width}.png`),fullPage:true});
 expect((await (await request.get(api+'/partners/'+partner.id,{headers})).json()).identities).toEqual(identities);
 const identity=await page.request.post(api+'/auth/identity/session',{headers:{Origin:origin},data:{create:true}});
 expect(identity.status()).toBe(200);const user=await identity.json();
 await page.addInitScript(s=>{localStorage.setItem('banfei:user:token',s.access_token);localStorage.setItem('banfei:user:user',JSON.stringify(s.user));localStorage.setItem('banfei:user:device-secret',s.device_secret);},user);
 await page.goto('/partners');await page.getByLabel('搜索伙伴',{exact:true}).fill(name);
 const card=page.locator('.partner-insight-card');await expect(card).toHaveCount(1);
 await expect(card.getByRole('list',{name:'伙伴身份',exact:true}).getByRole('listitem')).toHaveText(identities);
 await page.screenshot({path:info.outputPath(`directory-identities-${width}.png`),fullPage:true});
 await page.goto('/partners/'+partner.id);
 await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
 await expect(page.getByRole('list',{name:'伙伴身份',exact:true}).getByRole('listitem')).toHaveText(identities);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:info.outputPath(`detail-identities-${width}.png`),fullPage:true});
 await page.goto('/admin/partners/'+partner.id);
 for(const label of identities)await page.getByRole('checkbox',{name:label,exact:true}).uncheck();
 await page.getByRole('button',{name:'保存伙伴信息',exact:true}).click();
 await expect(page.getByText('伙伴信息已保存。',{exact:true})).toBeVisible();
 await page.goto('/partners/'+partner.id);
 await expect(page.getByTestId('partner-identities')).toHaveCount(0);
 expect(writes).toEqual([]);
});


async function visibilityFixture(page:Page){
 const user={id:'identity-visibility-user',username:'visibility',role:'user',status:'active',must_change_password:false};
 const common={identities:undefined as string[]|undefined,capabilities:null as string|null,industries:null as string|null,service_areas:null as string|null,ai_profile:null,profile_status:'missing',created_at:'2026-11-04',case_count:0,deliverable_count:0};
 const rows=[
  {...common,id:'empty-identities',name:'未维护身份伙伴',identities:[],capabilities:'服务合作伙伴',industries:'金融',service_areas:'广东'},
  {...common,id:'legacy-identities',name:'历史未提供身份伙伴'},
  {...common,id:'all-identities',name:'全部身份伙伴',identities,capabilities:'AI,数据治理',industries:'金融',service_areas:'广东'},
  {...common,id:'service-identities',name:'服务身份伙伴',identities:[identities[1]],capabilities:'AI',industries:'制造与工业',service_areas:'北京'},
  {...common,id:'software-identities',name:'软件身份伙伴',identities:[identities[0]],capabilities:'数据治理',industries:'金融',service_areas:'广东'},
 ];
 const unexpected:string[]=[];
 await page.addInitScript(user=>{localStorage.setItem('banfei:user:token','synthetic-visibility-token');localStorage.setItem('banfei:user:user',JSON.stringify(user));},user);
 await page.route('**/api/**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname.replace(/^\/api/,'');
  if(req.method()!=='GET'){unexpected.push(req.method()+' '+path);return route.fulfill({status:409,json:{detail:'Unexpected isolated write'}});}
  if(path==='/auth/me')return route.fulfill({json:user});
  if(path==='/health')return route.fulfill({json:{status:'ok'}});
  if(path==='/agents')return route.fulfill({json:[]});
  if(path==='/agent/tasks')return route.fulfill({json:{items:[],total:0,page:1,pageSize:20,totalPages:0}});
  if(path==='/partners/profiles')return route.fulfill({json:rows});
  if(path.startsWith('/partners/')){const row=rows.find(row=>row.id===path.split('/').pop());if(row)return route.fulfill({json:row});}
  if(path==='/enablement/resources')return route.fulfill({json:{items:[],total:0,page:1,pageSize:20,totalPages:0}});
  unexpected.push(path);return route.fulfill({status:404,json:{detail:'Unexpected isolated read'}});
 });
 await mockDeviceSession(page);
 return {rows,unexpected};
}

for(const width of [1440,390])test(`identity visibility hides empty directory and detail rows while retaining every maintained label ${width}`,async({page},info)=>{
 const {rows,unexpected}=await visibilityFixture(page);await page.setViewportSize({width,height:900});
 await page.goto('/partners');await expect(page.locator('.partner-insight-card')).toHaveCount(5);
 for(const row of rows.slice(0,2)){
  const card=page.locator('.partner-insight-card').filter({has:page.getByRole('heading',{name:row.name,exact:true})});
  await expect(card.getByTestId('partner-identities')).toHaveCount(0);
 }
 const maintained=page.locator('.partner-insight-card').filter({has:page.getByRole('heading',{name:'全部身份伙伴',exact:true})});
 await expect(maintained.getByRole('list',{name:'伙伴身份',exact:true}).getByRole('listitem')).toHaveText(identities);
 await expect(page.getByText('暂未维护',{exact:true})).toHaveCount(0);
 await page.screenshot({path:info.outputPath(`directory-visibility-${width}.png`),fullPage:true});
 for(const row of rows){
  await page.goto('/partners/'+row.id);await expect(page.getByRole('heading',{name:row.name,exact:true})).toBeVisible();
  if(row.identities?.length)await expect(page.getByRole('list',{name:'伙伴身份',exact:true}).getByRole('listitem')).toHaveText(row.identities);
  else await expect(page.getByTestId('partner-identities')).toHaveCount(0);
  await expect(page.getByText('暂未维护',{exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath(`${row.id}-${width}.png`),fullPage:true});
 }
 expect(unexpected).toEqual([]);
});

for(const width of [1440,390])test(`identity filtering uses stored identities and combines with existing filters ${width}`,async({page},info)=>{
 const {unexpected}=await visibilityFixture(page);await page.setViewportSize({width,height:900});await page.goto('/partners');
 const cards=page.locator('.partner-insight-card');await expect(cards).toHaveCount(5);
 const open=async(label:string)=>{await page.getByRole('button',{name:label+'筛选',exact:true}).click();const group=page.getByRole('group',{name:label+'选项',exact:true});await expect(group).toBeVisible();return group;};
 const close=async()=>page.keyboard.press('Escape');
 let group=await open('伙伴身份');await expect(group.getByRole('checkbox')).toHaveCount(6);
 const box=(await group.boundingBox())!;expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(width);
 await group.getByRole('checkbox',{name:identities[1],exact:true}).check();
 await expect(cards.locator('h2')).toHaveText(['全部身份伙伴','服务身份伙伴']);
 await group.getByRole('checkbox',{name:identities[0],exact:true}).check();
 await expect(cards.locator('h2')).toHaveText(['全部身份伙伴','服务身份伙伴','软件身份伙伴']);
 await group.getByRole('checkbox',{name:identities[0],exact:true}).uncheck();await close();
 group=await open('能力标签');await group.getByRole('checkbox',{name:'AI',exact:true}).check();await close();
 group=await open('行业');await group.getByRole('checkbox',{name:'金融',exact:true}).check();await close();
 await expect(cards.locator('h2')).toHaveText(['全部身份伙伴']);
 group=await open('区域');await group.getByRole('checkbox',{name:'北京',exact:true}).check();await close();
 await expect(page.getByRole('heading',{name:'暂无符合条件的伙伴',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'重置筛选与搜索',exact:true}).click();await expect(cards).toHaveCount(5);
 group=await open('伙伴身份');await group.getByRole('checkbox',{name:identities[1],exact:true}).check();
 await group.getByRole('button',{name:'清除',exact:true}).click();await expect(cards).toHaveCount(5);
 await group.getByRole('checkbox',{name:identities[3],exact:true}).check();await close();await expect(cards).toHaveCount(1);
 await page.getByLabel('搜索伙伴',{exact:true}).fill('服务身份伙伴');await expect(cards).toHaveCount(0);
 await page.getByRole('button',{name:'清除筛选',exact:true}).click();await expect(cards.locator('h2')).toHaveText(['服务身份伙伴']);
 await expect(page.getByLabel('搜索伙伴',{exact:true})).toHaveValue('服务身份伙伴');
 await page.getByLabel('搜索伙伴',{exact:true}).fill('');await expect(cards).toHaveCount(5);
 await expect(page.getByRole('button',{name:'清除筛选',exact:true})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:info.outputPath(`identity-filter-${width}.png`),fullPage:true});expect(unexpected).toEqual([]);
});
