import {expect, test, type Page} from '@playwright/test';

const partners = Array.from({length: 500}, (_, i) => ({id: `partner-${i}`, name: `合成伙伴 ${String(i).padStart(3, '0')}`}));
partners[498].name = 'Cooperate Cloud 498';
partners[499].name = '上海星河数据技术有限公司';
const user = {id:'select-user',username:'select-user',display_name:'合成测试用户',role:'user',status:'active',must_change_password:false};

async function fixture(page: Page, admin = false) {
  const identity = {...user, role:admin ? 'admin' : 'user'};
  await page.addInitScript(user => {
    localStorage.setItem(`banfei:${user.role}:token`, 'synthetic-select-token');
    localStorage.setItem(`banfei:${user.role}:user`, JSON.stringify(user));
  }, identity);
  const writes: {path:string;body:any}[] = [], queries: string[] = [], errors: string[] = [], unexpected: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('crash', () => errors.push('browser page crashed'));
  let entry = {id:'case-fixture',kind:'case',partner_id:partners[0].id,partner_name:partners[0].name,title:'合成资料',description:'合成简介',category_id:'technical-3',visible:false,file_count:0,processing_status:'ready',updated_at:'2026-09-29T00:00:00Z',profile_needs_update:false};
  await page.route('**/*', async route => {
    const req=route.request(),url=new URL(req.url());
    if (!url.pathname.startsWith('/api/') && url.port!=='8000') return route.continue();
    const path=url.pathname.replace(/^\/api/,'');
    if(req.method()!=='GET') {
      const body=req.postDataJSON()||{};writes.push({path,body});
      if(path==='/cases'||path==='/cases/case-fixture') {
        entry={...entry,...body,partner_name:partners.find(p=>p.id===body.partner_id)?.name||entry.partner_name};
        return route.fulfill({status:path==='/cases'?201:200,json:entry});
      }
      unexpected.push(req.method()+' '+path);
      return route.fulfill({status:400,json:{detail:'Unexpected synthetic write'}});
    }
    let json: unknown;
    if(path==='/auth/me') json=identity;
    else if(path==='/health') json={status:'ok'};
    else if(path==='/partners') json=partners;
    else if(path==='/agent/tasks') json={items:[],total:0,page:1,pageSize:20,totalPages:0};
    else if(path==='/enablement/context') {const partner=partners.find(p=>p.id===url.searchParams.get('partner_id'));json={partner:partner?{...partner,intro:'合成资料'}:null,project:null,shared_case:null,evidence:[]};}
    else if(path==='/admin/partner-materials') {queries.push(url.search);json={items:[entry],total:url.searchParams.get('page')==='2'?24:1,partners};}
    else if(path==='/cases/case-fixture/deliverables') json=[];
    else {unexpected.push(req.method()+' '+path);return route.fulfill({status:404,json:{detail:'Unlisted fixture API'}});}
    return route.fulfill({json});
  });
  return {writes,queries,errors,unexpected};
}

async function reachable(page: Page) {
  const list=page.getByRole('listbox');await expect(list).toBeVisible();
  const bounds=await list.boundingBox();expect(bounds).toBeTruthy();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  const option=list.getByRole('option').first();await expect(option).toBeInViewport();
  expect(await option.evaluate(el=>{const b=el.getBoundingClientRect();return el.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2));})).toBeTruthy();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
}

