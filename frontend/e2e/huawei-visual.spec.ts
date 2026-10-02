import {selectPartner} from './partner-select-helper';
import {fixtureLogin} from './identity-fixture';
import { test, expect } from '@playwright/test';
import { mkdir, readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { createFontVerification } from './font-verification';
import { writeFile } from 'node:fs/promises';

const API = 'http://localhost/api';

// Fail closed before authentication: this suite must never reuse the manual server.
async function isolatedSession() {
  if (process.env.PLAYWRIGHT_REUSE_SERVER === '1') throw new Error('Visual tests require isolated servers');
  let isolatedBackend = false;
  for (const pid of (await readdir('/proc')).filter(value => /^\d+$/.test(value))) {
    try {
      const command = (await readFile(`/proc/${pid}/cmdline`, 'utf8')).split('\0');
      if (!command.includes('uvicorn') || !command.includes('8000')) continue;
      const environment = (await readFile(`/proc/${pid}/environ`, 'utf8')).split('\0');
      if (process.env.PLAYWRIGHT_DATABASE_URL && !environment.includes(`DATABASE_URL=${process.env.PLAYWRIGHT_DATABASE_URL}`)) throw new Error('Unexpected backend database');
      isolatedBackend = true;
    } catch (error) {
      if ((error as Error).message === 'Unexpected backend database') throw error;
    }
  }
  if (!isolatedBackend) throw new Error('Cannot verify isolated backend');
  const session = JSON.parse(await readFile(`${process.env.BANFEI_TEST_ROOT}/visual-session.json`, 'utf8'));
  if (session.database !== 'postgresql:'+new URL(process.env.PLAYWRIGHT_DATABASE_URL!).pathname.slice(1)) throw new Error('Unexpected fixture database');
  return session;
}

// Own synthetic resources keep the visual suite runnable without earlier specs.
test.beforeAll(async ({ request }) => {
  const session = await isolatedSession();
  const headers = { Authorization: `Bearer ${session.access_token}` };
  const tags = await (await request.get(`${API}/development/capabilities`, { headers })).json();
  const capability = tags.find((tag: { name: string }) => tag.name === '盘古大模型');
  expect(capability).toBeTruthy();
  for (const [resource_type, title] of [['course', 'RAG 知识库工程课程（视觉合成测试）'], ['lab', 'Agent 系统集成实验（视觉合成测试）']]) {
    const created = await request.post(`${API}/admin/enablement/resources`, { headers, data: { base_revision: 0, metadata: {
      resource_type, title, summary: '仅用于临时数据库的视觉验证，不是正式业务资源。', level: 'advanced', duration_minutes: 90, role_ids:['role-1'], zone_ids:['zone-1'],
      source_url: 'https://example.com/visual-fixture',

    } } });
    expect(created.ok()).toBeTruthy();
    let row = await created.json();
    const url = `${API}/admin/enablement/resources/${row.source_id}`;
    const permissions = await request.patch(url + '/permissions', { headers, data: { base_revision: row.revision,
      system_visible: true, model_allowed: true, partner_allowed: true, reason: '仅限临时库合成验证' } });
    expect(permissions.ok()).toBeTruthy(); row = await permissions.json();

    expect((await request.post(url + '/publish', { headers, data: { base_revision: row.revision } })).ok()).toBeTruthy();
  }
});

for (const width of [1366, 1920]) test(`Huawei visual system and layout ${width}`, async ({ page, request, browser }) => {
  test.setTimeout(120_000);
  const session = await isolatedSession();
  const typography = process.env.HUAWEI_FONT_VERIFICATION === '1' ? await createFontVerification(page) : null;
  const ordinary=await (await fixtureLogin(request,'user_a')).json();
  await page.addInitScript(value => {localStorage.setItem('banfei:user:token',value.access_token);localStorage.setItem('banfei:user:user',JSON.stringify(value.user));},ordinary);
  await page.addInitScript(value => {
    localStorage.setItem(`banfei:${value.user.role}:token`, value.access_token); localStorage.setItem(`banfei:${value.user.role}:user`, JSON.stringify(value.user));
  }, session);
  await page.setViewportSize({ width, height: width === 1366 ? 768 : 1080 });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const directory = path.resolve(process.env.HUAWEI_VISUAL_EVIDENCE_DIR || '../artifacts/huawei-visual');
  await mkdir(directory, { recursive: true });
  async function capture(name: string) {
    if (typography) await typography.inspect(name);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.addStyleTag({ content: 'nextjs-portal { display:none }' });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    const blue = await page.evaluate(() => {
      const findings: string[] = [];
      for (const element of document.querySelectorAll('body *')) {
        if (!(element instanceof HTMLElement || element instanceof SVGElement)) continue;
        const rectangle = element.getBoundingClientRect();
        if (!rectangle.width || !rectangle.height) continue;
        const style = getComputedStyle(element);
        if (style.visibility === 'hidden' || style.display === 'none') continue;
        for (const value of [style.color, style.backgroundColor, style.borderTopColor, style.outlineColor]) {
          const channels = value.match(/[\d.]+/g)?.map(Number);
          if (!channels || channels.length < 3 || channels[3] === 0) continue;
          const [r,g,b] = channels.map(channel => channel / 255);
          const max = Math.max(r,g,b), min = Math.min(r,g,b), delta = max-min;
          if (!delta || delta / max < .18) continue;
          const hue = ((max === r ? (g-b)/delta : max === g ? (b-r)/delta+2 : (r-g)/delta+4)*60+360)%360;
          if (hue > 185 && hue < 275) findings.push(`${element.tagName}.${element.getAttribute('class')}: ${value}`);
        }
      }
      return [...new Set(findings)];
    });
    expect(blue, 'No rendered brand blue').toEqual([]);
    await expect(page.locator('aside .brand-text')).toHaveText('伴飞 Agent');
    if (!new URL(page.url()).pathname.startsWith('/admin')) await expect(page.locator('aside').getByRole('link', { name: '资源中心', exact: true })).toBeInViewport();
    await page.screenshot({ path: path.join(directory, `${name}-${width}.png`), fullPage: true });
  }
  await page.goto('/');
  await expect(page).toHaveTitle(/伴飞 Agent/);
  await expect(page.locator('.sidebar .lingjian-mark')).toHaveCSS('background-color', 'rgb(199, 0, 11)');
  await page.locator('#requirement').fill('寻找具备数据库迁移与系统集成经验的交付伙伴');
  await expect(page.getByRole('button', { name: '开始', exact: true })).toHaveCSS('background-color', 'rgb(199, 0, 11)');
  await capture('01-project-match');
  await page.getByRole('tablist', { name: '任务模式', exact: true }).getByRole('tab', { name: '伙伴发展', exact: true }).click();
  await selectPartner(page, 'partner-1');
  await page.getByLabel('发展方向', { exact: true }).fill('希望形成企业级 Agent 应用交付能力');
  await expect(page.getByRole('tablist', { name: '任务模式', exact: true }).getByRole('tab', { name: '伙伴发展', exact: true })).toHaveCSS('border-bottom-color', 'rgb(199, 0, 11)');
  await capture('02-development');
  await page.getByRole('button', { name: '开始', exact: true }).click();
  await expect(page).toHaveURL(/\/tasks\/[^/?]+$/);
  const id = new URL(page.url()).pathname.split('/').pop();
  await expect.poll(async () => {
    const result = await request.get(`${API}/development/plans/${id}`, { headers: { Authorization: `Bearer ${session.access_token}` } });
    return (await result.json()).runs[0].status;
  }, { timeout: 30_000 }).toBe('ready');
  await expect(page.getByRole('heading', { name: '继续问伴飞', exact: true })).toBeVisible();
  await capture('03-advisor');
  for (const [route, name] of [['/resources','04-resources'], ['/scenes','05-scenes'], ['/partners','06-partners'], ['/tasks','07-tasks'], ['/admin','08-admin']]) {
    await page.goto(route);
    await expect(page.locator('main h1').first()).toBeVisible();
    await expect(page.getByText('正在读取资源…', { exact: true })).toHaveCount(0);
    if (route === '/partners') await expect(page.locator('.partner-insight-card').first()).toBeVisible();
    if (route === '/tasks') await expect(page.locator('tbody tr').first()).toBeVisible();
    if (route === '/admin') await expect(page.locator('.admin-metric-card').first()).toBeVisible();
    if (route === '/resources') await expect(page.locator('.learning-card').first()).toBeVisible();
    await capture(name);
  }
  const publicContext = await browser.newContext();
  const login = await publicContext.newPage();
  await login.goto('http://localhost/login');
  await expect(login.getByRole('heading', { name: '使用身份 Key 登录', exact: true })).toBeVisible();
  await publicContext.close();
  expect((await request.get('http://localhost/icon.svg')).status()).toBe(200);
  if (typography) await writeFile(path.join(directory, `font-validation-${width}.json`), JSON.stringify(typography.evidence(), null, 2));
  expect(errors).toEqual([]);
});
