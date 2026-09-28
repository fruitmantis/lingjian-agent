import {expect, test, type Page} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import standard from '../../shared/business-taxonomy.json';

const base = {ai_profile: null, case_count: 0, deliverable_count: 0};
const partners = [
  {...base, id:'alpha', name:'合成云桥伙伴', capabilities:'数据库迁移，系统集成；TCP/IP,CodeArts 应用交付,数据库迁移', industries:'金融', service_areas:'广东,欧洲'},
  {...base, id:'beta', name:'合成智造伙伴', capabilities:'数据库迁移', industries:'制造与工业', service_areas:'广东,江苏'},
  {...base, id:'gamma', name:'合成北辰伙伴', capabilities:'系统集成', industries:'金融', service_areas:'北京'},
  {...base, id:'delta', name:'合成远航伙伴', capabilities:'系统集成', industries:'金融', service_areas:'欧洲'},
  {...base, id:'empty', name:'合成待补充伙伴', capabilities:null, industries:null, service_areas:null, classification_pending:{industries:['待确认行业'],regions:['待确认区域']}},
  {...base, id:'prefix', name:'合成优化伙伴', capabilities:'数据库迁移优化', industries:'金融', service_areas:'广东'},
];

async function fixture(page: Page, fail = false, rows = partners) {
  const unexpected: string[] = [], errors: string[] = [];
  await page.addInitScript(() => localStorage.setItem('banfei:user:token', 'synthetic-filter-user'));
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname.replace(/^\/api/, '');
    if (!url.pathname.startsWith('/api/') && url.port !== '8000') return ['localhost','127.0.0.1'].includes(url.hostname) ? route.continue() : route.abort();
    if (req.method() !== 'GET') {unexpected.push(req.method() + ' ' + p); return route.abort();}
    if (p === '/auth/me') return route.fulfill({json:{id:'filter-user',username:'筛选验收',role:'user',status:'active',must_change_password:false}});
    if (p === '/health') return route.fulfill({json:{status:'ok'}});
    if (p === '/agent/tasks') return route.fulfill({json:{items:[],total:0,page:1,pageSize:20,totalPages:0}});
    if (p === '/partners/profiles') return fail ? route.fulfill({status:503,json:{detail:'伙伴加载失败'}}) : route.fulfill({json:rows});
    unexpected.push(p); return route.abort();
  });
  return {unexpected, errors};
}