test('new task searches 500 partners by partial Chinese or case-insensitive English name',async({page},testInfo)=>{
  const state=await fixture(page);await page.goto('/?mode=development');
  const picker=page.getByRole('combobox',{name:'选择目标伙伴',exact:true});
  await picker.fill('星河');await expect(page.getByRole('option')).toHaveCount(1);
  await reachable(page);await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:testInfo.outputPath('new-task-partner-search.png')});
  await page.getByRole('option',{name:partners[499].name}).locator('span').first().click();
  await expect(picker).toHaveValue(partners[499].name);await expect(picker).toHaveAttribute('data-partner-id',partners[499].id);
  await expect(page).toHaveURL(/partner_id=partner-499/);
  await picker.fill('  COOPERATE  ');await expect(page.getByRole('option')).toHaveCount(1);
  await picker.press('Enter');await expect(picker).toHaveValue(partners[498].name);
  expect(state.writes).toEqual([]);expect(state.errors).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('keyboard selection, IME, Escape and outside clicks preserve intentional selection',async({page})=>{
  const state=await fixture(page);await page.goto('/?mode=development&partner_id=partner-499');
  const picker=page.getByRole('combobox',{name:'选择目标伙伴',exact:true});
  await expect(picker).toHaveValue(partners[499].name);
  await picker.fill('不存在的伙伴');await expect(page.getByText('没有匹配的伙伴，请换个名称试试。')).toBeVisible();
  await picker.press('Enter');await expect(picker).toHaveAttribute('data-partner-id','partner-499');
  await picker.press('Escape');await expect(picker).toHaveValue(partners[499].name);
  await picker.fill('合成伙伴 00');await expect(page.getByRole('option')).toHaveCount(10);
  await picker.evaluate(el=>el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true})));
  await expect(picker).toHaveAttribute('aria-expanded','true');await expect(picker).toHaveAttribute('data-partner-id','partner-499');
  await picker.press('ArrowDown');await picker.press('Enter');await expect(picker).toHaveAttribute('data-partner-id','partner-1');
  await picker.fill('星河');await page.getByLabel('发展方向',{exact:true}).click();
  await expect(picker).toHaveValue(partners[1].name);await expect(page.getByRole('listbox')).toHaveCount(0);
  await picker.click();await picker.press('Tab');await expect(page.getByRole('listbox')).toHaveCount(0);
  expect(state.writes).toEqual([]);expect(state.errors).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('source task keeps the original partner locked',async({page})=>{
  const state=await fixture(page);await page.goto('/?mode=development&partner_id=partner-499&task_id=source-task');
  const picker=page.getByRole('combobox',{name:'选择目标伙伴',exact:true});
  await expect(picker).toBeDisabled();await expect(picker).toHaveValue(partners[499].name);
  await expect(page.getByRole('listbox')).toHaveCount(0);expect(state.writes).toEqual([]);expect(state.errors).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('materials partner filter searches locally and can return to all partners',async({page},testInfo)=>{
  const state=await fixture(page,true);await page.goto('/admin/partner-materials?category_group=technical&q=资料&page=2');
  const picker=page.getByRole('combobox',{name:'筛选伙伴',exact:true});
  await expect(page.getByRole('heading',{name:'伙伴资料',exact:true})).toBeVisible();
  await picker.fill('星河');await reachable(page);
  expect(new URL(page.url()).searchParams.has('partner_id')).toBe(false);
  await page.screenshot({path:testInfo.outputPath('admin-filter-partner-search.png')});
  await page.getByRole('option',{name:partners[499].name}).click();
  await expect(page).toHaveURL(/partner_id=partner-499/);
  expect(new URL(page.url()).searchParams.get('category_group')).toBe('technical');expect(new URL(page.url()).searchParams.has('page')).toBe(false);
  await expect.poll(()=>state.queries.some(q=>q.includes('partner_id=partner-499'))).toBeTruthy();
  await picker.click();await page.getByRole('option',{name:'全部伙伴',exact:true}).click();
  await expect(picker).toHaveAttribute('data-partner-id','');
  expect(new URL(page.url()).searchParams.has('partner_id')).toBe(false);expect(new URL(page.url()).searchParams.get('q')).toBe('资料');
  expect(state.writes).toEqual([]);expect(state.errors).toEqual([]);expect(state.unexpected).toEqual([]);
});

test('material create and edit submit selected ID, never typed search text',async({page},testInfo)=>{
  const state=await fixture(page,true);await page.goto('/admin/partner-materials');
  await page.getByRole('button',{name:'新增资料',exact:true}).click();
  let dialog=page.getByRole('dialog',{name:'新增资料',exact:true});
  await dialog.getByLabel('标题',{exact:true}).fill('合成新资料');await dialog.getByLabel('一级分类',{exact:true}).selectOption('technical');await dialog.getByLabel('二级分类',{exact:true}).selectOption('technical-3');
  const picker=dialog.getByRole('combobox',{name:'关联伙伴',exact:true});
  await picker.fill('星河');await expect(dialog.getByRole('button',{name:'保存资料',exact:true})).toBeDisabled();await reachable(page);
  await page.screenshot({path:testInfo.outputPath('admin-editor-partner-search.png')});
  await page.getByRole('option',{name:partners[499].name}).locator('span').first().click();
  await dialog.getByRole('button',{name:'保存资料',exact:true}).click();
  await expect.poll(()=>state.writes.length).toBe(1);expect(state.writes[0]).toMatchObject({path:'/cases',body:{partner_id:'partner-499'}});
  dialog=page.getByRole('dialog',{name:'合成新资料',exact:true});await dialog.getByRole('button',{name:'编辑资料',exact:true}).click();
  const editing=dialog.getByRole('combobox',{name:'关联伙伴',exact:true});await expect(editing).toHaveValue(partners[499].name);
  await editing.fill('cooperate');await editing.press('Enter');await dialog.getByRole('button',{name:'保存资料',exact:true}).click();
  await expect.poll(()=>state.writes.length).toBe(2);expect(state.writes[1]).toMatchObject({path:'/cases/case-fixture',body:{partner_id:'partner-498'}});
  expect(state.errors).toEqual([]);expect(state.unexpected).toEqual([]);
});