for (const width of [1366,1920,390]) test(`partner filters combine without changing data ${width}`, async ({page}) => {
  await page.setViewportSize({width,height:width === 1920 ? 1080 : width === 390 ? 844 : 768});
  const result = await fixture(page);
  await page.goto('/partners');
  const cards = page.locator('.partner-insight-card');
  await expect(cards).toHaveCount(6);
  await page.evaluate(() => document.fonts.ready);
  const directory = path.resolve(process.env.PARTNER_FILTER_EVIDENCE_DIR || '/tmp/banfei-partner-filters/screenshots');
  await mkdir(directory, {recursive:true});
  const fits = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  const open = async (label: string) => {
    const trigger = page.getByRole('button', {name:`${label}筛选`, exact:true});
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await trigger.focus(); await page.keyboard.press('Enter');
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    const group = page.getByRole('group', {name:`${label}选项`, exact:true});
    await expect(group).toBeVisible(); await fits();
    const box = (await group.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(width);
    return group;
  };
  const close = async (label: string) => {
    await page.keyboard.press('Escape');
    await expect(page.getByRole('group', {name:`${label}选项`, exact:true})).toBeHidden();
    await expect(page.getByLabel(`${label}筛选`, {exact:true})).toBeFocused();
    await expect(page.getByLabel(`${label}筛选`, {exact:true})).toHaveAttribute('aria-expanded', 'false');
  };
  await fits();
  await page.screenshot({path:path.join(directory,`partners-${width}.png`),fullPage:true});
  const cap = await open('能力标签');
  // Deduplicate choices, preserve slashes/spaces and match exact labels, not prefixes.
  await expect(cap.getByRole('checkbox',{name:'数据库迁移',exact:true})).toHaveCount(1);
  await cap.getByRole('checkbox',{name:'数据库迁移',exact:true}).check(); await expect(cards).toHaveCount(2);
  await cap.getByRole('checkbox',{name:'系统集成',exact:true}).check(); await expect(cards).toHaveCount(4);
  await close('能力标签');
  const industry = await open('行业');
  await expect(industry.getByRole('checkbox')).toHaveCount(standard.industries.length);
  await expect(industry.getByRole('checkbox',{name:'待确认行业'})).toHaveCount(0);
  await industry.getByRole('checkbox',{name:'金融',exact:true}).check(); await expect(cards).toHaveCount(3);
  await close('行业');
  const region = await open('区域');
  await expect(region.getByRole('group',{name:'国内',exact:true}).getByRole('checkbox')).toHaveCount(34);
  await expect(region.getByRole('group',{name:'海外',exact:true}).getByRole('checkbox')).toHaveCount(6);
  await region.getByRole('checkbox',{name:'广东',exact:true}).check(); await expect(cards).toHaveCount(1);
  await region.getByRole('checkbox',{name:'欧洲',exact:true}).check(); await expect(cards).toHaveCount(2);
  await page.screenshot({path:path.join(directory,`region-open-${width}.png`),fullPage:true});
  await close('区域');
  await page.getByLabel('搜索伙伴',{exact:true}).fill('远航'); await expect(cards).toHaveCount(1);
  await expect(cards.locator('h2')).toHaveText('合成远航伙伴');
  await expect(page.locator('.result-count')).toHaveText('共 1 家伙伴');
  await page.screenshot({path:path.join(directory,`filtered-${width}.png`),fullPage:true});
  await open('能力标签'); await cap.getByRole('button',{name:'清除',exact:true}).click(); await close('能力标签');
  await expect(page.getByLabel('行业筛选').getByLabel('已选 1 项')).toBeVisible();
  await page.getByRole('button',{name:'清除筛选',exact:true}).click();
  await expect(page.getByLabel('搜索伙伴',{exact:true})).toHaveValue('远航'); await expect(cards).toHaveCount(1);
  await page.getByLabel('搜索伙伴',{exact:true}).fill(''); await expect(cards).toHaveCount(6);
  await expect(page.getByRole('button',{name:'清除筛选',exact:true})).toHaveCount(0);

  await open('能力标签');
  await cap.getByLabel('搜索能力标签选项').fill('tcp');
  await expect(cap.getByRole('checkbox')).toHaveCount(1);
  await cap.getByRole('checkbox',{name:'TCP/IP',exact:true}).check(); await expect(cards).toHaveCount(1);
  await cap.getByLabel('搜索能力标签选项').fill('不存在的标签');
  await expect(cap.getByText('没有匹配的选项')).toBeVisible(); await expect(cards).toHaveCount(1);
  await cap.getByLabel('搜索能力标签选项').fill(''); await close('能力标签');
  await open('行业'); await industry.getByRole('checkbox',{name:'汽车',exact:true}).check();
  await expect(cards).toHaveCount(0); await close('行业');
  await expect(page.getByRole('heading',{name:'暂无符合条件的伙伴'})).toBeVisible();
  await page.getByRole('button',{name:'重置筛选与搜索'}).click(); await expect(cards).toHaveCount(6);
  // Moving focus outside dismisses the menu without changing its selections.
  await open('行业'); await page.getByLabel('搜索伙伴',{exact:true}).click();
  await expect(industry).toBeHidden(); await page.getByLabel('区域筛选').click();
  await expect(industry).toBeHidden(); await expect(region).toBeVisible(); await close('区域');
  await fits(); expect(result.unexpected).toEqual([]); expect(result.errors).toEqual([]);
});

test('partner filter label text and row padding toggle without dismissing', async ({page}) => {
  const result = await fixture(page); await page.goto('/partners');
  for (const [dimension, option] of [['能力标签', '数据库迁移'], ['行业', '金融'], ['区域', '广东']]) {
    const trigger = page.getByRole('button', {name:`${dimension}筛选`, exact:true});
    await trigger.click();
    const group = page.getByRole('group', {name:`${dimension}选项`, exact:true});
    const checkbox = group.getByRole('checkbox', {name:option, exact:true});
    const row = checkbox.locator('..');
    // Click the label text, not Playwright's checkbox locator, then the row's empty padding.
    await row.click({position:{x:45, y:15}, delay:150});
    await expect(group).toBeVisible(); await expect(checkbox).toBeChecked();
    await row.click({position:{x:(await row.boundingBox())!.width - 4, y:15}, delay:150});
    await expect(group).toBeVisible(); await expect(checkbox).not.toBeChecked();
    await checkbox.check(); await expect(group).toBeVisible();
    await group.getByText('可多选', {exact:true}).click(); await expect(group).toBeVisible();
    // A non-focusable element outside must still dismiss the popup.
    await page.getByRole('heading', {name:'伙伴洞察', exact:true}).click();
    await expect(group).toBeHidden(); await trigger.click(); await expect(checkbox).toBeChecked();
    await checkbox.focus(); await page.keyboard.press('Space'); await expect(checkbox).not.toBeChecked();
    await group.getByRole('button', {name:'清除', exact:true}).click(); await expect(group).toBeVisible();
    await page.keyboard.press('Escape'); await expect(group).toBeHidden(); await expect(trigger).toBeFocused();
  }
  expect(result.unexpected).toEqual([]); expect(result.errors).toEqual([]);
});

test('partner loading failure does not present a false empty result', async ({page}) => {
  const result = await fixture(page, true); await page.goto('/partners');
  await expect(page.locator('.error-text')).toHaveText('伙伴加载失败');
  await expect(page.getByLabel('伙伴筛选')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'暂无符合条件的伙伴'})).toHaveCount(0);
  expect(result.unexpected).toEqual([]); expect(result.errors).toEqual([]);
});

// Match production scale with synthetic names/tags; exercise repeated mount/unmount and measurements.
test('large partner catalog remains responsive across repeated filters', async ({page}) => {
  const rows = Array.from({length:180}, (_,i) => ({...partners[i % partners.length], id:`scale-${i}`, name:`合成规模伙伴 ${i}`, capabilities:`能力组 ${i % 12},数据库迁移,系统集成,较长的集成交付能力标签 ${i % 4}`, industries:i % 2 ? '金融' : '制造与工业', service_areas:i % 3 ? '广东' : '欧洲'}));
  const result = await fixture(page, false, rows);
  let crashes = 0; page.on('crash', () => crashes++);
  await page.goto('/partners'); await expect(page.locator('.partner-insight-card')).toHaveCount(180);
  await page.evaluate(() => document.fonts.ready);
  await page.getByLabel('能力标签筛选',{exact:true}).click();
  const group = page.getByRole('group',{name:'能力标签选项',exact:true});
  for (let i=0;i<12;i++) {
    const box = group.getByRole('checkbox',{name:`能力组 ${i}`,exact:true});
    await box.check(); await expect(page.locator('.partner-insight-card')).toHaveCount(15);
    await box.uncheck(); await expect(page.locator('.partner-insight-card')).toHaveCount(180);
  }
  expect(crashes).toBe(0); expect(result.errors).toEqual([]); expect(result.unexpected).toEqual([]);
});
